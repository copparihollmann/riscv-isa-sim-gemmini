#!/usr/bin/env python3
"""Exact compiled target bodies, no-metadata ROI, counters and independent goldens."""
import argparse,copy,json,struct
from pathlib import Path
from build import ROOT,sha
from validate import validate,validate_corpus,checksum,expected_words
class Elf:
 def __init__(self,raw):
  self.raw=raw;self.loads=[];self.syms={};assert raw[:7]==b'\x7fELF\x02\x01\x01'and self.u('<H',18)[0]==243
  po=self.u('<Q',32)[0];ps,pn=self.u('<HH',54);assert ps==56
  for i in range(pn):
   t,f,o,v,p,fs,ms,a=self.u('<IIQQQQQQ',po+i*ps)
   if t==1:assert v==p and fs<=ms and o+fs<=len(raw)and 0x80000000<=p<p+ms<=0x180000000;self.loads.append((p,o,fs,ms))
  so=self.u('<Q',40)[0];ss,sn=self.u('<HH',58);assert ss==64;sections=[self.u('<IIQQQQIIQQ',so+i*ss)for i in range(sn)]
  for s in sections:
   if s[1]!=2:continue
   st=sections[s[6]];names=raw[st[4]:st[4]+st[5]];assert s[9]==24
   for at in range(s[4],s[4]+s[5],24):
    n,info,other,index,address,size=self.u('<IBBHQQ',at)
    if index and n:
     end=names.find(b'\0',n);assert end>=n;name=names[n:end].decode()
     if name.startswith('asm_') or name in('experiments','rvv_records','rvv_record_count','rvv_measurements_done','parked','completion','benchmark_main','emit','finish','_start'):assert name not in self.syms;self.syms[name]=(address,size)
 def u(self,fmt,off):assert 0<=off<=len(self.raw)-struct.calcsize(fmt);return struct.unpack_from(fmt,self.raw,off)
 def offset(self,a,n):
  matches=[o+a-b for b,o,fs,ms in self.loads if b<=a and a+n<=b+fs];assert len(matches)==1;return matches[0]
 def read(self,a,n):o=self.offset(a,n);return self.raw[o:o+n]
 def string(self,a):
  data=bytearray()
  for i in range(240):
   b=self.read(a+i,1)
   if not b[0]:return data.decode()
   data+=b
  raise ValueError('Unterminated ID')
def inspect(raw,c,layout):
 validate_corpus(c);e=Elf(raw);table,size=e.syms['experiments'];assert size==1320*48
 kinds=['integer','fp','load','store','load_use','load_independent','store_compute','rowmove','matrix_int','matrix_fp8'];seen=set()
 for i,r in enumerate(c['cases']):
  name,*fields=struct.unpack('<Q10I',e.read(table+i*48,48));wanted=[r[k]for k in('kind_id','sew','lmul','mode','n','bytes','hart','trial_id','vl','streams')]
  assert e.string(name)==r['case_id']and fields==wanted and r['kind_id']==kinds.index(r['kind'])
  parent=f"rvv.compute.heldout2.asm.v1.{r['kind']}.e{r['sew']}.m{r['lmul']}.mode{r['mode']}.n{r['n']}.b{r['bytes']}";assert r['semantic_parent_case_id']==parent and r['parent_case_id']==parent+f".hart{r['hart']}"and r['case_id']==parent+f".hart{r['hart']}.trial{r['trial_id']}"
  key=tuple(wanted);assert key not in seen;seen.add(key)
 objects={k:dict(address=e.syms[k][0],size=e.syms[k][1])for k in('rvv_records','rvv_record_count','rvv_measurements_done','parked','completion')};assert objects==layout['objects'];assert objects['rvv_records']['size']==1320*192 and objects['rvv_records']['address']%64==0 and objects['parked']['size']==384 and objects['completion']['size']==128
 assert layout['record_bytes']==192 and type(layout['record_bytes'])is int and layout['records']==1320 and len(layout['fields'])==17 and e.read(objects['rvv_measurements_done']['address'],8)==b'\xff'*8 and e.read(objects['completion']['address'],4)==bytes(4)
 spans=[(r['address'],r['address']+r['size'])for r in objects.values()];assert all(max(a,c)>=min(b,d)for i,(a,b)in enumerate(spans)for c,d in spans[i+1:]);assert all(objects[k]['address']%128==0 for k in('parked','completion'))
 return dict(compiled_case_records=1320,table_stride=48,compiled_geometry_counts_roles_and_unique_IDs=True,record_stride=192,record_fields=layout['fields'],buffer_objects=objects,source_count_loop_and_184128_per_element_goldens_verified=True,known_filebacked_sentinel=True,padded_controls_and_records_disjoint=True)
