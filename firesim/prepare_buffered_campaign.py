#!/usr/bin/env python3
"""Freeze a new exact-ELF buffered fitting campaign; never contact hardware."""
import argparse
import collections
import importlib.util
import json
import os
from pathlib import Path
import shlex
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.export_cases import export
from batch_runner import digest, prepare, save_manifest, validate_cases
from prepare_managed_campaign import add_observer, snapshot_inputs
from run_prepared import verify

ROLE = 'buffered_fitting_campaign_v1'
SPLIT = 'iris-buffered-fit-campaign-v1'
WATCHDOG, PHASE_TIMEOUT = 600, 780
NO_TARGET_BOUND = ('No target +max-cycles: a successful hardware loader/startup exceeded5billion global '
                   'driver cycles, so1.9billion can terminate loading; the original driver also uses32-bit '
                   'atoi. Only the owned foreground wall watchdog bounds this run.')


def merge_inputs(target, identities):
    """Evidence maps may be ROOT-relative; prepared manifests never are."""
    for name, expected in identities.items():
        path = Path(name)
        absolute = os.path.normpath(str(path if path.is_absolute() else ROOT/path))
        if absolute in target and target[absolute] != expected:
            raise ValueError('Conflicting buffered input identity: '+absolute)
        target[absolute] = expected


