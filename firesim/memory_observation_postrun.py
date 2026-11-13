#!/usr/bin/env python3
"""Opt-in post-driver FASED readout via FireSim's existing post_run_hook.

Installation is local only and requires an exact fresh prepared-manifest hash.
Only the root coordinator invokes the installed hook through managed FireSim.
Neither runner nor driver is modified. The child writes a sidecar, never run.json.
"""
import argparse
import base64
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

try:
    from firesim import batch_runner as batch
    from firesim import memory_observation as original
    from firesim import run_prepared
except ModuleNotFoundError:
    import batch_runner as batch
    import memory_observation as original
    import run_prepared

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 'postrun-memory-observation'
OBSERVABILITY_SHA = 'e0cefa3a9fc03e40755eea4b89cd9970ad75690f361bf400a5f9887fea68d712'
DRIVER_ELF_SHA = '8f78167b754097623b031f41d7e5f121f4ae368f716255fdcf574693a071c48a'
DRIVER_TAR_SHA = '5457de1e9c0dd1e3c52efbf5d083bdac7dfa5a5e3124c9887961c08159b03450'
IMAGE_TAR_SHA = '9bbe1f12a2b18091c28b05ea43c001e579f70c8cfef0f528fcb49003212fb776'
IMMUTABLE_KEYS = ('schema_version', 'created_at_utc', 'cases', 'image', 'driver', 'elf_sha256',
                  'runner_sha256', 'prepared_manager_sha256', 'prepared_runtime_sha256',
                  'prepared_hwdb_sha256', 'observability_audit', 'capture_checklist_frozen',
                  'launch_authorization_receipt', 'require_regions', 'require_goldens')


def digest(path):
    return batch.digest(path)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def merge(target, entries):
    for name, expected in entries.items():
        path = Path(name).resolve()
        need(path.is_file() and digest(path) == expected, 'Changed immutable input: ' + str(path))
        key = str(path)
        need(key not in target or target[key] == expected, 'Conflicting immutable digest: ' + key)
        target[key] = expected


def projection(manifest):
    return {key: manifest.get(key) for key in IMMUTABLE_KEYS}


def remote_program():
    # Preserve the reviewed remote no-write program exactly except its new
    # output directory. This avoids colliding with the pre-init observer.
    old = "directory=base/'memory-observation';directory.mkdir(mode=0o700)"
    need(original.REMOTE.count(old) == 1, 'Reviewed remote observer layout changed')
    return original.REMOTE.replace(old, "directory=base/'memory-observation-postrun';directory.mkdir(mode=0o700)", 1)


def hook_text(job, plan_sha, python):
    argv = [python, str(Path(__file__).resolve()), '--observe-owned-postrun',
            '--job', str(job), '--expected-plan-sha256', plan_sha, '--results']
    return '#!/usr/bin/env sh\nset -eu\ntest "$#" -eq 1\nexec ' + shlex.join(argv) + ' "$1"\n'


def workload_bytes(plan, job):
    w = copy.deepcopy(plan['workload_before_hook'])
    w['post_run_hook'] = str(job / DIRECTORY / 'hook.sh')
    return (json.dumps(w, indent=2) + '\n').encode()


