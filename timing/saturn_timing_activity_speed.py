#!/usr/bin/env python3
"""Measure active source stepping cost of the frozen activity-capable SDK."""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--capsule',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();capsule=a.capsule.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'checker.py');ref=R/'build/saturn-timing-component-v1-final';fast=R/'build/saturn-timing-fast-component-v1-final';old=fast/'build/saturn-timing-fast-active-v2/report.json';gold=json.loads(old.read_text());sdk=capsule/'build/saturn-timing-activity-sdk-v4/sdk';src=ref/'timing/saturn_timing_bench.cpp';local=out/'benchmark.cpp';shutil.copy2(src,local);command=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(sdk),str(local),str(sdk/'libiris_saturn_timing.a'),'-latomic','-o',str(out/'benchmark')]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 mapping={entry['source_path']:ref/entry['path']for entry in json.loads((ref/'report.json').read_text())['artifacts']};inputs=[Path(__file__),capsule/'report.json',sdk/'libiris_saturn_timing.a',src,old,local,Path('/usr/bin/g++')];rows=[]
 for case,hart in [('vme',0),('rvv',0),('fpcomp',0),('shared-fpu',2)]:
  previous=next(row for row in gold['runs']if row['case']==case and row['hart']==hart);argv=previous['argv'][:];argv[0]=str(out/'benchmark');argv[3]=str(mapping[argv[3]]);argv[4]=str(mapping[argv[4]]);inputs.extend([Path(argv[3]),Path(argv[4])]);start=time.monotonic()
  with(out/(case+'.stdout')).open('w')as stdout,(out/(case+'.stderr')).open('w')as stderr:q=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=240)
  if q.returncode:raise ValueError('Frozen active workload refused '+case)
  fresh=json.loads((out/(case+'.stdout')).read_text())
  for key in ['executed_prefix_edges','timed_active_guest_edges']:
   if fresh[key]!=previous['result'][key]:raise ValueError('Changed active measurement window')
  for observed,expected in zip(fresh['runs'],previous['result']['runs']):
   for key in ['qualified_field_mix64','qualified_words','seed']:
    if observed[key]!=expected[key]:raise ValueError('Changed source-qualified behavior '+case+' '+key)
  rows.append({'case':case,'hart':hart,'argv':argv,'host_seconds_total':time.monotonic()-start,'result':fresh,'earlier_fast_edges_per_second':[r['edges_per_second']for r in previous['result']['runs']]});print(json.dumps({'case':case,'edges_per_second':[r['edges_per_second']for r in fresh['runs']]}),flush=True)
 result={'schema':'iris.saturn_activity_capable_active_speed.v1','runs':rows,'input_sha256':{str(p):sha(p)for p in inputs},'artifact_sha256':{p.name:sha(p)for p in out.iterdir()if p.is_file()},'in_process_stepping':True,'all_prefix_and_active_edges_executed':True,'activity_sampling_projection_and_gzip_not_in_timed_loop':True,'source_debug_formatting_included':True,'source_edges_skipped':0,'SoC_MIPS_or_timing_accuracy_claimed':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
