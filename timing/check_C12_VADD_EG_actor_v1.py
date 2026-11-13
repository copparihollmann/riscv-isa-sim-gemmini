#!/usr/bin/env python3
"""Fresh bounded native VADD-EG numeric, version, kill and admission controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(b,s):
 if not b:raise ValueError(s)
def main():
 a=argparse.ArgumentParser(__doc__);a.add_argument('--capsule',type=Path,required=True);a.add_argument('--ON',type=Path,required=True);a.add_argument('--OFF',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
 cap,on,off,out=[p.resolve()for p in(args.capsule,args.ON,args.OFF,args.output)];out.mkdir(parents=True,exist_ok=False)
 cm=json.loads((cap/'manifest.json').read_text())
 for n,h in cm['artifact_sha256'].items():need(sha(cap/n)==h,'Frozen capsule changed')
 source=ROOT/'timing/C12_VADD_EG_actor_guest_v1.c';cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc').resolve();runs=[];builds=[]
 inputs=[Path(__file__).resolve(),source,cc,cap/'manifest.json',cap/'spike',cap/'libsifive_uart.so',on,off,ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',*[ROOT/'benchmarks'/n for n in('start.S','runtime.c','runtime.h','link.ld','uart_drain.h')]]
 ids={str(p):sha(p)for p in inputs}
 def build(h,bad):
  d=out/f'guest-h{h}-bad{bad}';d.mkdir();elf=d/'guest.elf'
  argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3',f'-DIRIS_ACTIVE_HART={h}',f'-DIRIS_BAD={bad}','-I'+str(ROOT/'benchmarks'),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(source),'-lgcc','-o',str(elf)]
  p=subprocess.run(argv,capture_output=True);(d/'stderr').write_bytes(p.stderr);need(p.returncode==0,'Guest compile failed '+p.stderr.decode());builds.append(dict(argv=argv,ELF_sha256=sha(elf)));return elf
 def run(name,binary,uart,fixture,elf,seed=0):
  d=out/name;d.mkdir();argv=command(binary,elf);argv=['--extlib='+str(uart)if a.startswith('--extlib=')else a for a in argv]
  argv=argv[:-1]+['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-schedule-seed='+str(seed),'--iris-timing-trace='+str(d/'summary.json')]+argv[-1:]
  env={k:v for k,v in os.environ.items()if not k.startswith('IRIS_EMPIRICAL_')};env.update(IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl'),IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl'))
  started=time.monotonic();p=None;timed=False
  try:
   with(d/'stdout').open('wb')as so,(d/'stderr').open('wb')as se:
    p=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True)
    try:code=p.wait(timeout=60)
    except subprocess.TimeoutExpired:
     timed=True;os.killpg(p.pid,signal.SIGTERM)
     try:code=p.wait(timeout=1)
     except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);code=p.wait()
  finally:
   if p is not None and p.poll()is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
  row=dict(name=name,argv=argv,exit_status=code,timed_out=timed,host_seconds=time.monotonic()-started,
    binary_sha256=sha(binary),UART_sha256=sha(uart),fixture_sha256=sha(fixture),ELF_sha256=sha(elf))
  (d/'run.json').write_text(json.dumps(row,indent=2)+'\n');runs.append(row);return d,row
 for h in(0,1):
  elf=build(h,0)
  for seed in(0,17):
   d,row=run(f'ON-h{h}-seed{seed}',cap/'spike',cap/'libsifive_uart.so',on,elf,seed)
   text=(d/'stdout').read_text();need(row['exit_status']==0 and not row['timed_out']and not(d/'stderr').read_bytes(),'Normal positive guest failed')
   fields=[list(map(int,l.split()[1:]))for l in text.splitlines()if l.startswith('IRIS_VADD_EG ')]
   expected=[]
   for sew in(8,16,32,64):
    for lm in(1,2,4,8):
     for mode in range(4):expected.append([h,sew,lm,mode,256//sew*lm*(2 if mode in(1,2)else 1),0])
   need(fields==expected and f'IRIS_VADD_EG_DONE {h} 64 5408 0\n'in text,'Independent literal integer65/66/2 word goldens/count/order')
   summary=json.loads((d/'summary.json').read_text());metrics=summary['vadd_EG_metrics'][h]
   need(metrics['accepted']-metrics['preCOM_killed']==6145 and metrics['microissues']==46082 and metrics['physical_16B_writes']==46082 and metrics['preCOM_killed']>=1 and metrics['pending']==0 and metrics['peak']<=13,'Owned command/group/version/kill/drain counts')
   events=[json.loads(l)for l in(d/'async.jsonl').read_text().splitlines()];front={e['generation']:e for e in events if e['event']=='vadd_EG_front_reservation'};com={e['generation']:e for e in events if e['event']=='vadd_EG_functional_COM'};issued={};writes=0
   for e in events:
    if e['event']=='vadd_EG_microissue':
     g=e['generation'];need(g in com and e['cycle']>=front[g]['available']+3 and e['cycle']>=com[g]['cycle']+4,'Actual COM/input/issue order');issued[g,e['index']]=e['cycle']
    if e['event']=='vadd_EG_physical_write':
     need(e['cycle']-issued[e['generation'],e['index']]==1 and e['bytes']==16,'Exact qualified per-EG source write edge');writes+=1
   need(writes==46082,'Complete physical-write transcript')
   import struct
   data=elf.read_bytes();eh=struct.unpack_from('<16sHHIQQQIHHHHHH',data);pcs=[]
   for pi in range(eh[10]):
    seg=struct.unpack_from('<IIQQQQQQ',data,eh[5]+pi*eh[9])
    if seg[0]==1 and seg[1]&1:
     for offset in range(0,seg[5]-3,2):
      if int.from_bytes(data[seg[2]+offset:seg[2]+offset+4],'little')==0x02108457:pcs.append(seg[3]+offset)
   need(len(pcs)==1,'Unique actual partial-geometry/undefined-v1 wrongpath opcode')
   killed=[e for e in events if e['event']=='vadd_EG_wrongpath_cancel' and e['pc']==pcs[0]]
   need(killed,'Actual explicit opaque wrongpath was not observed')
   for e in killed:
    generation=e['generation'];need(generation not in com and not any(k[0]==generation for k in issued) and e['cycle']<front[generation]['COM'],'Opaque wrongpath touched semantic or backend state')

   row.update(pass_=True,independent_words=5408,metrics=metrics,source_phase_checks=writes)
  if h==0:
   parent=ROOT/'build/C12-source-composite-frozen-02b4a9ab-v2'
   da,ra=run('parent-OFF',parent/'spike',parent/'libsifive_uart.so',off,elf)
   db,rb=run('new-OFF',cap/'spike',cap/'libsifive_uart.so',off,elf)
   for file in('stdout','stderr','features.jsonl','async.jsonl'):need((da/file).read_bytes()==(db/file).read_bytes(),'DefaultOFF byte parity '+file)
   need(ra['exit_status']==rb['exit_status']==0,'OFF normal exits');ra.update(pass_=True);rb.update(pass_=True)
  expected_refusals={1:'IRIS_UNDEFINED_STATE',2:'IRIS_VADD_EG_FULLVL_UNMASKED_SCOPE',3:'IRIS_VADD_EG_FULLVL_UNMASKED_SCOPE',4:'IRIS_VADD_EG_CPU_FETCH_BOUNDARY_UNMODELED',5:'IRIS_VADD_EG_MMODE_KNOWN_CONFIG_VS_ALREADY_DIRTY_SCOPE',6:'IRIS_VADD_EG_IRQ_CONTEXT_UNMODELED',7:'IRIS_VADD_EG_ACTIVE_IRQ_CONTEXT_UNMODELED'}
  for bad,expected in expected_refusals.items():
   elf=build(h,bad);d,row=run(f'refusal-h{h}-bad{bad}',cap/'spike',cap/'libsifive_uart.so',on,elf)
   error=(d/'stderr').read_text();matched=expected in error or(bad==7 and 'IRIS_VADD_EG_IRQ_CONTEXT_UNMODELED'in error)
   need(row['exit_status']!=0 and not row['timed_out']and matched,'Typed refusal missing '+row['name']+': '+error)
   summary=json.loads((d/'summary.json').read_text());metrics=summary['vadd_EG_metrics'][h]
   if bad<=6:need(metrics['microissues']==0 and metrics['physical_16B_writes']==0,'Unqualified architectural command must not enqueue/issue/publish')
   if bad!=4:need(all(k in error for k in ('hart=', 'pc=', 'raw=', 'VL=', 'SEW=', 'LMUL=')),'Guest-context refusal must carry actionable context')
   if bad==7:need(metrics['accepted']>0 and metrics['pending']>0,'Active IRQ actually intersects live owned actor')
   row.update(pass_=True,typed_refusal=expected,metrics=metrics)
 need(all(sha(p)==v for p,v in ids.items()),'Inputs changed during tests')
 report=dict(schema='iris.C12_composite_VADD_directed_controls.v1',**{'pass':True},native_binary_sha256=sha(cap/'spike'),UART_sha256=sha(cap/'libsifive_uart.so'),source_capsule_manifest_sha256=sha(cap/'manifest.json'),
  scope='quiet harts0/1 individually; SEW8/16/32/64 LMUL1/2/4/8 dep/indep/chaining/WAW; all active words and FFLAGS31/VXSAT1 unchanged; wrongpath partialVL+unwrittenv1 opaque reservation canceled; architectural partialVL remains refused; explicit unsupported contexts',
  exact_16B_per_EG_physical_publication=True,source_issue_to_write_edges=1,CPU_COMplus1_bridge_qualified=False,
  default_OFF_byte_parity=True,normal_positive_runs=4,typed_refusals=14,old8f_causal_wrongpath_control=False,independent_word_checks=21632,
  metric_units='accepted counts front RRD reservations including preCOM cancellation; source/backend accepted = accepted - preCOM_killed after full drain; write bytes are internal VRF traffic only',
  floating_flags_and_vxsat_unchanged=True,VS_already_dirty_only=True,FPGA_or_reserved_labels_used=False,native_provider_promoted=False,hardware_contacted=False,
  guest_builds=builds,runs=[{('pass'if k=='pass_'else k):v for k,v in x.items()}for x in runs],input_sha256=ids)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json'),'runs':len(runs)}))
if __name__=='__main__':main()