def install(job, expected_manifest, probe_build, host, prototype_only=False):
    """Install only into a NEW unused prepared job; performs no network calls."""
    import yaml
    job, probe_build = Path(job).resolve(), Path(probe_build).resolve()
    need(digest(job / 'run.json') == expected_manifest, 'Prepared manifest hash changed')
    m = run_prepared.verify(job)
    need(m.get('lifecycle_started') in (None, False) and not (job / DIRECTORY).exists(), 'Fresh opt-in job only')
    need(re.fullmatch(r'[a-zA-Z0-9._-]+', host), 'Invalid SSH host alias')
    need(m.get('require_regions') is True and m.get('require_goldens') is True,
         'Postrun observation requires independent declared region goldens')
    audit_path = Path(m['observability_audit']['report']).resolve()
    audit = json.loads(audit_path.read_text())
    need(digest(audit_path) == m['observability_audit']['sha256'] == OBSERVABILITY_SHA
         and m['observability_audit']['verified'] is True, 'Exact archived-driver audit required')
    need(m['driver']['sha256'] == DRIVER_TAR_SHA and m['image']['sha256'] == IMAGE_TAR_SHA
         and audit['driver_binary_sha256'] == DRIVER_ELF_SHA
         and audit['generated_header_sha256'] == original.HEADER_SHA, 'Exact archived image/driver/MMIO contract required')
    receipt = json.loads((probe_build / 'report.json').read_text())
    need(receipt['schema'] == 'iris.readonly_memory_observer_build.v1' and receipt['pass'] is True
         and receipt['source_sha256'] == original.SOURCE_SHA
         and receipt['binary_sha256'] == digest(probe_build / 'readonly-fased-latency') == original.BINARY_SHA,
         'Exact reviewed no-write observer required')
    auth = m.get('launch_authorization_receipt', {})
    need(isinstance(auth.get('sha256'), str) and isinstance(auth.get('remote_path'), str),
         'Prepared standing-user authorization binding required')
    workload_path = job / 'manager/workloads/iris-batch.json'
    workload = json.loads(workload_path.read_text())
    need(not workload.get('post_run_hook'), 'Existing post-run hook cannot be silently replaced')
    inputs = dict(m['input_sha256'])
    merge(inputs, receipt['input_sha256'])
    merge(inputs, {str(probe_build / name): value for name, value in receipt['artifact_sha256'].items()})
    merge(inputs, audit['input_sha256'])
    merge(inputs, {str(p): digest(p) for p in [Path(__file__).resolve(), Path(original.__file__).resolve(),
          Path(batch.__file__).resolve(), Path(run_prepared.__file__).resolve(), Path(sys.executable).resolve(),
          probe_build / 'report.json', audit_path]})
    # A preparer may already have put private copies into its input map. These
    # two files have separately checked, narrowly defined transformations.
    inputs.pop(str(workload_path), None)
    inputs.pop(str(job / 'manager/config_runtime.yaml'), None)
    prepared = dict(m['prepared_file_sha256'])
    prepared.pop('manager/config_runtime.yaml', None)  # runner legitimately binds its owned directory at launch
    prepared.pop('manager/workloads/iris-batch.json', None)  # deterministic hook addition checked below
    plan = {'schema': 'iris.postdriver_fased_observation_plan.v1', 'job': str(job), 'host': host,
            'prototype_only': bool(prototype_only), 'phase': 'normal driver exit/results copied; before owned final kill',
            'immutable_manifest_projection': projection(m), 'immutable_input_sha256': inputs,
            'immutable_prepared_file_sha256': prepared, 'workload_before_hook': workload,
            'runtime_before_owned_directory': yaml.safe_load((job / 'manager/config_runtime.yaml').read_text()),
            'python': str(Path(sys.executable).resolve()), 'helper_sha256': digest(Path(__file__)),
            'remote_program_sha256': hashlib.sha256(remote_program().encode()).hexdigest(),
            'binary_sha256': original.BINARY_SHA, 'source_sha256': original.SOURCE_SHA,
            'generated_header_sha256': original.HEADER_SHA, 'observability_report_sha256': OBSERVABILITY_SHA,
            'observer_build_receipt_sha256': digest(probe_build / 'report.json'),
            'driver_binary_sha256': DRIVER_ELF_SHA, 'driver_bundle_sha256': DRIVER_TAR_SHA,
            'image_tar_sha256': IMAGE_TAR_SHA,
            'device': '/dev/xdma0_user', 'BDF': '0000:01:00.0',
            'access': 'O_RDONLY/PROT_READ; no writes', 'registers': {'writeLatency': 0, 'readLatency': 4},
            'clock_units': 'FASED memory-model target-clock cycles, not CPU or host cycles',
            'scope': 'Postdriver configuration registers only; not measured latency, per-hart latency or image attestation',
            'missing_configuration_fields': ['readMaxReqs', 'writeMaxReqs', 'relaxFunctionalModel'],
            'full_source_image_association_verified': False, 'physical_memory_latency_measured': False,
            'calibration_usable': False}
    destination = job / DIRECTORY
    destination.mkdir(mode=0o700)
    shutil.copyfile(probe_build / 'readonly-fased-latency', destination / 'readonly-fased-latency')
    shutil.copyfile(probe_build / 'report.json', destination / 'build.json')
    (destination / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    plan_sha = digest(destination / 'plan.json')
    hook = destination / 'hook.sh'
    hook.write_text(hook_text(job, plan_sha, plan['python'])); hook.chmod(0o700)
    workload_path.write_bytes(workload_bytes(plan, job))
    m['input_sha256'] = inputs
    # Parent run_task rechecks these actual hook bytes before every phase.
    for p in [destination / 'plan.json', destination / 'build.json', destination / 'readonly-fased-latency', hook, workload_path]:
        m['input_sha256'][str(p)] = digest(p)
    m['readonly_memory_postrun'] = {'plan': str(destination / 'plan.json'), 'sha256': plan_sha,
                                   'optional': True, 'sidecar': DIRECTORY + '/observation.json',
                                   'child_does_not_modify_run_manifest': True, 'prototype_only': bool(prototype_only)}
    m['prepared_file_sha256'].update({str(p.relative_to(job)): digest(p) for p in destination.iterdir() if p.is_file()})
    m['prepared_file_sha256']['manager/workloads/iris-batch.json'] = digest(workload_path)
    batch.save_manifest(job, m)
    run_prepared.verify(job)
    return {'schema': 'iris.postdriver_fased_observation_installation.v1', 'installed': True,
            'hardware_contacted': False, 'job': str(job), 'plan_sha256': plan_sha,
            'prepared_manifest_sha256': digest(job / 'run.json'), 'prototype_only': bool(prototype_only)}


def verify_active(job, expected_plan, results):
    import yaml
    plan_path = job / DIRECTORY / 'plan.json'
    need(digest(plan_path) == expected_plan, 'Frozen postrun plan changed')
    p = json.loads(plan_path.read_text()); m = json.loads((job / 'run.json').read_text())
    need(p['schema'] == 'iris.postdriver_fased_observation_plan.v1' and p['job'] == str(job)
         and p['helper_sha256'] == digest(Path(__file__)) and p['prototype_only'] is False,
         'Unqualified or prototype-only postrun hook')
    need(projection(m) == p['immutable_manifest_projection'], 'Immutable job identity changed')
    need(m.get('lifecycle_started') is True and m.get('active_phase') == 'runworkload'
         and not m.get('cleanup_status') in ('passed', 'refused_or_failed'), 'Not before owned final cleanup')
    commands = m.get('commands', [])
    need(len(commands) == 3 and [c['task'] for c in commands] == ['kill', 'infrasetup', 'runworkload']
         and all(c['status'] == 'passed' and type(c['returncode']) is int and c['returncode'] == 0
                 and c.get('timed_out') is False for c in commands[:2])
         and commands[2]['status'] == 'running', 'Not inside normal managed runworkload post hook')
    need(m.get('readonly_memory_postrun', {}).get('sha256') == expected_plan, 'Manifest postrun-plan identity changed')
    for name, value in p['immutable_input_sha256'].items():
        need(m['input_sha256'].get(name) == value and digest(name) == value, 'Immutable source mismatch: ' + name)
    for name, value in p['immutable_prepared_file_sha256'].items():
        target = (job / name).resolve()
        need(job in target.parents and digest(target) == value, 'Prepared artifact mismatch: ' + name)
    for path, expected in ((job / 'manager/workloads/iris-batch.json', workload_bytes(p, job)),
                           (job / DIRECTORY / 'hook.sh', hook_text(job, expected_plan, p['python']).encode())):
        need(path.read_bytes() == expected, 'Postrun invocation changed')
    need(digest(job / DIRECTORY / 'readonly-fased-latency') == original.BINARY_SHA
         and p['binary_sha256'] == original.BINARY_SHA
         and p['source_sha256'] == original.SOURCE_SHA
         and p['generated_header_sha256'] == original.HEADER_SHA
         and p['remote_program_sha256'] == hashlib.sha256(remote_program().encode()).hexdigest(),
         'Reviewed read-only contract changed')
    runtime_path = job / 'manager/config_runtime.yaml'
    runtime = yaml.safe_load(runtime_path.read_text())
    need(digest(runtime_path) == m.get('execution_runtime_sha256'), 'Owned execution runtime changed')
    before = copy.deepcopy(p['runtime_before_owned_directory'])
    owned = m.get('remote_simulation_dir')
    need(isinstance(owned, str) and re.fullmatch(r'/scratch/[a-z_][a-z0-9_-]*/firesim/[0-9a-f]{32}', owned), 'Owned remote directory shape')
    before['run_farm']['recipe_arg_overrides']['default_simulation_dir'] = owned
    need(runtime == before, 'Runtime changed beyond runner-owned private path')
    results = Path(results).resolve()
    need((job / 'manager/results-workload').resolve() in results.parents and results.is_dir(), 'Wrong postrun results directory')
    logs = sorted(results.rglob('uartlog'))
    need(len(logs) == 1, 'Exactly one copied guest console required')
    console = logs[0].read_text(errors='replace')
    exits = re.findall(r'COMMAND_EXIT_CODE="([0-9]+)"', console)
    need(exits == ['0'] and console.count('COMMAND_EXIT_CODE') == 1 and '*** PASSED ***' in console
         and '*** FAILED ***' not in console and 'IRIS_FATAL' not in console,
         'Normal driver/guest exit not independently established')
    private = copy.deepcopy(m)
    batch.collect_guest_results(job / 'manager', private)
    need(private.get('regions_validated') is True and private.get('region_checksums_independently_validated') is True,
         'Declared region/checksum completion required')
    return p, m, {'console_sha256': digest(logs[0]), 'driver_exit_status': 0,
                   'normal_completion_verified': True, 'region_count': len(private['regions']),
                   'independent_region_checksums_verified': True}


def capture_remote(job, plan, manifest, identity, uid):
    binary = job / DIRECTORY / 'readonly-fased-latency'
    code = ('BASE=' + repr(manifest['remote_simulation_dir']) + '\nUID=' + repr(uid)
            + '\nEXPECTED=' + repr(original.BINARY_SHA) + '\nLOCK=' + repr(dict(identity, token=manifest['lock_token']))
            + '\nAUTH=' + repr(manifest['launch_authorization_receipt']['remote_path'])
            + '\nBINARY=' + repr(base64.b64encode(binary.read_bytes()).decode()) + '\n' + remote_program())
    destination = job / DIRECTORY
    try:
        r = subprocess.run(batch.ssh_prefix(plan['host']) + ['/usr/bin/python3', '-I', '-S', '-'],
                           input=code.encode(), capture_output=True, timeout=25)
    except subprocess.TimeoutExpired as e:
        (destination / 'transport.stdout').write_bytes(e.stdout or b'')
        (destination / 'transport.stderr').write_bytes(e.stderr or b'')
        raise ValueError('Optional postdriver read transport timed out') from e
    (destination / 'transport.stdout').write_bytes(r.stdout)
    (destination / 'transport.stderr').write_bytes(r.stderr)
    need(r.returncode == 0, 'Postdriver read-only transport failed')
    remote = json.loads(r.stdout)
    for key, name in [('probe_stdout_b64', 'probe.stdout'), ('probe_stderr_b64', 'probe.stderr')]:
        if key in remote:
            (destination / name).write_bytes(base64.b64decode(remote[key], validate=True))
    return remote


def decode_remote(remote, manifest):
    probe = remote.get('probe', {})
    need(remote.get('status') == 'sampled' and type(remote.get('returncode')) is int and remote['returncode'] == 0
         and remote.get('binary_sha256') == original.BINARY_SHA
         and type(remote.get('uid')) is int and remote['uid'] == manifest['shared_lock']['uid']
         and remote.get('base') == manifest['remote_simulation_dir']
         and remote.get('device_identity', {}).get('bdf') == '0000:01:00.0'
         and probe.get('test_file') is False and probe.get('hardware_writes') is False
         and probe.get('access') == 'O_RDONLY/PROT_READ' and probe.get('register_width_bits') == 32
         and probe.get('presence_byte_offset') == 356 and probe.get('presence_verified_before_and_after') is True
         and probe.get('stable_two_samples') is True, 'Unqualified postdriver probe envelope')
    values = {}
    for name, offset in [('writeLatency', 0), ('readLatency', 4)]:
        value = probe.get(name, {})
        need(type(value.get('byte_offset')) is int and value['byte_offset'] == offset
             and type(value.get('first')) is int and type(value.get('second')) is int
             and value['first'] == value['second'] and 0 <= value['first'] < 2**32 - 1,
             'Unknown/unstable/ambiguous postdriver register value')
        values[name] = value['first']
    return values


def observe(job, expected_plan, results):
    """Root-coordinator hook only; optional failures do not rewrite guest outcome."""
    job = Path(job).resolve(); target = job / DIRECTORY
    need(target.is_dir() and not (target / 'observation.json').exists(), 'Fresh installed observation sidecar required')
    raw_before = (job / 'run.json').read_bytes()
    record = {'schema': 'iris.postdriver_fased_observation.v1', 'optional': True, 'status': 'unavailable',
              'started_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'hardware_writes': False,
              'hardware_access_attempted': False, 'selected_parameters': None,
              'sampled_before_driver_initialization': False, 'sampled_after_normal_driver_exit': False,
              'configuration_registers_only': True, 'clock_units': 'FASED memory-model target-clock cycles, not CPU cycles',
              'physical_memory_latency_measured': False, 'source_image_association_verified': False,
              'calibration_usable': False, 'guest_outcome_modified': False, 'child_run_manifest_modified': False}
    try:
        plan, m, completion = verify_active(job, expected_plan, results)
        record.update(plan_sha256=expected_plan, completion=completion, normal_driver_exit_verified=True,
                      driver_binary_sha256=plan['driver_binary_sha256'], image_tar_sha256=plan['image_tar_sha256'])
        identity = {key: m['shared_lock'][key] for key in ('uid', 'user', 'boot_id', 'authorization_id', 'authorization_sha256')}
        need(type(identity['uid']) is int and identity['uid'] >= 0 and re.fullmatch(r'[0-9a-f]{32}', m['lock_token'])
             and m['launch_authorization_receipt']['sha256'] == identity['authorization_sha256'], 'Owned lock/authorization identity')
        host, token = plan['host'], m['lock_token']
        def safe(stage):
            batch.checked_remote_lock(host, token, None, identity)
            inspection = batch.bind_launch_authorization(host, batch.inspect_remote(host), m)
            record[stage] = inspection
            # No owned-holder exemption here: the normal driver must be gone.
            batch.require_safe_remote(inspection, identity['authorization_id'], identity['boot_id'])
            need(inspection['uid'] == identity['uid'] and inspection['user'] == identity['user'], 'Observer account changed')
            return inspection
        safe('inspection_before')
        record['hardware_access_attempted'] = True
        try:
            remote = capture_remote(job, plan, m, identity, identity['uid'])
            record['remote'] = remote
            values = decode_remote(remote, m)
        finally:
            safe('inspection_after')
        record.update(status='observed_postdriver_configuration_registers', selected_parameters=values,
                      sampled_after_normal_driver_exit=True)
    except Exception as error:
        record.update(error=str(error), selected_parameters=None)
    finally:
        # Parent holds an in-memory manifest. Never replace or annotate its file.
        if (job / 'run.json').read_bytes() != raw_before:
            record.update(status='unavailable', selected_parameters=None, error='Parent manifest changed during postrun observation')
        record['finished_at_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        record['raw_artifact_sha256'] = {p.name: digest(p) for p in target.iterdir()
                                          if p.is_file() and p.name in ('transport.stdout', 'transport.stderr', 'probe.stdout', 'probe.stderr')}
        with (target / 'observation.json').open('x') as f:
            f.write(json.dumps(record, indent=2) + '\n')
    return record


def main():
    p = argparse.ArgumentParser(__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--install', action='store_true')
    mode.add_argument('--observe-owned-postrun', action='store_true')
    p.add_argument('--job', type=Path, required=True)
    p.add_argument('--expected-prepared-manifest-sha256')
    p.add_argument('--probe-build', type=Path)
    p.add_argument('--host', default='sohumpc')
    p.add_argument('--prototype-only', action='store_true')
    p.add_argument('--expected-plan-sha256')
    p.add_argument('--results', type=Path)
    a = p.parse_args()
    if a.install:
        need(a.probe_build and a.expected_prepared_manifest_sha256, 'Exact prepared hash and probe build required')
        result = install(a.job, a.expected_prepared_manifest_sha256, a.probe_build, a.host, a.prototype_only)
    else:
        need(a.expected_plan_sha256 and a.results and not a.prototype_only, 'Bound managed postrun arguments required')
        result = observe(a.job, a.expected_plan_sha256, a.results)
    print(json.dumps({k: result[k] for k in ('schema', 'status', 'installed', 'hardware_contacted', 'plan_sha256', 'prepared_manifest_sha256') if k in result}))


if __name__ == '__main__':
    main()