def validator():
    path = ROOT/'benchmarks/campaign_buffered/validate.py'
    spec = importlib.util.spec_from_file_location('iris_buffered_fitting_validator', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def corpus_cases(corpus, original):
    if (corpus.get('schema') != 'iris.buffered_fitting_corpus.v1' or corpus.get('split_id') != SPLIT
            or corpus.get('trials') != 3 or corpus.get('physical_harts') != 3
            or corpus.get('expected_region_count') != 4050 or len(corpus['cases']) != 2208):
        raise ValueError('Complete three-trial three-hart buffered training corpus required')
    prior = {c['case_id']: c for c in original['cases']}
    if len(prior) != 2208 or original.get('split_id') != 'iris-broad-fit-campaign-v1' or original.get('trials') != 3:
        raise ValueError('Exact fitting-only semantic parent corpus required')
    parents = collections.defaultdict(set)
    seen = set()
    for case in corpus['cases']:
        if not case['case_id'].startswith('buffered.v1.') or case['case_id'] in seen:
            raise ValueError('Unique new buffered case IDs required')
        seen.add(case['case_id'])
        old_id = case['case_id'][len('buffered.v1.'):]
        if old_id not in prior:
            raise ValueError('Buffered case has no declared original fitting parent')
        old = prior[old_id]
        copied = dict(case)
        if copied.pop('semantic_parent_case_id', None) != old['parent_case_id']:
            raise ValueError('Semantic original-parent identity changed')
        copied['case_id'] = old_id
        if copied['parent_case_id'] != 'buffered.v1.'+old['parent_case_id']:
            raise ValueError('Distinct buffered parent identity required')
        copied['parent_case_id'] = old['parent_case_id']
        if copied != old or case.get('split') != 'fitting':
            raise ValueError('Buffered kernel/mask/independent golden differs from its original fitting case')
        parents[case['semantic_parent_case_id']].add(case['trial_id'])
    if len(parents) != 736 or any(trials != {0, 1, 2} for trials in parents.values()):
        raise ValueError('All736 semantic parents must retain all three trials')
    rows = export(corpus)
    for row, case in zip(rows, corpus['cases']):
        row.update({key: case[key] for key in ('parent_case_id', 'semantic_parent_case_id', 'trial_id', 'suite', 'mask')})
    if (sum(len(r['active_harts']) for r in rows) != 4050
            or [sum(h in r['active_harts'] for r in rows) for h in range(3)] != [1425, 1380, 1245]):
        raise ValueError('Exact configured all-three-hart coverage required')
    validate_cases(rows, True)
    return rows


def check_readback(elf, layout, corpus):
    if (layout.get('schema') != 'iris.buffered_campaign_readback_layout.v1'
            or layout.get('elf_sha256') != digest(elf) or layout.get('record_bytes') != 64
            or layout.get('records') != 4050 or layout.get('fields') !=
                ['case_index', 'hart', 'start', 'end', 'instret', 'checksum', 'expected', 'pass']
            or layout.get('stop_sentinel_initial_value') != (1 << 64)-1
            or layout.get('stop_sentinel_complete_value') != 0
            or layout.get('file_backed_initial_sentinel_verified') is not True
            or layout.get('intentional_debugger_stop_is_normal_guest_exit') is not False):
        raise ValueError('Exact known-sentinel64-byte-record readback contract required')
    objects = layout['objects']
    if set(objects) != {'buffered_records', 'buffered_measurements_done', 'buffered_record_count', 'buffered_case_count'}:
        raise ValueError('Complete physical readback object identities required')
    if objects['buffered_records']['size'] != 64*4050:
        raise ValueError('Readback array must contain every measured region')
    raw = Path(elf).read_bytes()
    if raw[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Little-endian ELF64 required')
    phoff = struct.unpack_from('<Q', raw, 32)[0]; phsize, phnum = struct.unpack_from('<HH', raw, 54)
    sentinel = objects['buffered_measurements_done']['address']; found = False
    for k in range(phnum):
        typ, flags, off, va, pa, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', raw, phoff+k*phsize)
        if typ != 1: continue
        if any(max(base, pa) < min(base+size, pa+memsz) for base, size in corpus['memory_regions'].values()):
            raise ValueError('ELF overlaps a tested memory window')
        if pa <= sentinel and sentinel+8 <= pa+filesz:
            if int.from_bytes(raw[off+sentinel-pa:off+sentinel-pa+8], 'little') != (1 << 64)-1:
                raise ValueError('Actual loaded sentinel bytes are not known UINT64_MAX')
            found = True
    if not found: raise ValueError('Completion sentinel must be file-backed before CRT/BSS')


def admit(build, ready_sha):
    build = Path(build).resolve(); ready_path = build/'ready.json'
    if digest(ready_path) != ready_sha:
        raise ValueError('Exact frozen buffered ready packet required')
    ready = json.loads(ready_path.read_text()); built = json.loads((build/'build.json').read_text())
    corpus_path, elf = build/'corpus.json', build/'campaign.elf'
    corpus = json.loads(corpus_path.read_text()); qualification_path = build/'qualification.json'
    qualification = json.loads(qualification_path.read_text())
    if (ready.get('schema') != 'iris.buffered_campaign_ready.v1'
            or ready.get('status') != 'ready_for_root_managed_preparation'
            or ready.get('required_cases') != 2208 or ready.get('required_regions') != 4050
            or ready.get('trials') != 3 or Path(ready['elf']).resolve() != elf
            or Path(ready['corpus_path']).resolve() != corpus_path
            or ready.get('fitting_only') is not True or ready.get('global_heldout') is not False):
        raise ValueError('Exact complete buffered ready identity required')
    for path, key in [(elf, 'elf_sha256'), (corpus_path, 'corpus_sha256'),
                      (build/'build.json', 'build_sha256'), (qualification_path, 'qualification_sha256')]:
        if digest(path) != ready[key]: raise ValueError('Ready artifact changed: '+str(path))
    if (built.get('schema') != 'iris.buffered_campaign_build.v1' or built.get('elf_sha256') != digest(elf)
            or built.get('corpus_sha256') != digest(corpus_path) or built.get('cases') != 2208
            or built.get('regions') != 4050 or built.get('trials') != 3
            or built.get('parent_kernel_source_unchanged') is not True
            or built.get('same_ELF_as_original_campaign') is not False
            or built.get('old_campaign_timings_applicable') is not False):
        raise ValueError('New exact-ELF build with explicit old-timing exclusion required')
    original_path = build/'parent-derived/corpus.json'; original = json.loads(original_path.read_text())
    if digest(original_path) != corpus['original_corpus_sha256']:
        raise ValueError('Original independent fitting goldens changed')
    cases = corpus_cases(corpus, original)
    layout_path = build/'readback-layout.json'; layout = json.loads(layout_path.read_text())
    if digest(layout_path) != built['readback_layout_sha256']:
        raise ValueError('Readback layout changed')
    check_readback(elf, layout, corpus)
    identities = {str(p): digest(p) for p in (ready_path, build/'build.json', corpus_path, elf,
                  qualification_path, original_path, layout_path, build/'disassembly.txt')}
    merge_inputs(identities, built['input_sha256'])
    merge_inputs(identities, ready.get('source_inputs_sha256', {}))
    merge_inputs(identities, ready.get('support_source_sha256', {}))
    merge_inputs(identities, qualification.get('support_source_sha256', {}))
    if any(ready['source_inputs_sha256'].get(name) != expected for name, expected in built['input_sha256'].items()):
        raise ValueError('Ready source map does not preserve every exact build source input')
    split_path = ROOT/'calibration/empirical-buffered-v1/split.json'
    review_path = ROOT/'calibration/empirical-buffered-v1/review.json'
    if (digest(split_path) != ready['frozen_split_sha256']
            or digest(review_path) != ready['independent_prelaunch_review_sha256']
            or digest(build/'disassembly.txt') != built['disassembly_sha256']):
        raise ValueError('Frozen split/independent review/disassembly identity changed')
    policy_path = ROOT/'calibration/empirical-buffered-v1/policy.json'
    for path in (split_path, review_path, policy_path):
        evidence = json.loads(path.read_text())
        identities[str(path)] = digest(path)
        merge_inputs(identities, evidence.get('input_sha256', {}))
    if (qualification.get('schema') != 'iris.buffered_campaign_qualification.v1'
            or qualification.get('status') != 'passed' or qualification.get('pass') is not True
            or qualification.get('elf_sha256') != digest(elf)
            or qualification.get('corpus_sha256') != digest(corpus_path)
            or qualification.get('old_campaign_timings_reused') is not False
            or qualification.get('frozen_split_sha256') != ready['frozen_split_sha256']
            or qualification.get('independent_prelaunch_review_sha256') != ready['independent_prelaunch_review_sha256']):
        raise ValueError('Successful exact buffered functional qualification required')
    negatives = qualification['negative_controls']
    expected_negatives = {'checksum', 'expected_checksum', 'parent_case_id', 'trial_id', 'suite', 'hart',
                          'pass', 'start_cycle', 'end_cycle', 'missing_region', 'duplicate_region',
                          'missing_completion', 'duplicate_completion', 'fatal'}
    if (len(negatives) != 14 or {n['name'] for n in negatives} != expected_negatives
            or any(n.get('rejected') is not True for n in negatives)):
        raise ValueError('Independent numerical/identity/boundary corruption controls required')
    gates = qualification['functional_runs']
    if len(gates) != 2 or {g['seed'] for g in gates} != {0, 17}:
        raise ValueError('Actual deterministic seeds0/17 required')
    for gate in gates:
        folder = build/f"seed{gate['seed']}"; path = folder/'run.json'; result = json.loads(path.read_text())
        if (digest(path) != gate['results_sha256'] or digest(folder/'run.stdout') != gate['stdout_sha256']
                or gate.get('exit_status') != 0 or gate.get('regions') != 4050
                or result.get('schema') != 'iris.buffered_campaign_functional_run.v1'
                or result.get('status') != 'passed' or result.get('functional_checks_passed') is not True
                or result.get('exit_status') != 0 or result.get('hardware_contacted') is not False
                or result['argv'][-1] != str(elf) or '-p3' not in result['argv']
                or result['argv'].count('--iris-schedule-seed='+str(gate['seed'])) != 1):
            raise ValueError('Buffered functional gate identity/exit mismatch')
        for name in ('stdout', 'stderr'):
            if digest(folder/('run.'+name)) != result[name+'_sha256']:
                raise ValueError('Raw seeded gate output changed')
        proof = validator().validate((folder/'run.stdout').read_text(), corpus)
        if proof.get('functional_checks_passed') is not True or proof.get('regions') != 4050:
            raise ValueError('Independent buffered console validator refused functional gate')
        merge_inputs(identities, result['input_sha256'])
        merge_inputs(identities, {str(p): digest(p) for p in (path, folder/'run.stdout', folder/'run.stderr')})
    for name, expected in identities.items():
        if digest(name) != expected: raise ValueError('Buffered build/gate input changed: '+name)
    return ready, corpus, cases, elf, identities


def freeze(args):
    import yaml
    build, output = args.build.resolve(), args.output.resolve()
    ready, corpus, cases, elf, identities = admit(build, args.expected_ready_sha256)
    authorization = args.authorization_receipt.resolve(); receipt = json.loads(authorization.read_text())
    if receipt.get('schema') != 'iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Actual standing user authorization receipt required')
    controls_path = ROOT/'build/buffered-campaign-tools-local-v2/report.json'
    controls = json.loads(controls_path.read_text())
    if (controls.get('schema') != 'iris.buffered_campaign_managed_tools_local_controls.v1'
            or controls.get('pass') is not True or controls.get('unit_admission_tests') != 10
            or controls.get('real_wrong_role_archive', {}).get('rejected') is not True):
        raise ValueError('Actual helper admission/corruption/archive controls must pass')
    for name, expected in controls['input_sha256'].items():
        if digest(name) != expected: raise ValueError('Helper controls bind changed source/evidence: '+name)
    merge_inputs(identities, controls['input_sha256']); identities[str(controls_path)] = digest(controls_path)
    if args.validate_only:
        return {'status': 'local_admission_validated_no_job_or_hardware', 'expected_regions': 4050, 'hardware_contacted': False}
    fs = Path('/scratch/eygao/iris-cy/sims/firesim'); deploy = fs/'deploy'
    manager, manifest = prepare(deploy, output, elf, cases, deploy/'config_runtime.yaml', deploy/'config_hwdb.yaml',
        ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json', profile_interval=1000000)
    from memory_observation import freeze as freeze_memory
    freeze_memory(args.memory_probe_build.resolve(), output, manifest)
    add_observer(manager)
    watchdog = manager/'iris_workload_watchdog.py'; text = watchdog.read_text()
    if text.count('SECONDS=1500') != 1: raise ValueError('Reviewed watchdog changed')
    watchdog.write_text(text.replace('SECONDS=1500', 'SECONDS='+str(WATCHDOG), 1))
    runtime_path = manager/'config_runtime.yaml'; runtime = yaml.safe_load(runtime_path.read_text())
    previous = runtime['target_config'].get('plusarg_passthrough', '')
    if '+max-cycles' in previous or '+fesvr-step-size' in previous:
        raise ValueError('Conflicting or unsafe loader/cycle bound')
    runtime['target_config']['plusarg_passthrough'] = (previous+' +fesvr-step-size=128').strip()
    runtime_path.write_text(yaml.safe_dump(runtime, sort_keys=False))
    for name in ('corpus.json', 'ready.json', 'build.json', 'qualification.json', 'readback-layout.json'):
        (output/name).write_bytes((build/name).read_bytes())
    (output/'original-corpus.json').write_bytes((build/'parent-derived/corpus.json').read_bytes())
    (output/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
    (output/'launch-authorization.json').write_bytes(authorization.read_bytes())
    checklist = {'schema': 'iris.buffered_fitting_capture_checklist.v1', 'frozen_before_launch': True,
        'fitting_only': True, 'global_heldout': False, 'cases': 2208, 'semantic_parents': 736,
        'trials': 3, 'expected_regions': 4050, 'regions_by_hart': [1425, 1380, 1245],
        'console_policy': corpus['console_policy'], 'cache_policy': corpus['cache_policy'],
        'inactive_policy': corpus['inactive_policy'], 'phase_markers_expected': 0,
        'old_campaign_timings_applicable': False, 'new_exact_ELF_reference_required': True,
        'required': ['Raw all4050 mcycle/minstret/checksum and exactcase/parent/trial/hart records, terminal/fail-fast output',
            'All kernel+preparation source/input/compiler/ELF/readback layout and known file-backed completion sentinel',
            'Full kill/infrasetup/runworkload/kill phase timing, fresh complete inspection/shared lock/owned cleanup/external archive',
            'Raw manager/UART/heartbeat/available aggregate FASED CSV and reviewed read-only FASED settings'],
        'unavailable_instrumentation': ['TracerV', 'AutoCounter', 'SynthPrint'],
        'remote_wall_watchdog_seconds': WATCHDOG, 'host_phase_timeout_seconds': PHASE_TIMEOUT,
        'target_cycle_bound': None, 'target_cycle_bound_omission_reason': NO_TARGET_BOUND,
        'source_image_association_verified': False, 'calibration_usable': False, 'timing_certified': False}
    (output/'capture-checklist.json').write_text(json.dumps(checklist, indent=2)+'\n')
    launch = ['#!/usr/bin/env bash', 'export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH',
        'cd '+shlex.quote(str(fs))+' || exit 1',
        'source ./sourceme-manager.sh --skip-ssh-setup > '+shlex.quote(str(output/'launch-environment.stdout'))+
            ' 2> '+shlex.quote(str(output/'launch-environment.stderr')),
        'exec '+shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3', str(ROOT/'firesim/run_prepared.py'),
            str(output), '--execute', '--authorization-id', receipt['authorization']['authorization_id'], '--timeout', str(PHASE_TIMEOUT)])]
    (output/'launch.sh').write_text('\n'.join(launch)+'\n'); (output/'launch.sh').chmod(0o700)
    env_paths = [fs/'sourceme-manager.sh', fs/'env.sh', fs.parent.parent/'env.sh']
    sources = [Path(__file__).resolve(), ROOT/'firesim/analyze_buffered_campaign.py', ROOT/'firesim/test_buffered_campaign.py',
        ROOT/'firesim/analyze_campaign.py', ROOT/'firesim/run_prepared.py', ROOT/'firesim/prepare_managed_campaign.py',
        ROOT/'firesim/workload_watchdog.py', ROOT/'firesim/setup_phase_observer.py', ROOT/'firesim/managed_programming_tools.py',
        ROOT/'benchmarks/export_cases.py', ROOT/'benchmarks/campaign_buffered/validate.py', authorization,
        ROOT/'build/xilinx-tool-paths-v1.json', *env_paths,
        Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc')]
    merge_inputs(identities, {str(path): digest(path) for path in sources})
    merge_inputs(manifest['input_sha256'], identities)
    if any(not Path(name).is_absolute() for name in manifest['input_sha256']):
        raise ValueError('Prepared input identities must all be absolute across manager cwd changes')
    snapshot_inputs(output, manifest['input_sha256'])
    manifest.update(campaign_role=ROLE, require_regions=True, require_goldens=True, expected_regions=4050,
        fitting_only=True, global_heldout=False, launch_authorization_receipt=receipt,
        corpus_sha256=digest(output/'corpus.json'), ready_sha256=args.expected_ready_sha256,
        old_campaign_timings_applicable=False, new_exact_ELF_reference_required=True,
        calibration_usable=False, timing_accuracy_certified=False, hardware_source_association_verified=False,
        prepared_manager_sha256=digest(manager/'firesim'), prepared_runtime_sha256=digest(runtime_path),
        frozen_capture_checklist_sha256=digest(output/'capture-checklist.json'),
        environment_source_sha256={str(p): digest(p) for p in env_paths},
        loader_override={'fesvr_step_size_target_cycles': 128, 'target_cycle_bound': None,
            'target_cycle_bound_omission_reason': NO_TARGET_BOUND, 'remote_wall_watchdog_seconds': WATCHDOG,
            'foreground': True, 'driver_binary_unchanged': True})
    manifest['prepared_file_sha256'] = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*'))
        if p.is_file() and p.name != 'run.json' and not p.is_symlink()
        and not any(parent.is_symlink() for parent in p.parents if parent != output)}
    save_manifest(output, manifest); verify(output)
    return {'status': manifest['status'], 'expected_regions': 4050, 'hardware_contacted': False, 'job': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--build', type=Path, default=ROOT/'build/campaign-buffered-fit-v1')
    parser.add_argument('--expected-ready-sha256', required=True)
    parser.add_argument('--authorization-receipt', type=Path, required=True)
    parser.add_argument('--memory-probe-build', type=Path, default=ROOT/'build/fased-readonly-managed-v2')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    print(json.dumps(freeze(parser.parse_args())))
