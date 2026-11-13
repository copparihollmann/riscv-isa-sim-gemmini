#!/usr/bin/env python3
"""Replay an actual three-hart ELF and independently check vector-path features."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__)
 for key in ['binary','uart','fixture','elf','output']:p.add_argument('--'+key,type=Path,required=True)
 a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False,parents=True)
 inputs=[Path(__file__).resolve(),ROOT/'spike/run_functional.py',a.binary.resolve(),a.uart.resolve(),a.fixture.resolve(),a.elf.resolve(),ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];before={str(x):sha(x)for x in inputs}
 argv=command(a.binary.resolve(),a.elf.resolve());argv=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else x for x in argv];argv=argv[:-1]+['--iris-bootrom='+str(inputs[-2]),'--dtb='+str(inputs[-1]),'--iris-timing-fixture='+str(a.fixture.resolve()),'--iris-timing-trace='+str(o/'summary.json')]+argv[-1:]
 t=time.monotonic();r=subprocess.run(argv,capture_output=True,env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(o/'features.jsonl')),timeout=90);elapsed=time.monotonic()-t;(o/'stdout').write_bytes(r.stdout);(o/'stderr').write_bytes(r.stderr)
 rows=[json.loads(x)for x in(o/'features.jsonl').read_text().splitlines()];by={}
 for row in rows:by.setdefault(row['hart'],{}).setdefault(row['value'],[]).append(row)
 checks=[];observed=set()
 for line in r.stdout.decode().splitlines():
  if not line.startswith('IRIS_VECTOR_BYPASS '):continue
  _,h,lo,hi,sl,sh,failed=line.split();h=int(h);assert h not in observed and int(failed)==0;observed.add(h)
  for family,start,end in [('memory.vector.load',lo,hi),('memory.vector.store',sl,sh)]:
   lower,upper=[by[h][int(x)]for x in [start,end]];assert len(lower)==len(upper)==1;lower,upper=lower[0],upper[0]
   f={k:upper['features'].get(family,{}).get(k,0)-lower['features'].get(family,{}).get(k,0)for k in ['instructions','bytes','dlen_beats','atl_beats']}
   m={k:upper['memory'].get('DRAM',{}).get(k,0)-lower['memory'].get('DRAM',{}).get(k,0)for k in ['accesses','bytes','l1hits','l1misses','l2hits','l2misses','dirty_owner_forwards']}
   assert f==dict(instructions=2,bytes=64,dlen_beats=2 if h==2 else 4,atl_beats=8 if h==2 else 2),(h,f)
   assert m['accesses']==2 and m['bytes']==64 and m['l1hits']==m['l1misses']==0 and m['l2hits']+m['l2misses']==2,(h,m)
   checks.append(dict(hart=h,family=family,features=f,memory=m))
 passed=r.returncode==0 and observed=={0,1,2} and all(sha(x)==digest for x,digest in before.items())
 report=dict(schema='iris.empirical.vector_bypass_native_check.v1',**{'pass':passed},argv=argv,exit_status=r.returncode,host_seconds=elapsed,input_sha256=before,checks=checks,scope='actual3hartELF; independent per-word numerical values; directL2 timinghistory and DLEN/ATLrequestedbeat counts; wholeinstruction batchedresponse publication; latency unqualified',timing_certified=False)
 (o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':passed,'checks':len(checks),'seconds':elapsed}));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
