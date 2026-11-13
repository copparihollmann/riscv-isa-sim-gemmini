#!/usr/bin/env python3
"""Freeze continuous native return-branch replay with source and RTL input digests."""
import argparse,copy,hashlib,json,shutil,subprocess,time
from pathlib import Path
import noc_router_check as check
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final';RTL=R/'build/noc-router-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jread(p):return json.loads(Path(p).read_text())
def sig(path,checks):
 import struct
 lines=path.read_text().splitlines()
 if len(lines)!=28 or any(len(x)!=16 for x in lines):raise ValueError('Bad coherent signature')
 v=[int(x,16) for x in lines]
 if v[:4]!=[0x4952495350524f42,1,4,0]:raise ValueError('Failed memory guest')
 rows=[dict(zip(['stage','actual','expected','cause','pc','tval','checks','done'],v[4+8*h:12+8*h]),hart=h) for h in range(3)]
 if any(x['done']!=1 or x['checks']!=checks[x['hart']] or x['actual']!=x['expected'] for x in rows):raise ValueError('Wrong/incomplete passing control')
 return rows

def empty_seed():
 x={f['name']:0 for f in jread(R/'timing/noc_router_observer_fields.json')};x['egress_empty']=1;x['tb']=0;return x

def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--output',type=Path,default=R/'build/noc-router-component-v1-final');ap.add_argument('--verify',action='store_true');a=ap.parse_args();out=a.output.resolve()
 if a.verify:
  j=jread(out/'report.json')
  for name,digest in j['artifact_sha256'].items():
   if sha(out/name)!=digest:raise ValueError('Frozen router artifact changed: '+name)
  for case,receipt in j['cases'].items():
   q=subprocess.run([str(out/'noc-router')],input=(out/(case+'.input')).read_text(),text=True,capture_output=True,timeout=15)
   if q.returncode or hashlib.sha256(q.stdout.encode()).hexdigest()!=receipt['stdout_sha256']:raise ValueError('Frozen native continuous replay changed')
  for ex in j['unit_executions']:
   q=subprocess.run([str(out/'noc-router')],input=(out/ex['input']).read_text(),text=True,capture_output=True,timeout=15)
   if q.returncode!=ex['exit_status'] or hashlib.sha256(q.stdout.encode()).hexdigest()!=ex['stdout_sha256'] or hashlib.sha256(q.stderr.encode()).hexdigest()!=ex['stderr_sha256']:raise ValueError('Frozen native unit guard changed')
  print(json.dumps({'pass':True,'continuous_cycles':sum(c['cycles'] for c in j['cases'].values()),'whole_router_certified':False}));return
 if out.exists():raise ValueError('Refuse to overwrite router closure')
 profile=jread(R/'timing/noc_router_sources.json')
 for field in ['source_capsule','arbiter_component']:
  if sha(R/profile[field])!=profile[field+'_sha256']:raise ValueError('Reference component identity mismatch')
 build=jread(RTL/'build.json')
 for p,d in build['input_sha256'].items():
  if sha(p)!=d:raise ValueError('RTL observer build input changed')
 out.mkdir(parents=True);compiler=Path(shutil.which('c++')).resolve();binary=out/'noc-router';argv=[str(compiler),'-O2','-std=c++20','-Wall','-Wextra','-Werror',str(R/'timing/noc_arbiter.cpp'),str(R/'timing/noc_router.cpp'),str(R/'timing/noc_router_driver.cpp'),'-o',str(binary)];subprocess.run(argv,check=True)
 cases={};paths=[R/'timing'/n for n in ['noc_arbiter.hpp','noc_arbiter.cpp','noc_router.hpp','noc_router.cpp','noc_router_driver.cpp','noc_router_sources.json','noc_router_README.md','noc_router_package.py','noc_router_check.py','noc_router_observer.cpp','noc_router_observer.hpp','noc_router_observer_fields.json','noc_router_observer_build.py','noc_router_run.py']]+[compiler,CAP/'report.json',R/profile['arbiter_component'],RTL/'build.json']
 frames={}
 for case,status in [('original9',1),('control8',0),('fenced9',0)]:
  run=jread(RTL/(case+'.json'))
  if run['exit_status']!=status or run['timed_out']:raise ValueError('Unexpected RTL run outcome')
  for key,p in [('binary_sha256',Path(run['argv'][0])),('elf_sha256',Path(run['argv'][-1])),('build_sha256',RTL/'build.json'),('stdout_sha256',RTL/(case+'.stdout')),('stderr_sha256',RTL/(case+'.stderr'))]:
   if sha(p)!=run[key]:raise ValueError('RTL identity mismatch')
   paths.append(p)
  paths.append(RTL/(case+'.json'));started=time.monotonic();receipt=check.validate(binary,case,out);receipt['host_validation_seconds']=time.monotonic()-started;frames[case]=check.frames(case)
  internal=set(frames[case][0])-{'tb','arrival_valid','arrival_vc','arrival_dest','arrival_dest_id','arrival_word0','arrival_word1','arrival_word2','nif_ready','route_fire','route_vc'}-{'peer'+str(k)+'_'+n for k in range(1,4) for n in ['eligible','outputs']}
  poisoned=copy.deepcopy(frames[case])
  for row in poisoned[1:]:
   for key in internal:row[key]=0
  if check.seed(poisoned[0])+''.join(check.step(x) for x in poisoned)!=check.seed(frames[case][0])+''.join(check.step(x) for x in frames[case]):raise ValueError('Internal state reinjected after first snapshot')
  receipt.update(internal_state_after_first_not_used=True,peer_local_va_contenders=0,peer_local_switch_contenders=0,nonlocal_arrivals=0,route_completions=sum(x['route_fire'] for x in frames[case]),initial_queued_flits=sum(check.count(frames[case][0],'vc'+str(k)+'_',5) for k in range(6))+check.count(frames[case][0],'egress_',2),final_queued_flits=sum(check.count(frames[case][-1],'vc'+str(k)+'_',5) for k in range(6))+check.count(frames[case][-1],'egress_',2),rtl_run_sha256=sha(RTL/(case+'.json')),rtl_elf_sha256=run['elf_sha256'])
  if case!='original9':receipt['coherent_harts']=sig(RTL/(case+'.signature'),[0,0,64 if case=='control8' else 72]);paths.append(RTL/(case+'.signature'))
  cases[case]=receipt
 # The additional observer preserves the prior architectural-facing transcript exactly.
 original=[x for x in (RTL/'original9.stderr').read_text().splitlines() if x.startswith('RTL_MEMTRACE ')]
 if original!=[x for x in (CAP/'build/rtl-loader-diag/vector-memory-h2-9-va2.stderr').read_text().splitlines() if x.startswith('RTL_MEMTRACE ')]:raise ValueError('Observer changed original VTL trace')
 # Unit boundary cases are source-specific FIFO/reservation timing checks.
 units=[];labels=check.expected(frames['original9'][0])[0]
 def run_unit(name,body,status=0):
  q=subprocess.run([str(binary)],input=body,text=True,capture_output=True,timeout=15);base='unit-'+name
  (out/(base+'.input')).write_text(body);(out/(base+'.stdout')).write_text(q.stdout);(out/(base+'.stderr')).write_text(q.stderr)
  units.append({'name':name,'input':base+'.input','exit_status':q.returncode,'stdout_sha256':sha(out/(base+'.stdout')),'stderr_sha256':sha(out/(base+'.stderr'))})
  if q.returncode!=status:raise ValueError('Native unit failed: '+name+' '+q.stderr)
  return [dict(zip(labels,[int(v) for v in line.split()])) for line in q.stdout.splitlines()]
 prefix='profile 6 5 2 5 0 4 13 0 12\n';base=empty_seed();seq=prefix+check.seed(base)
 for tb in range(6):
  x=empty_seed();x['tb']=tb;x['nif_ready']=int(tb>=4)
  if tb in [0,1]:x.update(arrival_valid=1,arrival_vc=tb,arrival_dest=5,arrival_dest_id=0,arrival_word0=0x111103+(tb<<8))
  seq+=check.step(x)
 unit=run_unit('stalled-tail-and-new-reservation',seq)
 if not(unit[2]['popped_vcs']==1 and unit[2]['egress_push']==1 and unit[2]['freed_vcs']==1 and unit[3]['egress_count']==1 and unit[3]['output_grants']==4096 and unit[4]['popped_vcs']==0 and unit[4]['egress_pop']==1 and unit[5]['popped_vcs']==2 and unit[5]['egress_push']==0 and unit[5]['out_valid']==1):raise ValueError('Source FIFO/credit/reservation timing mismatch')
 invalid=[]
 x=empty_seed();x.update(tb=0,arrival_valid=1,arrival_dest=4,arrival_dest_id=0);invalid.append(('nonlocal-flow',prefix+check.seed(base)+check.step(x)))
 x=empty_seed();x['peer1_eligible']=1;x['peer1_outputs']=4096;invalid.append(('peer-local-contender',prefix+check.seed(base)+check.step(x)))
 x=empty_seed();x['route_fire']=1;x['route_vc']=0;invalid.append(('unmatched-route-completion',prefix+check.seed(base)+check.step(x)))
 full=empty_seed();full.update(vc0_enq=0,vc0_deq=0,vc0_maybe=1,vc0_state=2,vc0_local=1);x=empty_seed();x.update(arrival_valid=1,arrival_dest=5,arrival_word0=0);invalid.append(('full-input-fifo',prefix+check.seed(full)+check.step(x)))
 active=empty_seed();active.update(vc0_state=2,vc0_local=1);x=empty_seed();x.update(arrival_valid=1,arrival_dest=5,arrival_word0=1);invalid.append(('head-on-busy-vc',prefix+check.seed(active)+check.step(x)))
 invalid.append(('wrong-depth','profile 6 6 2 5 0 4 13 0 12\n'))
 invalid.append(('negative-field','profile -6 5 2 5 0 4 13 0 12\n'))
 for name,body in invalid:run_unit('reject-'+name,body,2)
 # Corrupt a real, compared valid field rather than inactive undefined payload.
 mutation_rejections=[]
 native=[[int(v) for v in line.split()] for line in (out/'original9.stdout').read_text().splitlines()]
 for key in ['input_mask','vc0_count','egress_empty','popped_vcs','out_word0']:
  index=labels.index(key);target=next(k for k,x in enumerate(frames['original9']) if x['out_valid']) if key=='out_word0' else 0
  bad=native[target][:];bad[index]^=1
  if bad==check.expected(frames['original9'][target])[1]:raise ValueError('Corrupt native result admitted')
  mutation_rejections.append(key)
 # Bind exact source statements and physical sizes.
 citations=[]
 for file,needle,fact in [('InputBuffer.sv','Queue5_BaseFlit qs_0','Five-entry VC FIFO; six instances0..5'),('EgressUnit_21.sv','Queue2_EgressFlit q','Two-entry egress FIFO'),('EgressUnit_21.sv','assign io_credit_available_0 =','Only an empty egress FIFO supplies credit'),('EgressUnit_21.sv','channel_empty <= ~io_allocs_0_alloc','New allocation wins over simultaneous release'),('InputUnit_10.sv','wire        salloc_outs_0_valid =','Same-edge switch traversal: combineSAST'),('SwitchArbiter_41.sv','lock_0 <= chosen','Packet lock transition'),('Queue5_BaseFlit.sv','wire        do_enq =','Nonpipelined VC enqueue'),('Queue2_EgressFlit.sv','wire        do_enq =','Flow-through egress bypass')]:
  p=CAP/'build/rtl-verilator/gen-collateral'/file;hits=[i for i,line in enumerate(p.read_text().splitlines(),1) if needle in line]
  if len(hits)!=1:raise ValueError('Ambiguous source citation: '+file+' '+needle)
  citations.append({'path':str(p.relative_to(R)),'sha256':sha(p),'line':hits[0],'fact':fact});paths.append(p)
 for p,d in build['input_sha256'].items():paths.append(Path(p))
 for rel,meta in jread(CAP/'report.json')['origins'].items():
  if '/riscv-tools/lib/' in meta['path']:
   if sha(meta['path'])!=meta['sha256']:raise ValueError('RTL host ABI changed')
   paths.append(Path(meta['path']))
 origins={}
 for p in sorted(set(paths)):
  p=p.resolve()
  try:rel=Path('inputs')/p.relative_to(R)
  except ValueError:rel=Path('inputs/external')/p.relative_to('/')
  dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst);origins[str(rel)]={'path':str(p),'sha256':sha(p)}
 report={'schema':'iris.native_local_router_return_branch.v1','pass':True,'source_profile':profile,'native_sha256':sha(binary),'compile_argv':argv,'compiler_sha256':sha(compiler),'compiler_version':subprocess.check_output([str(compiler),'--version'],text=True),'source_citations':citations,'cases':cases,'unit_executions':units,'invalid_boundary_rejections':[x[0] for x in invalid],'golden_corruption_rejections':mutation_rejections,'external_dependencies':profile['external_dependencies'],'accepted_input_sampling':'Data taken read-only from just-accepted RTL FIFO write slot afteredge, indexedby capturedpreedgeVC/enqueueaddress; anyvalidarrivalwithoutactualenqueue refuses. Allothergoldens oldstablepreedge.','continuous_internal_state':True,'observed_waiting_or_egress_availability_injected':False,'whole_router_certified':False,'whole_noc_certified':False,'timing_calibrated':False,'matches_ethan_firesim_image':False,'four_state_definedness_available':False,'unknown_reset_behavior_proven_irrelevant':False,'rtl_modified':False,'hardware_contacted':False,'origins':origins,'artifact_sha256':{str(x.relative_to(out)):sha(x) for x in sorted(out.rglob('*')) if x.is_file()}}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'cases':{k:v['cycles'] for k,v in cases.items()},'native_sha256':sha(binary),'report':str(out/'report.json')}))
if __name__=='__main__':main()
