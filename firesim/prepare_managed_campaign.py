#!/usr/bin/env python3
"""Freeze smoke then broad fitting jobs locally; never contacts the FPGA."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.export_cases import export
from batch_runner import digest, prepare, save_manifest, validate_cases
from run_prepared import verify


def snapshot_inputs(job, identities):
    target = job / 'prepared-inputs'
    target.mkdir()
    for name, expected in sorted(identities.items()):
        source = Path(name)
        if digest(source) != expected:
            raise ValueError('Preparation input changed: ' + name)
        destination = target / expected
        if not destination.exists():
            shutil.copyfile(source, destination)
        if digest(destination) != expected:
            raise ValueError('Preparation snapshot changed: ' + name)


def add_observer(manager):
    observer = Path(__file__).with_name('setup_phase_observer.py')
    shutil.copyfile(observer, manager / 'iris_setup_observer.py')
    shutil.copyfile(Path(__file__).with_name('managed_programming_tools.py'),manager/'iris_managed_programming_tools.py')
    shutil.copyfile(Path(__file__).with_name('workload_watchdog.py'),manager/'iris_workload_watchdog.py')
    front = manager / 'firesim'
    text = front.read_text()
    anchor = 'from runtools.runtime_config import RuntimeConfig\n'
    if text.count(anchor) != 1:
        raise ValueError('Manager observer import contract changed')
    text = text.replace(anchor, anchor + '\nfrom iris_managed_programming_tools import install as _iris_install_programming_tools\n_iris_install_programming_tools()\nfrom iris_setup_observer import install as _iris_install_setup_observer\n_iris_install_setup_observer()\nfrom iris_workload_watchdog import install as _iris_install_workload_watchdog\n_iris_install_workload_watchdog()\n', 1)
    compile(text, str(front), 'exec')
    front.write_text(text)
    return observer


def prepare_campaign(output, deploy, driver, observability, authorization=None, fesvr_step_size=None):
    output.mkdir(parents=True, exist_ok=False)
    audit = json.loads(observability.read_text())
    if audit.get('driver_policy', {}).get('has_host_mem') is not False:
        raise ValueError('This campaign requires the reviewed original archived driver')
    jobs = []
    for name, elf, corpus_path, build_path, smoke in [
        ('smoke', ROOT / 'benchmarks/build/smoke.elf', ROOT / 'benchmarks/calibration-corpus.json', ROOT / 'benchmarks/build/build.json', True),
        ('broad-fit', ROOT / 'build/campaign-fit-v1/campaign.elf', ROOT / 'build/campaign-fit-v1/corpus.json', ROOT / 'build/campaign-fit-v1/build.json', False),
    ]:
        corpus, build = json.loads(corpus_path.read_text()), json.loads(build_path.read_text())
        rows = export(corpus, smoke=smoke)
        for row in rows:
            row['corpus_sha256'] = digest(corpus_path)
        if not smoke:
            by_id = {row['case_id']: row for row in corpus['cases']}
            for row in rows:
                row.update({key: by_id[row['id']][key] for key in ('parent_case_id', 'trial_id', 'suite', 'mask')})
            if digest(elf) != build['elf_sha256']:
                raise ValueError('Broad ELF changed')
        else:
            candidates = [a for a in build['artifacts'] if a['name'] == 'smoke']
            if len(candidates) != 1 or digest(elf) != candidates[0]['sha256']:
                raise ValueError('Smoke ELF changed')
        validate_cases(rows, True)
        job = output / name
        manager, manifest = prepare(deploy, job, elf, rows, deploy / 'config_runtime.yaml',
                                    deploy / 'config_hwdb.yaml', driver,
                                    observability_report=observability, profile_interval=1000000)
        observer = add_observer(manager)
        if fesvr_step_size is not None:
            import yaml
            if type(fesvr_step_size)is not int or fesvr_step_size<128:raise ValueError('Source reset-safe FESVR quantum128or larger required')
            runtime_path=manager/'config_runtime.yaml';runtime=yaml.safe_load(runtime_path.read_text())
            original=runtime['target_config'].get('plusarg_passthrough','')
            if '+fesvr-step-size' in original or '+max-cycles' in original:raise ValueError('Conflicting manual loader/cycle bound')
            runtime['target_config']['plusarg_passthrough']=(original+' +fesvr-step-size='+str(fesvr_step_size)).strip()
            runtime_path.write_text(yaml.safe_dump(runtime,sort_keys=False));manifest['prepared_runtime_sha256']=digest(runtime_path)
            manifest['loader_override']={'fesvr_step_size_target_cycles':fesvr_step_size,'driver_default':2004765,
                'target_cycle_bound':None,'remote_wall_watchdog_seconds':1500,
                'remote_wall_watchdog_foreground':True,
                'cycle_bound_unavailable_reason':'Exact archived systematic_scheduler parses max-cycles with signed32 atoi; large bounds overflow',
                'scope':'Host-FESVR polling quantum; clock/memory timing unchanged',
                'reference_driver_unchanged':True,'affects_reference_fingerprint':True}
        sources = [Path(__file__), observer, Path(__file__).with_name('analyze_campaign.py'),
                   Path(__file__).with_name('managed_programming_tools.py'),
                   Path(__file__).with_name('workload_watchdog.py'),
                   Path(__file__).with_name('run_campaign.py'), Path(__file__).with_name('run_prepared.py'),
                   corpus_path, build_path, ROOT / 'benchmarks/campaign/capture-checklist.json',
                   ROOT / 'benchmarks/campaign/validate.py', ROOT / 'benchmarks/validate_console.py',
                   ROOT / 'hardware/manifest.json', ROOT / 'hardware/dtypes.json',
                   ROOT / 'hardware/memory-paths.json', ROOT / 'firesim/artifacts/archived-build-driver-v1/manifest.json',
                   ROOT / 'build/campaign-fit-v1-closure-v2/report.json']
        sources.append(ROOT/'build/xilinx-tool-paths-v1.json')
        if fesvr_step_size is not None:
            sources.append(Path('/scratch/eygao/iris-cy/generators/firechip/bridgestubs/src/main/cc/bridges/tsibridge.cc'))
            sources.append(Path('/scratch/eygao/iris-cy/sims/firesim/sim/midas/src/main/cc/core/systematic_scheduler.cc'))
        identities = dict(build['input_sha256'])
        if smoke:
            identities[build['compiler']] = build['compiler_sha256']
        identities.update({str(p): digest(p) for p in sources})
        if authorization is not None:
            authorization=Path(authorization).resolve()
            receipt=json.loads(authorization.read_text())
            if receipt.get('schema')!='iris.remote_user_launch_authorization_receipt.v1':
                raise ValueError('Reviewed user launch authorization receipt required')
            manifest['launch_authorization_receipt']=receipt
            identities[str(authorization)]=digest(authorization)
            (job/'launch-authorization.json').write_bytes(authorization.read_bytes())
        manifest['input_sha256'].update(identities)
        snapshot_inputs(job, manifest['input_sha256'])
        (job / 'cases.json').write_text(json.dumps(rows, indent=2) + '\n')
        (job / 'corpus.json').write_bytes(corpus_path.read_bytes())
        checklist = json.loads((ROOT / 'benchmarks/campaign/capture-checklist.json').read_text())
        checklist.update(job=name, source_template_sha256=digest(ROOT / 'benchmarks/campaign/capture-checklist.json'),
                         cases=len(rows), total_regions=sum(len(r['active_harts']) for r in rows),
                         selected_elf_sha256=digest(elf), image=manifest['image'], driver=manifest['driver'],
                         observability_report_sha256=digest(observability),
                         instrumentation_before_launch=audit, calibration_usable=False,
                         host_setup_observer={'source_sha256': digest(observer),
                             'output': 'IRIS_HOST_PHASE JSON in manager DEBUG logs (or per-phase stdout when forwarded)',
                             'boundaries': 'rsync commands, exact installed programming helper, nested setup methods',
                             'clock_or_memory_parameters_changed': False},
                         post_run_analysis='run_campaign.py invokes archive-bound analysis after run_prepared returns on both success/failure')
        if smoke:
            checklist.update(parent_cases=len(rows), trials=1, phase_markers=0,
                             per_hart_regions=[sum(h in r['active_harts'] for r in rows) for h in range(3)],
                             completion='One successful IRIS_BATCH_DONE; baseline smoke validator',
                             required_guest_capture=['Raw UART; all 12 regions with mcycle/minstret/checksums; final completion/fatal output'])
        (job / 'capture-checklist.json').write_text(json.dumps(checklist, indent=2) + '\n')
        manifest.update(require_regions=True, require_goldens=True, calibration_usable=False,
                        corpus_sha256=digest(corpus_path), campaign_role='smoke' if smoke else 'fitting',
                        hardware_source_association_verified=False,
                        frozen_capture_checklist_sha256=digest(job / 'capture-checklist.json'),
                        post_validation_required='archive-bound analyze_campaign.py via run_campaign.py',
                        source_snapshots='prepared-inputs/<sha256>; exact referenced bytes, not a source/image attestation',
                        setup_phase_observer_sha256=digest(observer), prepared_manager_sha256=digest(manager / 'firesim'))
        manifest['prepared_file_sha256'] = {str(p.relative_to(job)): digest(p) for p in sorted(job.rglob('*'))
            if p.is_file() and p.name != 'run.json' and not p.is_symlink()
            and not any(parent.is_symlink() for parent in p.parents if parent != job)}
        save_manifest(job, manifest)
        verify(job)
        jobs.append({'name': name, 'job': str(job), 'cases': len(rows),
                     'expected_regions': sum(len(r['active_harts']) for r in rows),
                     'elf_sha256': manifest['elf_sha256'], 'run_receipt_sha256': digest(job / 'run.json'),
                     'capture_checklist_sha256': manifest['frozen_capture_checklist_sha256']})
    campaign = {'schema': 'iris.managed_batched_campaign.v1', 'status': 'prepared_not_executed',
                'jobs': jobs, 'order': ['smoke', 'broad-fit'], 'broad_requires_smoke_success': True,
                'generator_sha256': digest(Path(__file__)), 'hardware_contacted': False,
                'hardware_launch_permitted': False, 'calibration_usable': False,
                'heldout_timing_consumed': False,
                'prerequisites': ['Installed exact reviewed protected inspector',
                    'Current explicit user authorization receipt, complete idle inspection and held shared group lock',
                    'Source FireSim manager environment; execute only through run_campaign.py/run_prepared.py'],
                'launch_argv': ['/scratch/eygao/iris-cy/.conda-env/bin/python3', str(ROOT / 'firesim/run_campaign.py'),
                    str(output / 'campaign.json'), '--execute', '--authorization-id', '<current-user-authorization-id>',
                    '--output', '<fresh-analysis-directory>']}
    (output / 'campaign.json').write_text(json.dumps(campaign, indent=2) + '\n')
    return campaign


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--deploy', type=Path, default=Path('/scratch/eygao/iris-cy/sims/firesim/deploy'))
    parser.add_argument('--driver-tar', type=Path, required=True)
    parser.add_argument('--observability-report', type=Path, required=True)
    parser.add_argument('--authorization-receipt',type=Path)
    parser.add_argument('--fesvr-step-size',type=int)
    args = parser.parse_args()
    report = prepare_campaign(args.output.resolve(), args.deploy.resolve(), args.driver_tar.resolve(), args.observability_report.resolve(),args.authorization_receipt,args.fesvr_step_size)
    print(json.dumps({'status': report['status'], 'jobs': report['jobs'], 'hardware_contacted': False}))


if __name__ == '__main__':
    main()
