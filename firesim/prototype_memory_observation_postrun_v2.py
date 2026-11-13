#!/usr/bin/env python3
"""Qualify local five-register hook installation; deliberately forbid execution."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import batch_runner as batch
import memory_observation_postrun_v2 as post
import run_prepared
from audit_fased_config_v2 import audit

ROOT=Path(__file__).resolve().parents[1]
FS=Path('/scratch/eygao/iris-cy/sims/firesim')


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    post.need(not out.exists(),'New prototype output required');out.mkdir(parents=True)
    checked=audit();(out/'binary-MMIO-audit.json').write_text(json.dumps(checked,indent=2)+'\n')
    test_argv=[sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'firesim/tests'),'-p','test_memory_observation_postrun_v2.py','-v']
    r=subprocess.run(test_argv,cwd=ROOT,capture_output=True,timeout=60)
    (out/'tests.stdout').write_bytes(r.stdout);(out/'tests.stderr').write_bytes(r.stderr)
    post.need(r.returncode==0,'New safety/refusal tests failed')
    deploy=FS/'deploy';build=ROOT/'build/rvv-compute-asm-v5';job=out/'job'
    cases=json.loads((build/'host-cases.json').read_text())
    manager,m=batch.prepare(deploy,job,build/'guest.elf',cases,deploy/'config_runtime.yaml',deploy/'config_hwdb.yaml',
        ROOT/'firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz',
        observability_report=ROOT/'build/firesim-observability-archived-driver-v3/report.json')
    auth=ROOT/'build/user-launch-authorization-focused-continuation-v1/receipt.json'
    m.update(require_regions=True,require_goldens=True,launch_authorization_receipt=json.loads(auth.read_text()),prototype_only=True)
    m['input_sha256'][str(auth)]=post.digest(auth);batch.save_manifest(job,m)
    (out/'before-install-manifest.json').write_bytes((job/'run.json').read_bytes())
    installed=post.install(job,post.digest(job/'run.json'),ROOT/'build/fased-readonly-extended-v2','sohumpc',prototype_only=True)
    run_prepared.verify(job)
    m=json.loads((job/'run.json').read_text());m.update(status='prototype_only_not_for_execution',prototype_hardware_admission=False)
    batch.save_manifest(job,m)
    refused=False
    try:run_prepared.verify(job)
    except ValueError:refused=True
    post.need(refused,'Prototype must refuse before hardware execution')
    (out/'installation.json').write_text(json.dumps(installed,indent=2)+'\n')
    old=ROOT/'build/fased-postrun-hook-prototype-v1/report.json';old_report=json.loads(old.read_text())
    post.need(all(post.digest(p)==h for p,h in old_report['input_sha256'].items()),'Frozen v1 input changed')
    reader=ROOT/'build/fased-readonly-extended-v2/report.json';reader_report=json.loads(reader.read_text())
    paths=[Path(__file__),ROOT/'firesim/memory_observation_postrun_v2.py',ROOT/'firesim/memory_observation_extended_v2.py',
        ROOT/'firesim/audit_fased_config_v2.py',ROOT/'firesim/build_memory_observer_v2.py',ROOT/'firesim/readonly_fased_config_v2.c',
        ROOT/'firesim/tests/test_memory_observation_postrun_v2.py',ROOT/'firesim/MEMORY_OBSERVATION_POSTRUN_V2.md',
        ROOT/'build/fased-config-MMIO-audit-v2/report.json',reader,old,
        ROOT/'firesim/batch_runner.py',ROOT/'firesim/memory_observation.py',ROOT/'firesim/memory_observation_postrun.py']
    report={'schema':'iris.postdriver_fased_observer_local_qualification.v2','pass':True,
        'mocked_tests':14,'mocked_test_argv':test_argv,'independent_binary_checks':len(checked['compiled_binary_checks']),
        'reader_fake_controls':len(reader_report['fake_controls']),'reader_strace_no_write':reader_report['strace_no_write'],
        'reader_binary_sha256':reader_report['binary_sha256'],'five_registers':post.original.REGISTER_MAP,
        'prototype_prepared_closure_verified':True,'prototype_execution_refusal_verified':True,
        'prototype_job':str(job),'prototype_final_manifest_sha256':post.digest(job/'run.json'),'installation':installed,
        'all_v1_inputs_still_match_frozen_receipt':True,'actual_postdriver_read_performed':False,
        'hardware_contacted':False,'privileged_installation_performed':False,'runner_or_source_package_modified':False,
        'ready_for_root_review':True,'calibration_usable':False,'source_image_association_verified':False,
        'input_sha256':{str(p):post.digest(p)for p in paths},
        'report_artifact_sha256':{str(p.relative_to(out)):post.digest(p)for p in out.iterdir()if p.is_file()}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'report_sha256':post.digest(out/'report.json'),'prototype_execution_refused':True,'hardware_contacted':False}))


if __name__=='__main__':main()
