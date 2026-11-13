#!/usr/bin/env python3
"""Check finite FADD values, source flags, opaque bits, pending IRQ and RAW publication."""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 reference=json.loads((ROOT/'build/empirical-critical-cpu-fixes-selftest-v1/selected/report.json').read_text())['argv'];reports={}
 variants={'numeric':'build/empirical-fadd-async-guest-v3/guest.elf','opaque':'build/empirical-fadd-opaque-guest-v3/guest.elf','irq':'build/empirical-fadd-irq-guest-v2/guest.elf','chain':'build/empirical-fadd-chain-guest-v2/guest.elf','alt':'build/empirical-fadd-alt-guest-v1/guest.elf'}
 cases=[(variant,mode,None)for variant in variants for mode in('functional','base','long')]+[('bad','long',hart)for hart in range(3)]
 for variant,mode,bad in cases:
  name=f'{variant}-{mode}'+(''if bad is None else str(bad));o=out/name;o.mkdir();elf=ROOT/(variants[variant]if variant!='bad'else f'build/empirical-fadd-opaque-bad{bad}-v2/guest.elf');binary=(ROOT/'build/empirical-fast-frozen-05775560/spike')if mode=='functional'else a.binary.resolve();fixture=None if mode=='functional'else ROOT/f'build/empirical-fadd-first-v1/{mode}.fixture'
  argv=[x for x in reference if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))];argv[0]=str(binary);argv[-1]=str(elf);argv=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else x for x in argv]
  if fixture:argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(o/'summary.json')]
  env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(o/'async.jsonl'),IRIS_EMPIRICAL_FEATURES=str(o/'features.jsonl'));inputs=[Path(__file__).resolve(),elf,binary,a.uart.resolve(),ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb']+([fixture]if fixture else[]);before={str(x):sha(x)for x in inputs};t=time.monotonic();got=subprocess.run(argv,env=env,capture_output=True,timeout=90);elapsed=time.monotonic()-t;(o/'stdout').write_bytes(got.stdout);(o/'stderr').write_bytes(got.stderr)
  staged=[];rows=[];pending_irq=[]
  if bad is not None:assert got.returncode!=0 and f'IRIS_UNDEFINED_STATE hart={bad} '.encode() in got.stderr,(name,got.returncode,got.stderr.decode())
  else:
   assert got.returncode==0,(name,got.returncode,got.stderr.decode(),got.stdout.decode())
   if variant=='numeric':
    rows=[list(map(int,x.split()[1:]))for x in got.stdout.decode().splitlines()if x.startswith('IRIS_FADD_ASYNC ')];assert len(rows)==9 and all(row[-1]==0 for row in rows) and b'IRIS_FADD_DONE 0' in got.stdout,(name,rows)
    if mode=='long':assert all(row[4]-row[3]>9000 for row in rows),rows
   elif variant=='opaque':assert all(f'IRIS_FADD_OPAQUE {h} {16 if h==2 else 1}\n'.encode() in got.stdout for h in range(3))
   elif variant=='irq':assert all(f'IRIS_FADD_IRQ {h} 0 1077936128 1 0\n'.encode() in got.stdout for h in range(3))
   elif variant=='chain':assert all(f'IRIS_FADD_CHAIN {h} 0\n'.encode() in got.stdout for h in range(3))
   else:assert b'IRIS_FADD_ALT 0 120\n' in got.stdout,got.stdout.decode()
  if fixture:
   events=[json.loads(x)for x in(o/'async.jsonl').read_text().splitlines()];staged=[e for e in events if e['event']=='fp_staged'];expected={'numeric':9,'opaque':6,'irq':3,'chain':48,'alt':30}
   if bad is None:assert len(staged)==expected[variant],(name,len(staged))
   assert all(e['visible_flags']==e['flags_before'] and e['visible_fs']==e['fs_before'] for e in staged)
   if variant in('numeric','opaque','bad'):
    assert all(e['known_before']==31 and e['known_after']==31 for e in staged) if variant=='numeric'else all(e['known_before'] in(0,16 if e['hart']==2 else 1) and e['known_after']==(16 if e['hart']==2 else 1) for e in staged)
   if variant=='numeric':assert all(e['flags_before']==4 and e['flags_after']==(20 if e['hart']==2 else 5) for e in staged)
   begins={(e['hart'],e['backend_node']):e for e in events if e['event']=='begin'};pubs={(e['hart'],e['backend_node']):e for e in events if e['event']=='publish'}
   if bad is None:
    for e in staged:
     key=(e['hart'],e['backend_node']);assert key in begins and key in pubs
     assert pubs[key]['cycle']>=e['cycle'] and pubs[key]['cycle']>=begins[key]['com']
    summary=json.loads((o/'summary.json').read_text());assert not any(summary['pending_async_backends'])
    if variant=='chain':
     assert all(summary['per_hart_features'][h]['rvv.fadd.fp32']['instructions']==16 and summary['per_hart_features'][h]['rvv.fadd.fp32']['work']==(128 if h==2 else 32) for h in range(3)),summary['per_hart_features']
    if variant=='irq'and mode=='long':
     pending_irq=sorted({e['hart']for e in events if e['event']=='interrupt_pre_completion' and e['pending']>0});assert pending_irq==[0,1,2]
    if variant=='alt':
     for h in(0,1):assert summary['per_hart_features'][h]['rvv.fadd.bf16']['instructions']==5 and summary['per_hart_features'][h]['rvv.fadd.fp8']['instructions']==10
   for key,e in begins.items():
    if 'prior_backend_node'in e and key in pubs:
     prior=(e['hart'],e['prior_backend_node']);assert pubs[prior]['cycle']<=e['ex'] and e['prior_com']<=e['ex']
  assert all(sha(path)==digest for path,digest in before.items())
  report={'schema':'iris.empirical.fadd_async_check.v1','pass':True,'argv':argv,'input_sha256':before,'exit_status':got.returncode,'rows':rows,'host_seconds':elapsed,'staged_fp_snapshots_checked':len(staged),'pending_IRQ_harts':pending_irq,'scope':'functional/definedness and numeric publication; not FPGA timing calibration'};(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');reports[name]=str(o/'report.json');print(name,elapsed,flush=True)
 result={'schema':'iris.empirical.fadd_async_suite.v2','pass':True,'binary_sha256':sha(a.binary),'reports':{x:sha(path)for x,path in reports.items()},'calibrated':False,'timing_2pct':False};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
