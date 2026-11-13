# Derived read-only verifier; original diagnostic reader is preserved unchanged.
# Scope: two new source-bound operator packet kinds, with mandatory goldens.
"""Read-only diagnostic archive integrity, including failed guest evidence.

Integrity PASS never means numerical PASS or that all lifecycle commands passed.
Setup and final owned cleanup must pass; workload failures remain explicit.
No archived content is executed. The diagnostic numerical gate runs separately.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

CHUNK = 1024 * 1024
MAX_JSON_BYTES = 64 * CHUNK
MAX_UART_BYTES = 256 * CHUNK


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(CHUNK), b''):
            h.update(data)
    return h.hexdigest()


def signature(path):
    st = Path(path).stat()
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def json_bytes(data):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON key: ' + str(key))
            result[key] = value
        return result
    def bad(value):
        raise ValueError('nonfinite JSON: ' + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=bad)


def relative_name(name):
    need(type(name) is str and name and '\\' not in name, 'invalid archive-relative path')
    path = PurePosixPath(name)
    need(not path.is_absolute() and '..' not in path.parts and str(path) == name, 'unsafe/noncanonical archive path: ' + name)
    return name


def lifecycle(state):
    need(state.get('status') in ['completed_uncertified', 'failed'], 'Diagnostic must be terminal')
    need(state.get('campaign_role') in {'bounded_campaign_memory_roofline','bounded_campaign_panel_b_ab'} and state.get('primary_measurement_eligible') is False, 'Only explicit source-bound campaign archives are in scope')
    roles = {'bounded_campaign_memory_roofline': ('memory_roofline', 432),
             'bounded_campaign_panel_b_ab': ('panel_b_ab', 54)}
    kind, regions = roles[state['campaign_role']]
    need(state.get('campaign_kind') == kind and len(state.get('cases', [])) == regions,
         'Explicit operator kind and complete case roster required')
    need(state.get('require_regions') is True and state.get('require_goldens') is True,
         'Operator archives require regions and independent goldens')
    need(state.get('cleanup_error') is None, 'Owned diagnostic cleanup error')
    need(state.get('cleanup_status') == 'passed', 'owned cleanup did not pass')
    need(type(state.get('require_regions')) is bool and type(state.get('require_goldens')) is bool and state.get('strict_postgate'), 'Explicit scope and mandatory independent numerical gate required')
    need(state.get('lifecycle_policy') == 'kill -> infrasetup -> runworkload -> kill', 'lifecycle policy mismatch')
    commands = state.get('commands')
    need(type(commands) is list and [c.get('task') for c in commands] == ['kill','infrasetup','runworkload','kill'], 'incomplete/reordered four-phase lifecycle')
    for index, command in enumerate(commands):
        if index == 2:
            need(command.get('status') in ['passed', 'failed', 'timed_out', 'interrupted'] and type(command.get('returncode')) is int and type(command.get('timed_out')) is bool, 'Diagnostic workload status missing')
        else:
            need(command.get('status') == 'passed' and type(command.get('returncode')) is int and command['returncode'] == 0 and command.get('timed_out') is False, 'Setup/owned cleanup did not pass')
        need(type(command.get('phase_index')) is int and command['phase_index'] == index+1, 'phase index mismatch')
        need(command.get('cleanup_phase') is (index == 3), 'final phase is not declared owned cleanup')
    lock = state.get('shared_lock', {})
    private = state.get('private_directory', {})
    need(lock.get('kind') == 'exclusive_atomic_directory' and lock.get('path') == '/scratch/firesim/iris-locks/fpga0', 'shared lock evidence missing')
    need(type(lock.get('uid')) is int and private.get('uid') == lock['uid'], 'cleanup/private directory owner mismatch')
    need(type(state.get('lock_token')) is str and state['lock_token'] and private.get('path') == state.get('remote_simulation_dir') and PurePosixPath(private.get('path','')).name == state['lock_token'], 'owned private directory/token mismatch')
    need(type(lock.get('boot_id')) is str and lock['boot_id'], 'lock boot identity missing')
    inspections = state.get('safety_inspections', [])
    for phase in ['kill','infrasetup','runworkload','cleanup']:
        matches = [item.get('report', {}) for item in inspections if item.get('stage') == phase]
        need(len(matches) == 1, 'missing/ambiguous safety inspection: ' + phase)
        check = matches[0]
        need(check.get('inspection_complete') is True and check.get('inspection_errors') == [] and check.get('launch_authorization_verified') is True, 'incomplete/unauthorized inspection: ' + phase)
        need(check.get('boot_id') == lock['boot_id'] and check.get('uid') == lock['uid'], 'inspection owner/boot mismatch: ' + phase)


def verify(job, expected_elf_sha256):
    need(digest(expected_elf_sha256), 'explicit expected ELF SHA256 must be lowercase64hex')
    job = Path(job).resolve()
    run_path = job/'run.json'
    state_bytes = run_path.read_bytes()
    state = json_bytes(state_bytes)
    lifecycle(state)
    need(state.get('elf_sha256') == expected_elf_sha256, 'wrong expected ELF SHA256')
    capture = state.get('capture', {})
    need(capture.get('status') == 'captured' and type(capture.get('returncode')) is int and capture['returncode'] == 0, 'archive capture did not pass')
    need(capture.get('archive_contains_pre_capture_result_manifest') is True and digest(capture.get('captured_run_manifest_sha256')), 'capture does not bind frozen pre-capture run manifest')
    archive = Path(capture['archive'])
    archive_sig = signature(archive)
    archive_sha = sha_file(archive)
    need(archive_sha == capture.get('archive_sha256'), 'archive SHA256 mismatch')
    seen, retained, uart = {}, {}, []
    with tarfile.open(archive, 'r|gz') as stream:
        for member in stream:
            name = relative_name(member.name)
            need(member.isfile(), 'nonregular archive member: ' + name)
            need(name not in seen, 'duplicate archive member: ' + name)
            is_uart = name.endswith('/uartlog')
            keep = name in ('capture-manifest.json','job/run.json') or is_uart
            if keep:
                need(member.size <= (MAX_UART_BYTES if is_uart else MAX_JSON_BYTES), 'retained metadata/UART exceeds explicit size cap')
            h, count, chunks = hashlib.sha256(), 0, []
            source = stream.extractfile(member)
            need(source is not None, 'unreadable archive member')
            with source:
                for data in iter(lambda: source.read(CHUNK), b''):
                    h.update(data); count += len(data)
                    if keep:
                        chunks.append(data)
            need(count == member.size, 'truncated archive member: ' + name)
            seen[name] = {'bytes':count, 'sha256':h.hexdigest()}
            if keep:
                retained[name] = b''.join(chunks)
            if is_uart:
                uart.append(name)
    need(signature(archive) == archive_sig, 'archive changed during verification')
    need('capture-manifest.json' in retained and 'job/run.json' in retained, 'archive manifest/run missing')
    manifest = json_bytes(retained['capture-manifest.json'])
    inventory = {}
    for item in manifest.get('files', []):
        name = relative_name(item['path'])
        need(name not in inventory and name != 'capture-manifest.json', 'duplicate/self inventory member')
        need(type(item.get('bytes')) is int and item['bytes'] >= 0 and digest(item.get('sha256')), 'malformed archive inventory record')
        inventory[name] = {'bytes':item['bytes'], 'sha256':item['sha256']}
    payload_seen = {k:v for k,v in seen.items() if k != 'capture-manifest.json'}
    need(payload_seen == inventory, 'archive inventory differs from actual bytes/members')
    need(sha_bytes(retained['job/run.json']) == capture['captured_run_manifest_sha256'], 'captured run SHA256 mismatch')
    frozen = json_bytes(retained['job/run.json'])
    lifecycle(frozen)
    for key in ['campaign_role','campaign_kind','progress_packet','strict_postgate','status','error','cleanup_error','cleanup_status','commands','elf_sha256','input_sha256','prepared_file_sha256','cases','shared_lock','private_directory','lock_token','remote_simulation_dir','regions_validated','region_checksums_independently_validated','execution_runtime_sha256','execution_runner_sha256']:
        need(frozen.get(key) == state.get(key), 'live/frozen run contract changed: ' + key)
    need(frozen['elf_sha256'] == expected_elf_sha256, 'frozen ELF identity differs')
    inputs = frozen.get('input_sha256')
    need(type(inputs) is dict and inputs, 'nonempty frozen input closure required')
    for source, wanted in inputs.items():
        need(type(source) is str and Path(source).is_absolute() and digest(wanted), 'invalid frozen input identity')
        snapshot = 'job/prepared-inputs/' + wanted
        need(snapshot in payload_seen and payload_seen[snapshot]['sha256'] == wanted, 'missing/altered frozen input snapshot: ' + source)
    runtime_overrides = []
    prepared = frozen.get('prepared_file_sha256')
    need(type(prepared) is dict and prepared, 'prepared file roster missing')
    for name, wanted in prepared.items():
        relative_name(name)
        need(digest(wanted), 'invalid prepared SHA256')
        if name == 'manager/config_runtime.yaml' and frozen.get('execution_runtime_sha256') is not None:
            executed = frozen['execution_runtime_sha256']
            need(digest(executed) and all(c.get('actual_input_sha256',{}).get('runtime_sha256') == executed for c in frozen['commands']), 'runtime override not bound by every executed phase')
            if executed != wanted:
                runtime_overrides.append({'path':name, 'prepared_sha256':wanted, 'executed_sha256':executed})
            wanted = executed
        member = 'job/' + name
        need(member in payload_seen and payload_seen[member]['sha256'] == wanted, 'missing/altered prepared file: ' + name)
    deployed_elf = 'job/manager/workloads/iris-batch/batch.elf'
    need(deployed_elf in payload_seen and payload_seen[deployed_elf]['sha256'] == expected_elf_sha256, 'archived deployed ELF bytes differ')
    execution_runner = frozen.get('execution_runner_sha256')
    need(digest(execution_runner) and execution_runner in inputs.values(), 'executed runner is not in frozen input snapshots')
    for command in frozen['commands']:
        for channel in ['stdout','stderr']:
            name = relative_name(command[channel+'_path'])
            wanted = command[channel+'_sha256']
            need(digest(wanted) and payload_seen.get('job/'+name,{}).get('sha256') == wanted, 'altered/missing lifecycle log: ' + name)
    for name, wanted in frozen.get('artifact_sha256', {}).items():
        member = 'job/' + relative_name(name)
        need(digest(wanted) and payload_seen.get(member,{}).get('sha256') == wanted, 'altered/missing captured artifact: ' + name)
    primary = [name for name in uart if name.startswith('job/manager/results-workload/')]
    need(len(primary) == 1, 'one primary archived workload UART required')
    need(all(retained[name] == retained[primary[0]] for name in uart), 'UART copies differ byte-for-byte')
    need(run_path.read_bytes() == state_bytes and signature(archive) == archive_sig, 'source evidence changed before publication')
    report = {
        'schema':'iris.diagnostic_archive_integrity.v1', 'pass':True, 'integrity_only':True, 'numerical_admission':False, 'primary_measurement_eligible':False, 'original_run_status':frozen['status'], 'original_run_error':frozen.get('error'),
        'archive':str(archive), 'archive_sha256':archive_sha,
        'expected_ELF_sha256':expected_elf_sha256, 'ELF_sha256':frozen['elf_sha256'],
        'deployed_ELF_member':deployed_elf, 'all_lifecycle_phases_recorded_and_owned_cleanup_verified':True,
        'all_managed_commands_passed':all(c.get('status')=='passed' and c.get('returncode')==0 and c.get('timed_out') is False for c in frozen['commands']),
        'frozen_input_paths':len(inputs), 'all_frozen_snapshot_content_hashes_verified':True,
        'prepared_files_verified':len(prepared), 'explicit_execution_runtime_overrides':runtime_overrides,
        'verified_files':len(payload_seen), 'UART_member':primary[0],
        'identical_UART_copies':uart, 'UART_sha256':payload_seen[primary[0]]['sha256'],
        'UART_bytes':len(retained[primary[0]]), 'console_source':'verified archive only',
        'live_source_paths_revalidated':False,
        'missing_optional_context':manifest.get('missing_optional_context', []),
        'source_readers':'Invoke separately on this verified UART. Archive integrity does not replace numerical/profile admission.',
        'hardware_source_image_attestation':False, 'physical_busy_available':False,
        'hardware_actions':False, 'source_run_json_sha256':sha_bytes(state_bytes),
        'archived_run_json_sha256':sha_bytes(retained['job/run.json'])
    }
    return report, retained[primary[0]], retained['job/run.json']


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-elf-sha256', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        report, uart, frozen = verify(args.job, args.expected_elf_sha256)
        (args.output/'uartlog').write_bytes(uart)
        (args.output/'archived-run.json').write_bytes(frozen)
    except (ValueError, KeyError, TypeError, OSError, tarfile.TarError) as error:
        report = {'schema':'iris.generic_archive_intake.v1','pass':False,
                  'error':str(error),'job':str(args.job),'expected_ELF_sha256':args.expected_elf_sha256,
                  'original_evidence_preserved':True,'hardware_actions':False}
    report['reader_sha256'] = sha_file(Path(__file__))
    temp = args.output/'report.json.pending'
    temp.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    temp.rename(args.output/'report.json')
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report['pass'] else 1)


if __name__ == '__main__':
    main()
