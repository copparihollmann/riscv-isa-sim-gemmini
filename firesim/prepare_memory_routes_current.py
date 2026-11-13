#!/usr/bin/env python3
"""Prepare NEW repeated scalar memory routes with current managed controls; no launch."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from batch_runner import digest, prepare, save_manifest, validate_cases
from prepare_managed_campaign import add_observer, snapshot_inputs
from prepare_buffered_priority import merge_inputs, NO_TARGET_BOUND
from run_prepared import verify

ROLE = 'memory_routes_current_fitting_v1'
WATCHDOG, PHASE_TIMEOUT = 600, 780


def validator():
    path = ROOT / 'benchmarks/memory_routes_current/validate.py'
    spec = importlib.util.spec_from_file_location('iris_memory_routes_current_validator', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def corpus_cases(corpus):
    validator().admitted(corpus)
    routes = {r['id'] for r in json.loads((ROOT/'hardware/memory-paths.json').read_text())['routes']}
    cases = []
    for c in corpus['cases']:
        active = [h for h in range(3) if c['mask'] & (1 << h)]
        read_bytes = c['n']*8 if c['kind']=='chase' else c['n']*64*8 if c['kind']=='read' else 0
        write_bytes = c['n']*64*8 if c['kind']=='write' else 0
        if c['kernel_read_bytes_per_hart']!=read_bytes or c['kernel_write_bytes_per_hart']!=write_bytes:raise ValueError('Wrong kernel payload accounting')
        if set(c['source_route_ids']) != {f"hart{h}.scalar_data.{c['target_region']}" for h in active} or not set(c['source_route_ids']) <= routes:
            raise ValueError('Unsourced scalar target route')
        cases.append({'id':c['case_id'],'active_harts':active,'region':'kernel','parent_case_id':c['parent_case_id'],
            'semantic_parent_case_id':c['semantic_parent_case_id'],'trial_id':c['trial_id'],'suite':c['suite'],
            'expected_checksums_by_hart':c['expected_checksums']})
    validate_cases(cases,True)
    if sum(len(c['active_harts']) for c in cases) != 2592: raise ValueError('Complete all-mask coverage required')
    return cases


def check_readback(elf,layout,corpus):
    if (layout.get('schema')!='iris.buffered_campaign_readback_layout.v1' or layout.get('elf_sha256')!=digest(elf)
        or layout.get('record_bytes')!=64 or layout.get('records')!=2592 or layout.get('fields')!=
        ['case_index','hart','start','end','instret','checksum','expected','pass']
        or layout.get('stop_sentinel_initial_value')!=(1<<64)-1 or layout.get('stop_sentinel_complete_value')!=0
        or layout.get('file_backed_initial_sentinel_verified') is not True
        or layout.get('intentional_debugger_stop_is_normal_guest_exit') is not False):
        raise ValueError('Wrong exact known-sentinel/readback geometry')
    return validator().check_elf(elf,corpus,layout)


def admit(build,expected_ready):
    build=Path(build).resolve()
    if digest(build/'ready.json')!=expected_ready:raise ValueError('Ready packet changed')
    ready=json.loads((build/'ready.json').read_text());corpus=json.loads((build/'corpus.json').read_text());cases=corpus_cases(corpus);elf=build/'memory-routes.elf'
    if (ready.get('schema')!='iris.memory_routes_current_ready.v1' or ready.get('fitting_only')is not True
        or ready.get('global_heldout')is not False or ready.get('elf_sha256')!=digest(elf)
        or ready.get('corpus_sha256')!=digest(build/'corpus.json')or ready.get('required_cases')!=1512
        or ready.get('required_regions')!=2592 or ready.get('trials')!=3):raise ValueError('Wrong current fitting packet')
    check_readback(elf,json.loads((build/'readback-layout.json').read_text()),corpus)
    identities={str(build/n):digest(build/n)for n in ('ready.json','build.json','corpus.json','qualification.json','readback-layout.json','split.json','independent-review.json')}
    for n,k in [('build.json','build_sha256'),('qualification.json','qualification_sha256'),('readback-layout.json','readback_layout_sha256')]:
        if digest(build/n)!=ready.get(k):raise ValueError('Changed readiness evidence '+n)
    built=json.loads((build/'build.json').read_text())
    if (not built.get('pass')or built.get('elf_sha256')!=digest(elf)or built.get('bss_bytes',1<<30)>262144
        or built.get('kernel_preparation_and_measured_window_source_unchanged')is not True
        or built.get('compiled_kernel_byteidentical_original')is not True):raise ValueError('Exact kernel/source/storage proof required')
    for name,wanted in built['input_sha256'].items():
        if digest(build/'inputs'/wanted)!=wanted:raise ValueError('Changed archived build source')
    merge_inputs(identities,built['input_sha256'])
    qualification=json.loads((build/'qualification.json').read_text());negative=qualification.get('negative_controls',[])
    if qualification.get('pass')is not True or qualification.get('elf_sha256')!=digest(elf)or len(negative)!=15 or any(x.get('rejected')is not True for x in negative):raise ValueError('Actual functional/corruption evidence required')
    merge_inputs(identities,qualification['input_sha256'])
    review=Path(ready['independent_prelaunch_review']).resolve()
    if digest(review)!=ready['independent_prelaunch_review_sha256']:raise ValueError('Changed independent review')
    reviewed=json.loads(review.read_text())
    if (reviewed.get('schema')!='iris.memory_routes_current_independent_review.v1'or reviewed.get('pass')is not True
        or reviewed.get('elf_sha256')!=digest(elf)or reviewed.get('corpus_sha256')!=digest(build/'corpus.json')
        or reviewed.get('split_sha256')!=digest(build/'split.json')or any(reviewed.get(k)is not True for k in
        ('kernel_preparation_window_source_equal','compiled_kernel_byteidentical_original','compiled_table_identity_order_verified','independent_goldens_verified','all_targets_and_masks_checked'))):raise ValueError('Independent source/table/golden review required')
    merge_inputs(identities,reviewed['input_sha256']);identities[str(review)]=digest(review)
    for seed in (0,17):
        folder=build/f'seed{seed}';r=json.loads((folder/'run.json').read_text())
        if r.get('schema')!='iris.memory_routes_current_functional.v1'or r.get('pass')is not True or r.get('exit_status')!=0 or r.get('seed')!=seed or r['argv'][-1]!=str(elf)or '-p3'not in r['argv']or '--iris-schedule-seed='+str(seed)not in r['argv']:raise ValueError('Both exact three-hart normal-exit functional schedules required')
        for suffix in ('stdout','stderr'):
            if digest(folder/('run.'+suffix))!=r[suffix+'_sha256']:raise ValueError('Changed functional output')
        validator().validate((folder/'run.stdout').read_text(),corpus)
        merge_inputs(identities,r['input_sha256']);merge_inputs(identities,{str(folder/n):digest(folder/n)for n in ('run.json','run.stdout','run.stderr')})
    identities[str(elf)]=digest(elf)
    for name,wanted in identities.items():
        if digest(name)!=wanted:raise ValueError('Changed admitted input '+name)
    return ready,corpus,cases,elf,identities


def freeze(args):
    import yaml
    build, output = args.build.resolve(), args.output.resolve()
    ready, corpus, cases, elf, identities = admit(build, args.expected_ready_sha256)
    authorization = args.authorization_receipt.resolve(); receipt = json.loads(authorization.read_text())
    if receipt.get('schema') != 'iris.remote_user_launch_authorization_receipt.v1':
        raise ValueError('Actual user launch authorization receipt required')
    controls_path = args.controls.resolve(); controls = json.loads(controls_path.read_text())
    if (controls.get('schema') != 'iris.memory_routes_current_managed_tool_controls.v1'
            or controls.get('pass') is not True or controls.get('unit_admission_tests') != 8
            or controls.get('real_wrong_role_archive', {}).get('rejected') is not True):
        raise ValueError('Actual admission and wrong-reference archive controls required')
    for name, wanted in controls['input_sha256'].items():
        if digest(name) != wanted: raise ValueError('Managed tool controls bind changed input: ' + name)
    merge_inputs(identities, controls['input_sha256']); identities[str(controls_path)] = digest(controls_path)
    if args.validate_only: return {'status': 'local_admission_validated', 'regions': 2592, 'hardware_contacted': False}
    fs = Path('/scratch/eygao/iris-cy/sims/firesim'); deploy = fs / 'deploy'
    manager, manifest = prepare(deploy, output, elf, cases, deploy / 'config_runtime.yaml', deploy / 'config_hwdb.yaml',
        ROOT / 'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT / 'build/firesim-observability-archived-driver-v3/report.json', profile_interval=1000000)
    from memory_observation import freeze as freeze_memory
    freeze_memory(args.memory_probe_build.resolve(), output, manifest); add_observer(manager)
    watchdog = manager / 'iris_workload_watchdog.py'; text = watchdog.read_text()
    if text.count('SECONDS=1500') != 1: raise ValueError('Reviewed watchdog changed')
    watchdog.write_text(text.replace('SECONDS=1500', 'SECONDS=' + str(WATCHDOG), 1))
    runtime_path = manager / 'config_runtime.yaml'; runtime = yaml.safe_load(runtime_path.read_text())
    previous = runtime['target_config'].get('plusarg_passthrough', '')
    if '+max-cycles' in previous or '+fesvr-step-size' in previous: raise ValueError('Conflicting loader/cycle bound')
    runtime['target_config']['plusarg_passthrough'] = (previous + ' +fesvr-step-size=128').strip()
    runtime_path.write_text(yaml.safe_dump(runtime, sort_keys=False))
    for name in ('corpus.json', 'ready.json', 'build.json', 'qualification.json', 'readback-layout.json', 'split.json', 'independent-review.json'):
        (output / name).write_bytes((build / name).read_bytes())
    (output / 'cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    (output / 'launch-authorization.json').write_bytes(authorization.read_bytes())
    checklist = {'schema': 'iris.memory_routes_current_capture_checklist.v1', 'frozen_before_launch': True,
        'fitting_only': True, 'global_heldout': False, 'cases': 1512, 'semantic_parents': 252, 'trials': 3,
        'expected_regions': 2592, 'remote_wall_watchdog_seconds': WATCHDOG, 'host_phase_timeout_seconds': PHASE_TIMEOUT,
        'old_campaign_timings_applicable': False, 'new_exact_ELF_reference_required': True,
        'memory_bank_scope':'TCM/scratch bit6 geometry only; no DRAM bank identification; warm preparation only',
        'required': ['All region mcycle/minstret/checksums, failure/terminal records and repeat identity',
            'Raw manager/stdout/stderr/UART/heartbeat/FASED, exact configs/plusargs and all source/ELF/toolchain/image/driver digests',
            'Complete four-phase managed lifecycle with full occupancy/ownership/lock checks and owned cleanup before external capture'],
        'unavailable_instrumentation': ['TracerV', 'AutoCounter', 'SynthPrint'],
        'source_image_association_verified': False, 'timing_accuracy_certified': False}
    (output / 'capture-checklist.json').write_text(json.dumps(checklist, indent=2) + '\n')
    sources = [Path(__file__).resolve(), ROOT / 'firesim/analyze_memory_routes_current.py', ROOT / 'firesim/analyze_campaign.py',
        ROOT / 'firesim/prepare_buffered_priority.py', ROOT / 'firesim/prepare_managed_campaign.py', ROOT / 'firesim/run_prepared.py',
        ROOT / 'firesim/workload_watchdog.py', ROOT / 'firesim/setup_phase_observer.py', ROOT / 'firesim/managed_programming_tools.py',
        ROOT / 'benchmarks/memory_routes_current/validate.py', ROOT / 'benchmarks/campaign_buffered/validate_priority.py',
        ROOT / 'firesim/test_memory_routes_current.py', controls_path, authorization,
        ROOT / 'build/xilinx-tool-paths-v1.json', fs / 'sourceme-manager.sh', fs / 'env.sh', fs.parent.parent / 'env.sh']
    merge_inputs(identities, {str(p): digest(p) for p in sources}); merge_inputs(manifest['input_sha256'], identities)
    snapshot_inputs(output, manifest['input_sha256'])
    manifest.update(campaign_role=ROLE, require_regions=True, require_goldens=True, expected_regions=2592,
        fitting_only=True, global_heldout=False, launch_authorization_receipt=receipt,
        corpus_sha256=digest(output / 'corpus.json'), ready_sha256=args.expected_ready_sha256,
        old_campaign_timings_applicable=False, new_exact_ELF_reference_required=True,
        calibration_usable=False, timing_accuracy_certified=False, hardware_source_association_verified=False,
        prepared_manager_sha256=digest(manager / 'firesim'), prepared_runtime_sha256=digest(runtime_path),
        frozen_capture_checklist_sha256=digest(output / 'capture-checklist.json'),
        loader_override={'fesvr_step_size_target_cycles': 128, 'target_cycle_bound': None,
            'target_cycle_bound_omission_reason': NO_TARGET_BOUND, 'remote_wall_watchdog_seconds': WATCHDOG,
            'foreground': True, 'driver_binary_unchanged': True})
    launch = ['#!/usr/bin/env bash', 'export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH',
        'cd ' + shlex.quote(str(fs)) + ' || exit 1',
        'source ./sourceme-manager.sh --skip-ssh-setup > ' + shlex.quote(str(output / 'launch-environment.stdout')) +
            ' 2> ' + shlex.quote(str(output / 'launch-environment.stderr')),
        'exec ' + shlex.join(['/scratch/eygao/iris-cy/.conda-env/bin/python3', str(ROOT / 'firesim/run_prepared.py'),
            str(output), '--execute', '--authorization-id', receipt['authorization']['authorization_id'], '--timeout', str(PHASE_TIMEOUT)])]
    (output / 'launch.sh').write_text('\n'.join(launch) + '\n'); (output / 'launch.sh').chmod(0o700)
    manifest['prepared_file_sha256'] = {str(p.relative_to(output)): digest(p) for p in output.rglob('*')
        if p.is_file() and p.name != 'run.json' and not p.is_symlink()
        and not any(parent.is_symlink() for parent in p.parents if parent != output)}
    save_manifest(output, manifest); verify(output)
    return {'status': manifest['status'], 'regions': 2592, 'hardware_contacted': False, 'job': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--build', type=Path, default=ROOT / 'build/memory-routes-current-v1')
    parser.add_argument('--expected-ready-sha256', required=True)
    parser.add_argument('--authorization-receipt', type=Path, required=True)
    parser.add_argument('--memory-probe-build', type=Path, default=ROOT / 'build/fased-readonly-managed-v2')
    parser.add_argument('--controls', type=Path, default=ROOT / 'build/memory-routes-current-tools-controls-v1/report.json')
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--validate-only', action='store_true')
    print(json.dumps(freeze(parser.parse_args())))
