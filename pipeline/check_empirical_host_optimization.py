#!/usr/bin/env python3
"""Exact executed-ELF equivalence for host-only timing-engine optimizations."""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
 reports=[]
 for original in sorted((ROOT/'build/empirical-fadd-async-proof-v3').glob('*/report.json')):
  if '-functional'in original.parent.name:continue
  source=json.loads(original.read_text());o=out/original.parent.name;o.mkdir();argv=source['argv'][:];argv[0]=str(a.candidate.resolve());argv=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else'--iris-timing-trace='+str(o/'summary.json')if x.startswith('--iris-timing-trace=')else x for x in argv]
  env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(o/'async.jsonl'),IRIS_EMPIRICAL_FEATURES=str(o/'features.jsonl'));t=time.monotonic();got=subprocess.run(argv,env=env,capture_output=True,timeout=90);elapsed=time.monotonic()-t;(o/'stdout').write_bytes(got.stdout);(o/'stderr').write_bytes(got.stderr)
  assert got.returncode==source['exit_status'],(original.parent.name,got.returncode,got.stderr.decode())
  equal={}
  for name in('stdout','stderr','summary.json','async.jsonl','features.jsonl'):
   before=original.parent/name;after=o/name
   if before.exists():assert after.read_bytes()==before.read_bytes(),(original.parent.name,name)
   equal[name]=True
  report={'case':original.parent.name,'pass':True,'argv':argv,'exit_status':got.returncode,'byte_identical_outputs':equal,'baseline_host_seconds':source['host_seconds'],'candidate_host_seconds':elapsed,'input_sha256':{str(x):sha(x)for x in[Path(__file__).resolve(),a.candidate.resolve(),a.uart.resolve(),original]}};reports.append(report);(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(original.parent.name,elapsed,flush=True)
 result={'schema':'iris.empirical.host_optimization_equivalence.v1','pass':True,'candidate_sha256':sha(a.candidate),'uart_sha256':sha(a.uart),'reports':reports,'policy_or_calibration_changes':False,'scope':'all byte-level stdout/counters/prefix/async ledger/bounded summaries identical; directed tests only, wholeOS/fullCPUlayout remain separate'};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