def instructions(e,name):
 start,size=e.syms[name];pc=start;out=[]
 while pc<start+size:
  half=int.from_bytes(e.read(pc,2),'little');n=4 if half&3==3 else 2
  out.append((pc,n,int.from_bytes(e.read(pc,n),'little')));pc+=n
 assert pc==start+size
 return out


BODY={
 'integer0':[0x02880457], 'integer1':[0x02880457,0x03880c57], 'integer2':[0x02880457,0x02880c57],
 'fp0':[0x02881457], 'fp1':[0x02881457,0x03881c57], 'fp2':[0x02881457,0x02881c57],
 'load':[0x0205e407], 'store':[0x02066427],
 'load_use':[0x0205e407,0x02880c57], 'load_independent':[0x0205e407,0x0380bc57], 'store_compute':[0x02066427,0x0380bc57],
 'matrix_int':[0xf2880077], 'matrix_fp8':[0xf2881077]}
def function(case):
 k=case['kind']
 return 'asm_'+(k+str(case['mode'])if k in('integer','fp')else'row'+str(case['n'])if k=='rowmove'else k)
def cb_imm(w):
 x=((w>>12)&1)<<8|((w>>10)&3)<<3|((w>>5)&3)<<6|((w>>3)&3)<<1|((w>>2)&1)<<5
 return x-512 if x&256 else x

