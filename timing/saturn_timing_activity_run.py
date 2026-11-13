#!/usr/bin/env python3
"""Finite independent whole-RTL activity capture with explicit binary provenance."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

R=Path(__file__).resolve().parents[1]
REFERENCE=R/'build/saturn-timing-component-v1-final'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--observer',type=Path,required=True)
    parser.add_argument('--case',choices=['vme','rvv','fpcomp','shared-fpu'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();observer=args.observer.resolve();out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    old=json.loads((REFERENCE/'build/saturn-timing-rtl-v1'/(args.case+'.json')).read_text())
    original=Path(old['argv'][-1]);entry=next(x for x in json.loads((REFERENCE/'report.json').read_text())['artifacts']if x['source_path']==str(original))
    elf=REFERENCE/entry['path'];assert sha(elf)==old['elf_sha256']
    command=old['argv'][:];command[0]=str(observer/'simulator-activity');command[-1]=str(elf)
    command=[x for x in command if not x.startswith('+signature')]
    command.insert(command.index('+permissive-off'),'+iris-activity='+str(out/'activity.bin.gz'))
    command.insert(-1,'+signature='+str(out/'guest.signature'))
    command.insert(-1,'+signature-granularity=8')
    start=time.monotonic()
    with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
        try:q=subprocess.run(command,cwd=R,stdout=stdout,stderr=stderr,timeout=600);code=q.returncode;timed=False
        except subprocess.TimeoutExpired:code=None;timed=True
    report={'schema':'iris.saturn_activity_actual_whole_rtl_run.v1','case':args.case,
            'argv':command,'exit_status':code,'timed_out':timed,
            'host_seconds':time.monotonic()-start,
            'input_sha256':{str(p):sha(p)for p in[Path(__file__),observer/'build.json',elf,observer/'simulator-activity',REFERENCE/'report.json']},
            'source_RTL_logic_modified':False,'hardware_contacted':False,
            'loaded_FPGA_image_or_whole_timing_certified':False}
    report['artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()}
    if(out/'guest.signature').is_file():
        report['same_architectural_signature_as_frozen_guest']=sha(out/'guest.signature')==old['signature_sha256']
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'case':args.case,'exit_status':code,'timed_out':timed,
                      'host_seconds':report['host_seconds'],
                      'same_signature':report.get('same_architectural_signature_as_frozen_guest'),
                      'report_sha256':sha(out/'report.json')}))
    if code!=0 or timed:raise SystemExit(1)

if __name__=='__main__':main()
