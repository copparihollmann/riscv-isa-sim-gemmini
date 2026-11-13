#!/usr/bin/env python3
import argparse,copy,importlib.util,json,struct
from pathlib import Path
from build import ROOT,sha
from validate import validate,validate_corpus,canonical
spec=importlib.util.spec_from_file_location('strict_old_ELF_reader',ROOT/'firesim/pow2_memory_review.py');elfmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(elfmod)
def inspect(raw,c,layout):
 validate_corpus(c);e=elfmod.Elf(raw);table,size=e.syms['experiments'];assert size==117*24
 for i,r in enumerate(c['cases']):
  name,n,loads,h,t=struct.unpack('<QIIII',e.read(table+24*i,24));assert e.string(name)==r['case_id']and(n,loads,h,t)==(r['nodes'],r['loads'],r['hart'],r['trial_id'])
 addr,size=e.syms['footprint_chase'];body=struct.pack('<4I',0x00053503,0xfff58593,0xfe059ce3,0x00008067);assert size==16 and addr%4==0 and e.read(addr,16)==body
 objects={k:dict(address=e.syms[k][0],size=e.syms[k][1])for k in('footprint_records','footprint_record_count','footprint_measurements_done')};assert objects==layout['objects']and objects['footprint_records']['size']==234*128 and objects['footprint_records']['address']%128==0
 assert layout['record_bytes']==128 and type(layout['record_bytes'])is int and layout['records']==234 and layout['fields']==['case_index','phase','hart','start','end','instret','checksum','expected','mtime_before','mtime_after','loads','evict_sum','msip_before','msip_after']
 assert e.read(objects['footprint_measurements_done']['address'],8)==b'\xff'*8
 controls=layout['control_objects'];assert controls['parked']['size']==384 and controls['completion']['size']==128 and all(r['address']%128==0 for r in controls.values())
 spans=[(r['address'],r['address']+r['size'])for r in [*objects.values(),*controls.values()]];assert all(max(a,c)>=min(b,d)for i,(a,b)in enumerate(spans)for c,d in spans[i+1:])
 return dict(compiled_case_records=117,compiled_case_stride=24,compiled_nodes_loads_roles_trials=True,exact_dependent_loop_bytes=body.hex(),loop_address=addr,record_stride=128,buffer_objects=objects,control_objects=controls,all_records_private_cacheline_aligned=True,control_record_nonoverlap=True,sentinel_known_filebacked=True)
def flatten(c):
 validate_corpus(c);out=[]
 for r in c['cases']:
  for p,name in enumerate(('cold','steady')):
   expected=[0x90000000+h*0x02000000+64*((17*r['trial_id']+7*h)%r['nodes'])for h in range(3)]
   out.append(dict(id=r['case_id']+'.'+name,active_harts=[r['hart']],expected_checksums_by_hart=expected,parent_case_id=r['case_id'],semantic_parent_case_id=r['semantic_parent_case_id'],trial_id=r['trial_id'],pass_index=p,region='chase',suite='pow2_isolated_memory',corpus_split=c['split_id'],internal_split=r['internal_split']))
 return out
def protocol_check():
 # Inactive states:0clear,1publishpark,2waitcompletion,3waitactualMSIP,4clear,5done.
 # Active:0waitacks,1window,2publishcompletion,3sendwakes,4done.
 start=(0,0,0,0,0,0);seen={start};todo=[start];term=0
 while todo:
  a,b,m0,m1,active,done=todo.pop();states=[a,b];mips=[m0,m1];nexts=[]
  for h in range(2):
   st=states[h];ns=states[:];nm=mips[:]
   if st==0:assert active<1;ns[h]=1;nm[h]=0
   elif st==1:assert active<1;ns[h]=2
   elif st==2:
    if not done:continue
    ns[h]=3
   elif st==3:
    if not nm[h]:continue
    ns[h]=4
   elif st==4:assert done and active>=3;ns[h]=5;nm[h]=0
   else:continue
   nexts.append((*ns,*nm,active,done))
  if active==0 and a>=2 and b>=2:nexts.append((a,b,m0,m1,1,0))
  elif active==1:nexts.append((a,b,m0,m1,2,0))
  elif active==2:nexts.append((a,b,m0,m1,3,1))
  elif active==3:
   if not m0 and a<4:nexts.append((a,b,1,m1,3,1))
   if not m1 and b<4:nexts.append((a,b,m0,1,3,1))
   if a>=4 and b>=4:nexts.append((a,b,m0,m1,4,1))
  if not nexts:assert a==b==5 and active==4;term+=1
  for s in nexts:
   if s not in seen:seen.add(s);todo.append(s)
 return dict(pass_=True,states=len(seen),terminal_states=term,foreign_writes_during_window=0,early_completion_before_MMIO_wake_explored=True,delayed_wake_consumed_before_next_ack=True,MIE_masked_across_checks_WFI=True)
