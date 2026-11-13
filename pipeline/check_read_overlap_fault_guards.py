#!/usr/bin/env python3
"""Executed fallback recovery and unchanged capability-refusal controls."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 base=json.loads((ROOT/'build/rocket-packet-native-first-v1/report.json').read_text())['argv'];rows=[]
 for mprv in (False,True):
  for parent in (True,False):
   label=('MPRV-'if mprv else'recovery-')+('parent'if parent else'on');d=out/label;d.mkdir()
   b=ROOT/'build/empirical-rocket-RAS-frozen-52314001/spike'if parent else a.binary.resolve();u=ROOT/'build/empirical-rocket-RAS-frozen-52314001/libsifive_uart.so'if parent else a.uart.resolve()
   elf=ROOT/('build/empirical-owned-store-MPRV-guest-v2/guest.elf'if mprv else'build/empirical-owned-store-fault-guest-v2/guest.elf')
   f=d/'fixture';text=(ROOT/'build/rocket-packet-native-first-v1/first.fixture').read_text()
   if not parent:text+='\nempirical_store_front owned-dirty-L1-COM-v1\nempirical_read_overlap warm-private-L1-read-only-v1\n'
   f.write_text(text);argv=[x for x in base if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))];argv[0]=str(b);argv=['--extlib='+str(u)if x.startswith('--extlib=')else x for x in argv];argv[-1]=str(elf);argv[-1:-1]=['--iris-timing-fixture='+str(f),'--iris-timing-trace='+str(d/'summary.json')]
   inputs=[Path(__file__).resolve(),b,u,elf,elf.parent/'build.json',elf.parent/'private-runtime.c',f];hashes={str(p):sha(p)for p in inputs};start=time.monotonic();r=subprocess.run(argv,capture_output=True,timeout=60,env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl')));elapsed=time.monotonic()-start;(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr)
   if mprv:assert r.returncode==1 and r.stderr==b'IRIS_EMPIRICAL_TRANSLATED_MEMORY_UNSUPPORTED\n',(label,r.returncode,r.stderr)
   else:
    numeric=[list(map(int,line.split()[1:]))for line in r.stdout.decode().splitlines()if line.startswith('IRIS_STORE_FAULT ')];assert r.returncode==0 and sorted(numeric)==[[0,0,3],[1,0,3],[2,0,3]],(label,r.returncode,r.stdout,r.stderr)
    if not parent:
     events=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()];publications=[e for e in events if e['event']=='store_publish'];assert publications
     assert all(e['address']>=0x80000000 and e['address']+e['bytes']<=0x180000000 and not(e['address']%e['bytes'])for e in publications)
     metrics=json.loads((d/'summary.json').read_text())['owned_store_front']['per_hart'];assert all(m['published']>0 and not m['pending_accepted_response']for m in metrics)
   assert all(sha(p)==h for p,h in hashes.items());report={'pass':True,'argv':argv,'host_seconds':elapsed,'returncode':r.returncode,'input_sha256':hashes,'MPRV_refusal_control':mprv};(d/'report.json').write_text(json.dumps(report,indent=2)+'\n');rows.append({'case':label,'report_sha256':sha(d/'report.json')});print(label,elapsed,flush=True)
 report={'schema':'iris.owned_store_fallback_controls.v1','pass':True,'binary_sha256':sha(a.binary),'uart_sha256':sha(a.uart),'all3_recoverable_ROM_PMA_unmapped_misaligned_faults':9,'MPRV_existing_refusal_unchanged':True,'PMP_configuration_qualified':False,'reports':rows};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':main()
