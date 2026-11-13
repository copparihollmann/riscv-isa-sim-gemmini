#!/usr/bin/env python3
"""Freeze/verify LOCAL readiness evidence; no network or privileged invocation."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identities(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from identities(item)
        else:yield item.id()
def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/managed-path-ready-v1')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();output=args.output.resolve();public=Path(__file__).with_name('release.json')
    if args.verify:
        report=json.loads((output/'report.json').read_text())
        if sha(output/'report.json')!=sha(public):raise ValueError('Public release/report mismatch')
        for name,value in report['input_sha256'].items():
            if sha(Path(name))!=value:raise ValueError('Current source changed: '+name)
        for name,value in report['artifact_sha256'].items():
            if sha(output/name)!=value:raise ValueError('Archived evidence changed: '+name)
        print(json.dumps({'status':'verified','report':str(output/'report.json'),'report_sha256':sha(output/'report.json'),
            'test_count':report['tests']['run'],'hardware_contacted':False}));return
    output.mkdir(parents=True,exist_ok=False)
    suite=unittest.defaultTestLoader.discover(str(ROOT/'firesim/tests'))
    cases=list(identities(suite))
    if len(cases)!=len(set(cases)):raise ValueError('Duplicate test identity')
    with (output/'tests.log').open('w') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    if not result.wasSuccessful():raise ValueError('Local tests failed; preserve output')
    paths=[ROOT/'AGENTS.md',ROOT.parent/'AGENTS.md',ROOT/'firesim/OPERATING_RULES.md',
        ROOT/'firesim/batch_runner.py',ROOT/'firesim/prepare_campaign.py',ROOT/'firesim/run_prepared.py',
        ROOT/'firesim/capture_run.py',ROOT/'firesim/CAMPAIGN_POLICY.md',ROOT/'firesim/inspect_instrumentation.py',
        ROOT/'build/firesim-observability-candidate-v2/report.json']
    paths += sorted((ROOT/'firesim/tests').glob('test_*.py'))
    paths += [path for path in Path(__file__).parent.iterdir() if path.is_file() and path.name!='release.json']
    audit=json.loads((ROOT/'firesim/operator/managed-path-audit.json').read_text())
    paths += [Path(name) for name in audit['input_sha256']]
    inputs={str(path.resolve()):sha(path) for path in paths}
    for name,value in audit['input_sha256'].items():
        if inputs[str(Path(name).resolve())]!=value:raise ValueError('Privilege audit input changed: '+name)
    snapshots=[]
    for index,(name,value)in enumerate(sorted(inputs.items())):
        target=output/'sources'/(str(index).zfill(3)+'-'+Path(name).name)
        target.parent.mkdir(exist_ok=True);shutil.copyfile(name,target)
        if sha(target)!=value:raise ValueError('Input changed while copying: '+name)
        snapshots.append({'source':name,'artifact':str(target.relative_to(output)),'sha256':value})
    report={'schema':'iris.local_managed_path_readiness.v1','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status':'local_tests_pass_operator_actions_still_required','hardware_contacted':False,'remote_installed':False,
        'inspection_complete_on_fpga_host':False,'operator_allocation_confirmed':False,'hardware_launch_permitted':False,
        'loaded_image_verified':False,'driver_image_build_association_verified':False,'calibration_usable':False,
        'inspector_version':'iris-fpga-inspection-v1','inspector_sha256':sha(ROOT/'firesim/operator/firesim-iris-inspect'),
        'runner_sha256':sha(ROOT/'firesim/batch_runner.py'),'prepare_campaign_sha256':sha(ROOT/'firesim/prepare_campaign.py'),
        'python':{'executable':sys.executable,'version':sys.version},
        'tests':{'run':result.testsRun,'unique_case_ids':cases,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)},
        'api':{'prepare':'prepare(..., observability_report=Path(...), profile_interval=1000000)',
            'profile_interval_target_cycles':1000000,'observability_report':'build/firesim-observability-candidate-v2/report.json',
            'candidate_observability_sha256':sha(ROOT/'build/firesim-observability-candidate-v2/report.json')},
        'source_snapshots':snapshots,'input_sha256':inputs,
        'artifact_sha256':{str(path.relative_to(output)):sha(path)for path in output.rglob('*')if path.is_file()},
        'remaining_requirements':audit['remaining_requirements'],
        'scope':'Local synthetic process, actual local transport/capture and mocked managed lifecycle tests. No SSH, root helper execution, device access or hardware lifecycle.'}
    text=json.dumps(report,indent=2)+'\n';(output/'report.json').write_text(text);public.write_text(text)
    print(output/'report.json')
if __name__=='__main__':main()