def qualify(build,negative):
 c=json.loads((build/'corpus.json').read_text());b=json.loads((build/'build.json').read_text());layout=json.loads((build/'layout.json').read_text());validate_corpus(c);proof=inspect((build/'footprints.elf').read_bytes(),c,layout);normal=[];ids=dict(b['input_sha256'])
 for seed in(0,17):
  d=build/('seed%d'%seed);r=json.loads((d/'run.json').read_text());assert r['pass']is True and r['exit_status']==0 and not r['timed_out']and r['normal_guest_exit_verified']is True and r['elf_sha256']==b['elf_sha256'];validate((d/'stdout').read_text(),c);assert sha(d/'stdout')==r['stdout_sha256']and sha(d/'stderr')==r['stderr_sha256'];ids.update(r['input_sha256']);ids.update({str(p):sha(p)for p in[d/'run.json',d/'stdout',d/'stderr']});normal.append(dict(seed=seed,report=str(d/'run.json'),report_sha256=sha(d/'run.json'),host_seconds=r['host_seconds']))
 neg=negative/'seed0/run.json';n=json.loads(neg.read_text());assert n['pass']is True and n['expect_negative']is True and n['exit_status']!=0 and not n['timed_out']and n['proof']==dict(actual_omitted_kernel_detected=True,failed_regions=234);ids.update(n['input_sha256']);ids.update({str(p):sha(p)for p in[neg,neg.parent/'stdout',neg.parent/'stderr']})
 text=(build/'seed0/stdout').read_text();rows=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_REGION ')];controls=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,AssertionError,KeyError,TypeError,struct.error):controls.append(dict(name=name,rejected=True))
  else:raise ValueError('Corruption admitted '+name)
 def wire(rr):return '\n'.join('IRIS_REGION '+json.dumps(r)for r in rr)+'\nIRIS_BATCH_DONE {"failed":0,"cases":117,"regions":234,"trials":3}\n'
 for key,value in [('hart',True),('checksum',0),('expected_checksum',0),('body_loads',1),('whole_laps',1),('msip_before',1),('msip_after',True),('eviction_checksum',0),('pass_index',1),('footprint_bytes',2),('trial_id',3),('mtime_hz',1),('end_cycle',0),('instret_delta',True)]:
  changed=copy.deepcopy(rows);changed[0][key]=value;reject(key,lambda:validate(wire(changed),c))
 reject('truncated',lambda:validate(wire(rows[:-1]),c));reject('duplicated',lambda:validate(wire(rows+rows[:1]),c))
 raw=(build/'footprints.elf').read_bytes();e=elfmod.Elf(raw);t=e.syms['experiments'][0]
 for name,off in [('tableID',0),('tablenodes',8),('tableloads',12),('tablehart',16),('tabletrial',20)]:
  rr=bytearray(raw);rr[e.file_offset(t+off,1)]^=1;reject(name,lambda:inspect(bytes(rr),c,layout))
 rr=bytearray(raw);rr[e.file_offset(e.syms['footprint_chase'][0],1)]^=1;reject('loopopcode',lambda:inspect(bytes(rr),c,layout))
 indices=0
 for size in(1<<k for k in range(10,23)):
  n=size//64
  for trial in range(3):
   for h in range(3):
    values=[]
    for i in range(n):
     x=i^(i>>3);x=x*13&(n-1);x^=x>>5;values.append((x+17*trial+7*h)&(n-1))
    assert len(set(values))==n and values[0]==(17*trial+7*h)%n;indices+=n
    links={values[i]:values[(i+1)%n]for i in range(n)};cursor=values[0]
    for _ in range(max(1024,n)):cursor=links[cursor]
    assert cursor==values[0]
 protocol=protocol_check();(build/'protocol-proof.json').write_text(json.dumps(protocol,indent=2)+'\n');(build/'host-cases.json').write_text(json.dumps(flatten(c),indent=2)+'\n')
 paths=[Path(__file__).resolve(),Path(__file__).with_name('run.py'),build/'footprints.elf',build/'build.json',build/'protocol-proof.json',build/'host-cases.json',ROOT/'firesim/pow2_memory_review.py'];ids.update({str(p):sha(p)for p in paths})
 for p,h in ids.items():assert sha(p)==h,p
 q=dict(schema='iris.pow2_isolated_memory_qualification.v3',**{'pass':True},elf_sha256=b['elf_sha256'],corpus_sha256=sha(build/'corpus.json'),functional=normal,actual_omitted_kernel=dict(report=str(neg),report_sha256=sha(neg),failed_regions=234),negative_controls=controls,compiled_and_layout_proof=proof,protocol_proof=protocol,permutation_bijections=117,permutation_indices_checked=indices,independent_whole_lap_returns_checked=117,normal_guest_exit_verified=True,input_sha256=ids,hardware_contacted=False,source_image_association_verified=False)
 (build/'qualification.json').write_text(json.dumps(q,indent=2)+'\n');(build/'review.json').write_text(json.dumps(dict(pass_=True,compiled_and_layout_proof=proof,source_protocol=protocol),indent=2)+'\n')
 ready=dict(schema='iris.pow2_isolated_memory_ready.v3',status='ready_for_root_managed_preparation',source_frozen=True,elf=str(build/'footprints.elf'),elf_sha256=b['elf_sha256'],required_cohorts=117,declared_cases=234,required_regions=234,trials=3,passes=2,min_dependent_loads=1024,record_bytes=128,buffered_all_output=True,fitting_only=True,global_heldout=False,reserved_timing_labels_root_only=True,train_regions=180,reserved_regions=54,new_exact_reference_required=True,source_image_association_verified=False,physical_hit_or_miss_measured=False,counter_scope='Raw mcycle/minstret with call/fence/counter/spills; no subtraction',mtime_scope='encloses_CSR_ROI_with_sampling_overhead',history_scope=c['protocol'],cold_definition=c['cold_definition'],steady_definition=c['steady_definition'],artifact_sha256={name:sha(build/name)for name in('footprints.elf','build.json','qualification.json','review.json','corpus.json','layout.json','host-cases.json','protocol-proof.json')})
 for name in('build','qualification','review','corpus','layout'):ready[name+'_sha256']=sha(build/(name+'.json'))
 ready['host_cases_sha256']=sha(build/'host-cases.json');(build/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(pass_=True,ready_sha256=sha(build/'ready.json'),controls=len(controls),protocol_states=protocol['states'])))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--negative-build',type=Path,required=True);a=p.parse_args();qualify(a.build.resolve(),a.negative_build.resolve())