def body_proof(raw,c):
 e=Elf(raw);bodies={}
 for name,body in BODY.items():
  symbol='asm_'+name;rows=instructions(e,symbol);target=body*16;assert [n for _,n,_ in rows[:len(target)]]==[4]*len(target)and[w for _,_,w in rows[:len(target)]]==target
  tail=rows[len(target):];assert len(tail)==3 and tail[0][1:]==(2,0x157d)and tail[2][1:]==(2,0x8082)
  pc,n,w=tail[1];assert n==2 and w&0xe383==0xe101 and pc+cb_imm(w)==e.syms[symbol][0]
  bodies[symbol]=dict(address=e.syms[symbol][0],bytes=e.syms[symbol][1],target_raw_per_iteration=body,unroll=16,static_target_instructions=len(target),loop_scalar_instructions=2,return_instructions=1,metadata_loads=0,scalar_data_accesses=0,loop_target=e.syms[symbol][0],line64_spans=sorted({p//64*64 for p,_,_ in rows}))
 for count in(3,12,48,192):
  symbol='asm_row'+str(count);rows=instructions(e,symbol);want=[]
  for j in range(count):want.extend([(2,0x4e01+((j&31)<<2)),(4,0x43fe6c57)])
  want.append((2,0x8082));assert [(n,w)for _,n,w in rows]==want
  bodies[symbol]=dict(address=e.syms[symbol][0],bytes=e.syms[symbol][1],static_target_instructions=count,row_TSS_indices=[j&31 for j in range(count)],scalar_index_instructions=count,return_instructions=1,metadata_loads=0,scalar_data_accesses=0,line64_spans=sorted({p//64*64 for p,_,_ in rows}))
 wrapper=instructions(e,'asm_measure');cy=[p for p,n,w in wrapper if n==4 and w&0x707f==0x2073 and w>>20==0xb00];ir=[p for p,n,w in wrapper if n==4 and w&0x707f==0x2073 and w>>20==0xb02]
 assert len(cy)==len(ir)==3 and cy[0]<ir[0]<ir[1]<cy[1]<ir[2]<cy[2]
 roi=[(p,n,w)for p,n,w in wrapper if cy[0]<=p<=cy[2]];assert [w for p,n,w in roi]==[0xb0002af3,0xb0202b73,0x000480e7,0xb0202bf3,0xb0002c73,0x0330000f,0xb0202cf3,0xb0002d73]
 assert e.read(cy[0]-10,10)==bytes.fromhex('b7c20002e13203ba0200')
 assert e.read(cy[2]+4,10)==bytes.fromhex('b7c20002e13283bd0200')
 stores=[]
 for pc,n,w in wrapper:
  if n==4 and w&0x707f==0x3023 and(w>>15)&31==8:stores.append(dict(pc=pc,offset=((w>>25)<<5)|((w>>7)&31)))
 assert [x['offset']for x in stores]==[16,24,32,40,48,56,104,112,120,128]
 phase=dict(mtime_address=0x0200bff8,mtime_before_pc=cy[0]-4,mcycle_begin_pc=cy[0],mcycle_issue_pc=cy[1],mcycle_drain_pc=cy[2],mtime_after_pc=cy[2]+10,real_minstret_read_pcs=ir,fence_between_issue_and_drain_pc=cy[1]+4,actual_static_order_verified=True,no_overhead_subtraction=True,measured_wrapper_raw=[w for _,_,w in roi],wrapper_scalar_data_loads_in_ROI=0,wrapper_scalar_data_stores_in_ROI=0,function_dispatch_and_args_before_first_CSR=True,measured_call_return_overhead_explicit=True)
 emit=instructions(e,'emit');assert not any(n==4 and(w&127==0x57 or w&127 in(7,39)and(w>>12)&7 in(0,5,6,7))for _,n,w in emit)
 main=instructions(e,'benchmark_main');assert not any(n==4 and w&127 in(7,39)and(w>>12)&7 in(0,5,6,7)and(w>>7)&31==1 for _,n,w in main)
 # Exact dynamic counts, including three CSR/call/return instructions in issue
 # and the final three retired CSR/FENCE instructions in the drain interval.
 cases=[];first=set()
 for case in c['cases']:
  fn=function(case);body=bodies[fn];n=case['n'];target=n*(len(BODY[fn[4:]])if case['kind']!='rowmove'else 1);scalar=n if case['kind']=='rowmove'else 2*(n//16)
  key=(case['hart'],fn);cases.append(dict(case_id=case['case_id'],hart=case['hart'],function=fn,target_instructions=target,scalar_loop_or_index_instructions=scalar,functional359_issue_instret_delta=target+scalar+2,functional359_drain_instret_delta=2,functional359_total_instret_delta=target+scalar+4,dynamic_kernel_plus_call_return_instructions=target+scalar+2,architectural_target_load_bytes=(n*case['bytes']if case['kind']in('load','load_use','load_independent')else 0),architectural_target_store_bytes=(n*case['bytes']if case['kind']in('store','store_compute')else 0),metadata_bytes_in_ROI=0,first_body_invocation_on_hart=key not in first));first.add(key)
 return dict(schema='iris.rvv_compute_asm_compiled_bodies.v1',**{'pass':True},bodies=bodies,compiled_counter_phase_proof=phase,per_case_counts=cases,emit_vector_instructions=0,all_wrapper_record_accesses_scalar=True,no_implicit_v1_block_copy=True,source_scope='ActualELFdecode andfunctionalminstret crosscheck; requestedarchitecturalpayload, notTLtransactions'),phase

def clint_proof(raw):
 # Kept stable for managed helper API; complete body proof is checked separately.
 e=Elf(raw);rows=instructions(e,'asm_measure');cy=[p for p,n,w in rows if n==4 and w&0x707f==0x2073 and w>>20==0xb00];ir=[p for p,n,w in rows if n==4 and w&0x707f==0x2073 and w>>20==0xb02]
 assert len(cy)==len(ir)==3 and e.read(cy[1]+4,4)==bytes.fromhex('0f003003')
 assert [w for p,n,w in rows if cy[0]<=p<=cy[2]]==[0xb0002af3,0xb0202b73,0x000480e7,0xb0202bf3,0xb0002c73,0x0330000f,0xb0202cf3,0xb0002d73]
 return dict(mtime_address=0x0200bff8,mtime_before_pc=cy[0]-4,mcycle_begin_pc=cy[0],mcycle_issue_pc=cy[1],mcycle_drain_pc=cy[2],mtime_after_pc=cy[2]+10,real_minstret_read_pcs=ir,fence_between_issue_and_drain_pc=cy[1]+4,actual_static_order_verified=True,no_overhead_subtraction=True,measured_wrapper_raw=[w for p,n,w in rows if cy[0]<=p<=cy[2]],wrapper_scalar_data_loads_in_ROI=0,wrapper_scalar_data_stores_in_ROI=0,function_dispatch_and_args_before_first_CSR=True,measured_call_return_overhead_explicit=True)
def flatten(c):
 validate_corpus(c);return[dict(id=r['case_id'],active_harts=[r['hart']],expected_checksums_by_hart=[r['expected_checksum']]*3,parent_case_id=r['parent_case_id'],semantic_parent_case_id=r['semantic_parent_case_id'],trial_id=r['trial_id'],region='kernel',suite='rvv_compute_heldout2_asm_v1',internal_split=r['internal_split'],corpus_split='iris-rvv-compute-heldout2-asm-v1')for r in c['cases']]
def qualify(b,n):
 c=json.loads((b/'corpus.json').read_text());built=json.loads((b/'build.json').read_text());layout=json.loads((b/'layout.json').read_text());raw=(b/'guest.elf').read_bytes()
 binary=inspect(raw,c,layout);wire,phase=body_proof(raw,c);ids=dict(built['input_sha256']);normal=[]
 for seed in(0,17):
  directory=ROOT/('build/rvv-compute-heldout2-asm-functional-seed%d-v1'%seed);r=json.loads((directory/'run.json').read_text())
  assert r['pass']is True and r['normal_guest_exit_verified']is True and r['exit_status']==0 and r['timed_out']is False and r['elf_sha256']==sha(b/'guest.elf')
  proof=validate((directory/'stdout').read_text(),c);assert proof['checked_words']==184128
  actual=[json.loads(x.split(' ',1)[1])for x in(directory/'stdout').read_text().splitlines()if x.startswith('IRIS_REGION ')]
  for observed,want in zip(actual,wire['per_case_counts']):
   assert observed['case_id']==want['case_id']and all(observed[k]==want['functional359_'+k]for k in('issue_instret_delta','drain_instret_delta'))
   assert observed['instret_delta']==want['functional359_total_instret_delta']
  for name,digest in r['input_sha256'].items():assert sha(name)==digest
  assert sha(directory/'stdout')==r['stdout_sha256']and sha(directory/'stderr')==r['stderr_sha256']
  normal.append(dict(seed=seed,report=str(directory/'run.json'),report_sha256=sha(directory/'run.json'),host_seconds=r['host_seconds']))
  ids.update(r['input_sha256']);ids.update({str(x):sha(x)for x in(directory/'run.json',directory/'stdout',directory/'stderr')})
 nd=ROOT/'build/rvv-compute-heldout2-asm-omission-seed0-v1';neg=json.loads((nd/'run.json').read_text());assert neg['pass']is True and neg['exit_status']!=0 and neg['timed_out']is False and neg['proof']==dict(actual_omitted_kernel_detected=True,failed_regions=1320)
 assert neg['elf_sha256']==sha(n/'guest.elf')
 ids.update(neg['input_sha256']);ids.update({str(x):sha(x)for x in(nd/'run.json',nd/'stdout',nd/'stderr')})
 rows=[json.loads(x.split(' ',1)[1])for x in (ROOT/'build/rvv-compute-heldout2-asm-functional-seed0-v1/stdout').read_text().splitlines()if x.startswith('IRIS_REGION ')]
 controls=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,AssertionError,KeyError,TypeError,struct.error):controls.append(dict(name=name,rejected=True))
  else:raise ValueError('Corruption admitted '+name)
 def text(rr):return '\n'.join('IRIS_REGION '+json.dumps(x)for x in rr)+'\nIRIS_BATCH_DONE {"failed":0,"cases":1320,"regions":1320,"trials":3}\n'
 for key,value in [('hart',2),('hart',True),('kind',7),('sew',1),('lmul',3),('mode',17),('operations',1),('vl',0),('checked_words',True),('mismatch_or',1),('checksum',0),('expected_checksum',0),('msip_before',1),('msip_after',True),('end_cycle',0),('start_cycle',True),('issue_instret_delta',0),('trial_id',3)]:
  rr=copy.deepcopy(rows);rr[0][key]=value;reject(key+str(value),lambda:validate(text(rr),c))
 reject('missing-last-trial',lambda:validate(text(rows[:-1]),c));reject('duplicate-first',lambda:validate(text(rows+rows[:1]),c))
 e=Elf(raw);table=e.syms['experiments'][0]
 for name,off in [('ID',0),('kind',8),('sew',12),('lmul',16),('n',24),('hart',32),('VL',40)]:
  rr=bytearray(raw);rr[e.offset(table+off,1)]^=1;reject('compiled-'+name,lambda:inspect(bytes(rr),c,layout))
 rr=bytearray(raw);rr[e.offset(phase['fence_between_issue_and_drain_pc'],1)]^=1;reject('compiled-ROI-fence',lambda:clint_proof(bytes(rr)))
 rr=bytearray(raw);rr[e.offset(e.syms['completion'][0],1)]=1;reject('compiled-phase-zero',lambda:inspect(bytes(rr),c,layout))
 for name in BODY:
  rr=bytearray(raw);at=e.offset(e.syms['asm_'+name][0],4);rr[at:at+4]=bytes.fromhex('13000000');reject('compiled-missing-target-'+name,lambda:body_proof(bytes(rr),c))
 rr=bytearray(raw);at=e.offset(e.syms['asm_integer0'][0],4);rr[at:at+4]=bytes.fromhex('03350500');reject('compiled-scalar-memory-in-target',lambda:body_proof(bytes(rr),c))
 scope=dict(schema='iris.rvv_compute_asm_scope.v1',**{'pass':True},parent_corpus_sha256=sha(ROOT/'build/rvv-compute-asm-v5/corpus.json'),parent_ELF_sha256=c['parent_ELF_sha256'],new1320_IDs_repeats_goldens_protected_split=True,active_harts=[0,1],permanently_parked_harts=[2],all3_boot_and_acknowledge=True,phase_handoffs=1,MSIP_wakeups=1,new_exact_ELF_history_reference_required=True,old_timing_transfer=False,source_image_association_verified=False)
 src=Path(__file__).with_name('guest.c').read_text();assert 'send_ipi(1)'in src and 'if(h==2){for(;;)__asm__ volatile("wfi");}'in src and src.index('rvv_measurements_done=0')<src.index('memory_fence();emit();') and src.count('emit();')==1 and 'record_t r='not in src and '=(record_t)'not in src
 protocol=dict(schema='iris.rvv_compute_asm_protocol.v1',**{'pass':True},source_sha256=sha(Path(__file__).with_name('guest.c')),all3_boot_and_acknowledge=True,active_hart_order=[0,1],inactive_hart2_permanent_WFI=True,one_MSIP_handoff=True,UART_between_measurement_phases=False,complete_buffer_done_sentinel_BEFORE_all_final_UART=True,all_output_scalar_volatile=True,actual_functional_schedules=[0,17],scope='Source protocol +actualseedednormalexit; notwholehardwareliveness')
 cache_policy=dict(schema='iris.rvv_compute_asm_cache_history.v1',selected_body_preexecuted_once=True,full_operand_tile_output_reset_and_fence_after_preexecution=True,physical_body_cache_hit_proven=False,actual_Icache_hits_measured=False,actual_data_cache_hits_measured=False,actual_cold_or_warm_claimed=False,all_trials_retained=True,subtraction_or_filter=False,body_policy='Activehartsetup thenexecutesselectedasmbodyoncewithoutCSRreads, thenrepeatsfulloperand/tile/output-poisonsetup+fenceBEFOREROI. Thisispreexecuted/resethistory,notprovenIcache/datahit; interveningsetupcanalterresidency. Perbodyfirstinvocationmarker ishistorymetadata,notahit/missclaim.',handoff='NoUARTbetweenhart0andhart1; all1320measurementsbeforefinalhart1emission; NEWexactreference/history.',per_case_body_history=[dict(case_id=x['case_id'],hart=x['hart'],function=x['function'],first_body_invocation_on_hart=x['first_body_invocation_on_hart'])for x in wire['per_case_counts']])
 (b/'cache-history.json').write_text(json.dumps(cache_policy,indent=2)+'\n')
 for name,value in [('scope-proof.json',scope),('protocol-proof.json',protocol),('phase-proof.json',phase),('scalar-wire-proof.json',wire),('host-cases.json',flatten(c)),('review.json',dict(pass_=True,compiled_and_layout_proof=binary))]:(b/name).write_text(json.dumps(value,indent=2)+'\n')
 paths=[Path(__file__).resolve(),Path(__file__).with_name('run.py'),b/'build.json',b/'guest.elf',b/'layout.json',*[b/x for x in('scope-proof.json','protocol-proof.json','phase-proof.json','scalar-wire-proof.json','host-cases.json','review.json','cache-history.json')]];ids.update({str(x):sha(x)for x in paths})
 for name,digest in ids.items():assert sha(name)==digest,name
 reserved=sum(x['internal_split']=='reserved_holdout'for x in c['cases']);q=dict(schema='iris.rvv_identify_qualification.v1',**{'pass':True},ELF_sha256=sha(b/'guest.elf'),functional=normal,actual_omitted_kernel=dict(report=str(nd/'run.json'),report_sha256=sha(nd/'run.json'),failed_regions=1320),corruption_controls=controls,compiled_and_layout_proof=binary,compiled_counter_phase_proof=phase,scalar_wire_proof=wire,per_element_words_checked_per_schedule=184128,quiet_hart_protocol=protocol,train_regions=1320-reserved,reserved_regions=reserved,normal_guest_exit_verified=True,input_sha256=ids,hardware_contacted=False)
 (b/'qualification.json').write_text(json.dumps(q,indent=2)+'\n')
 artifacts=['scope-proof.json','guest.elf','build.json','qualification.json','review.json','corpus.json','layout.json','host-cases.json','protocol-proof.json','phase-proof.json','scalar-wire-proof.json','cache-history.json'];ready=dict(schema='iris.rvv_identify_ready.v1',status='ready_for_root_managed_preparation',source_frozen=True,ELF_sha256=sha(b/'guest.elf'),required_cases=1320,required_regions=1320,trials=3,all_output_after_measurements=True,all_output_after_own_hart_measurements=True,phase_handoffs=1,record_bytes=192,checked_words_per_schedule=184128,fitting_only=False,global_heldout=True,protected_validation_only=True,reserved_timing_labels_root_only=True,train_regions=1320-reserved,reserved_regions=reserved,new_exact_reference_required=True,physical_LSU_requests_or_TL_transactions_measured=False,source_image_association_verified=False,artifact_sha256={name:sha(b/name)for name in artifacts})
 (b/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(pass_=True,ready_sha256=sha(b/'ready.json'),reserved=reserved,controls=len(controls))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--negative-build',type=Path,required=True);a=p.parse_args();qualify(a.build.resolve(),a.negative_build.resolve())
