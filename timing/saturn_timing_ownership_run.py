#!/usr/bin/env python3
"""Finite same-clock whole-RTL activity plus ownership sidecar capture."""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
BASE=R/'build/saturn-timing-activity-component-v1-final'
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as stream:
  for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--observer',type=Path,required=True);p.add_argument('--case',choices=['vme','rvv','fpcomp','shared-fpu'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'runner.py');observer=a.observer.resolve();old=BASE/'build/saturn-timing-activity-capture-v1'/a.case/'report.json';receipt=json.loads(old.read_text());command=receipt['argv'][:];command[0]=str(observer/'simulator-ownership');command=[arg for arg in command if not arg.startswith(('+signature=','+iris-activity='))];command.insert(command.index('+permissive-off'),'+iris-activity='+str(out/'activity.bin.gz'));command.insert(command.index('+permissive-off'),'+iris-ownership='+str(out/'ownership.bin.gz'));command.insert(-1,'+signature='+str(out/'guest.signature'));start=time.monotonic()
 with(out/'stdout').open('w')as stdout,(out/'stderr').open('w')as stderr:
  try:q=subprocess.run(command,stdout=stdout,stderr=stderr,cwd=R,timeout=600);code=q.returncode;timed=False
  except subprocess.TimeoutExpired:code=None;timed=True
 inputs=[Path(__file__),BASE/'report.json',old,observer/'build.json',observer/'simulator-ownership',Path(command[-1])];result={'schema':'iris.saturn_ownership_actual_whole_RTL_run.v1','case':a.case,'argv':command,'exit_status':code,'timed_out':timed,'host_seconds':time.monotonic()-start,'input_sha256':{str(p):sha(p)for p in inputs},'source_RTL_logic_or_objects_modified':False,'physical_or_internal_state_driven':False,'hardware_contacted':False};result['artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()};result['same_architectural_signature_as_frozen_activity_run']=(out/'guest.signature').is_file()and sha(out/'guest.signature')==sha(BASE/'build/saturn-timing-activity-capture-v1'/a.case/'guest.signature');(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'case':a.case,'exit_status':code,'host_seconds':result['host_seconds'],'same_architectural_signature':result['same_architectural_signature_as_frozen_activity_run'],'report_sha256':sha(out/'report.json')}))
 if code!=0 or timed or not result['same_architectural_signature_as_frozen_activity_run']:raise SystemExit(1)
if __name__=='__main__':main()
