#!/usr/bin/env python3
"""Execute the frozen candidate normally on the exact original native/ELF."""
import argparse
import datetime
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from compare_wfi_footprints_v2 import ROOT,inventory,load,sha

def main(candidate,output):
    base=ROOT/'build/memory-footprints-WFI-groups-hybrid7bd5-selected-v1';parent=load(base/'run.json')
    fit=load(candidate/'report.json');inventory(fit['input_sha256'])
    if fit['pass']is not True or sha(candidate/'runtime.fixture')!=fit['fixture_sha256']:raise ValueError('Unfrozen fit')
    output.mkdir(parents=True,exist_ok=False);argv=list(parent['argv'])
    argv=[('--iris-timing-fixture='+str(candidate/'runtime.fixture'))if a.startswith('--iris-timing-fixture=')else('--iris-timing-trace='+str(output/'native-summary.json'))if a.startswith('--iris-timing-trace=')else a for a in argv]
    inputs=dict(parent['input_sha256']);inputs.update({str(p):sha(p)for p in [Path(__file__).resolve(),candidate/'report.json',candidate/'parameters.json',candidate/'runtime.fixture']});inventory(inputs)
    env=dict(os.environ);env.pop('IRIS_EMPIRICAL_ASYNC_TRACE',None);env['IRIS_EMPIRICAL_FEATURES']=str(output/'features.jsonl')
    report={'schema':'iris.empirical_ELF_execution.v1','status':'running','pass':False,'candidate_only':True,'timing_accuracy_certified':False,
        'started_at_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hardware_contacted':False,'argv':argv,
        'ELF_sha256':parent['ELF_sha256'],'fixture_sha256':fit['fixture_sha256'],'input_sha256':inputs,'timeout_seconds':900,
        'calibration_identity':'iris-empirical-WFI-TRAIN-L2-hit-v1','physical_harts':3,'native_or_ISA_changed':False}
    def save():(output/'run.json').write_text(json.dumps(report,indent=2)+'\n')
    save();start=time.monotonic();process=None
    try:
        with(output/'stdout').open('wb')as stdout,(output/'stderr').open('wb')as stderr:
            process=subprocess.Popen(argv,env=env,stdout=stdout,stderr=stderr,start_new_session=True);report['pid']=process.pid;save();timed=False
            try:code=process.wait(timeout=900)
            except subprocess.TimeoutExpired:
                timed=True;os.killpg(process.pid,signal.SIGTERM)
                try:code=process.wait(timeout=.2)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait()
        inventory(inputs);report.update(exit_status=code,timed_out=timed,status='passed_guest_exit'if code==0 and not timed else'failed_guest_exit',**{'pass':code==0 and not timed})
    finally:
        if process is not None and process.poll()is None:os.killpg(process.pid,signal.SIGKILL);process.wait()
        report['host_seconds']=time.monotonic()-start;report['output_sha256']={str(p):sha(p)for p in [output/n for n in('stdout','stderr','features.jsonl','native-summary.json')]if p.is_file()};save()
    print(json.dumps({k:report.get(k)for k in('pass','status','host_seconds','exit_status')}))
if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.candidate.resolve(),a.output.resolve())
