#!/usr/bin/env python3
"""Run frozen ELF/control bytes through separate opt-in phase successor, locally."""
import argparse,concurrent.futures,hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 template=json.loads((R/'build/warm-load-phase-native-v2/argv.json').read_text());parent=(R/'build/warm-load-phase-native-v2/full.fixture').read_text().replace('empirical_icache address-tags-refill-proxy-v1\n','')
 def one(kind,mode):
  b=o/(kind+'-'+mode);b.mkdir();f=b/'full.fixture';t=parent
  if mode=='ON':t=t.replace('dram-L1-hit-latched-response-v1','dram-L1-hit-Shuttle-COM-forward-v2')
  f.write_text(t);elf=R/('build/warm-load-phase-guest-'+('v2'if kind=='pair'else'v1')+'/guest.elf');argv=[('--extlib='+str(a.uart.resolve()))if x.startswith('--extlib=')else('--iris-timing-fixture='+str(f))if x.startswith('--iris-timing-fixture=')else('--iris-timing-trace='+str(b/'graph.json'))if x.startswith('--iris-timing-trace=')else x for x in template];argv[0]=str(a.binary.resolve());argv[-1]=str(elf);(b/'argv.json').write_text(json.dumps(argv,indent=2)+'\n')
  paths=[Path(__file__).resolve(),a.binary.resolve(),a.uart.resolve(),f,elf,R/'board/evidence/bootrom.rv64.img',R/'board/build/iris.dtb'];before={str(x):sha(x)for x in paths};start=time.monotonic()
  with(b/'stdout').open('wb')as out,(b/'stderr').open('wb')as err:
   try:cp=subprocess.run(argv,stdout=out,stderr=err,timeout=120);rc=cp.returncode
   except subprocess.TimeoutExpired:rc=124
  elapsed=time.monotonic()-start;assert before=={str(x):sha(x)for x in paths};text=(b/'stdout').read_text();lines=[x.split()for x in text.splitlines()if x.startswith('WARM_LOAD_PHASE ')];assert rc==0 and len(lines)==3 and {int(x[1])for x in lines}=={0,1,2};assert all(int(x[3])>int(x[2])for x in lines)
  r=dict(schema='iris.warm_load_phase_native_run.v1',status='passed_numeric_normal_exit',kind=kind,mode=mode,argv=argv,exit_status=rc,host_seconds=elapsed,input_sha256=before,stdout_sha256=sha(b/'stdout'),stderr_sha256=sha(b/'stderr'),graph_sha256=sha(b/'graph.json'),all3_booted_and_private_pointer_numeric_passed=True,hardware_contacted=False,source_phase_certified=False);(b/'run.json').write_text(json.dumps(r,indent=2)+'\n');return dict(kind=kind,mode=mode,host_seconds=elapsed,receipt=str(b/'run.json'),receipt_sha256=sha(b/'run.json'))
 with concurrent.futures.ThreadPoolExecutor(max_workers=2)as ex:rows=list(ex.map(lambda v:one(*v),[(k,m)for k in('pair','chain')for m in('OFF','ON')]))
 (o/'report.json').write_text(json.dumps(dict(schema='iris.warm_load_phase_native_runs.v1',pass_=True,runs=rows),indent=2)+'\n');print(json.dumps(rows))
if __name__=='__main__':main()
