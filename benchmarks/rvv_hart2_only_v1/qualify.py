#!/usr/bin/env python3
"""Independent compiled-table, scalar wire, exact subset and phase checks."""
import argparse,copy,json,struct,re
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
     if name in('experiments','rvv_records','rvv_record_count','rvv_measurements_done','parked','completion','benchmark_main','emit','finish','_start'):assert name not in self.syms;self.syms[name]=(address,size)
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
 validate_corpus(c);e=Elf(raw);table,size=e.syms['experiments'];assert size==588*48
 kinds=['integer','fp','load','store','load_use','load_independent','store_compute','rowmove','matrix_int','matrix_fp8'];seen=set()
 for i,r in enumerate(c['cases']):
  name,*fields=struct.unpack('<Q10I',e.read(table+i*48,48));wanted=[r[k]for k in('kind_id','sew','lmul','mode','n','bytes','hart','trial_id','vl','streams')]
  assert e.string(name)==r['case_id']and fields==wanted and r['kind_id']==kinds.index(r['kind'])
  parent=f"rvv.identify.{r['kind']}.e{r['sew']}.m{r['lmul']}.mode{r['mode']}.n{r['n']}.b{r['bytes']}";assert r['semantic_parent_case_id']==parent and r['parent_case_id']==parent+f".hart{r['hart']}"and r['case_id']==parent+f".hart{r['hart']}.trial{r['trial_id']}"
  key=tuple(wanted);assert key not in seen;seen.add(key)
 objects={k:dict(address=e.syms[k][0],size=e.syms[k][1])for k in('rvv_records','rvv_record_count','rvv_measurements_done','parked','completion')};assert objects==layout['objects'];assert objects['rvv_records']['size']==588*192 and objects['rvv_records']['address']%64==0 and objects['parked']['size']==384 and objects['completion']['size']==128
 assert layout['record_bytes']==192 and type(layout['record_bytes'])is int and layout['records']==588 and len(layout['fields'])==17 and e.read(objects['rvv_measurements_done']['address'],8)==b'\xff'*8 and e.read(objects['completion']['address'],4)==bytes(4)
 spans=[(r['address'],r['address']+r['size'])for r in objects.values()];assert all(max(a,c)>=min(b,d)for i,(a,b)in enumerate(spans)for c,d in spans[i+1:]);assert all(objects[k]['address']%128==0 for k in('parked','completion'))
 return dict(compiled_case_records=588,table_stride=48,compiled_geometry_counts_roles_and_unique_IDs=True,record_stride=192,record_fields=layout['fields'],buffer_objects=objects,source_count_loop_and_41760_per_element_goldens_verified=True,known_filebacked_sentinel=True,padded_controls_and_records_disjoint=True)
def clint_proof(raw):
 e=Elf(raw);start,size=e.syms['benchmark_main'];pc=start;instructions=[]
 while pc<start+size:
  half=struct.unpack('<H',e.read(pc,2))[0];length=4 if half&3==3 else 2;word=int.from_bytes(e.read(pc,length),'little');instructions.append((pc,length,word));pc+=length
 cycles=[p for p,n,w in instructions if n==4 and w&0x707f==0x2073 and w>>20==0xb00]
 retired=[p for p,n,w in instructions if n==4 and w&0x707f==0x2073 and w>>20==0xb02]
 assert len(cycles)==len(retired)==3 and cycles[0]<retired[0]<retired[1]<cycles[1]<retired[2]<cycles[2]
 fences=[p for p,n,w in instructions if w==0x0330000f and cycles[1]<p<cycles[2]];assert len(fences)==1
 loads=[]
 for p,n,w in instructions:
  if n==4 and w&0xfffff07f==0x0200c037:
   rd=(w>>7)&31
   if 8<=rd<=15 and struct.unpack('<H',e.read(p+4,2))[0]==(0x1000|(rd<<7)|(24<<2)|1) and struct.unpack('<H',e.read(p+6,2))[0]==(0x6000|((rd-8)<<7)|((rd-8)<<2)):loads.append(p+6)
 before=[p for p in loads if cycles[0]-32<=p<cycles[0]];after=[p for p in loads if cycles[2]<p<=cycles[2]+32];assert len(before)==len(after)==1
 return dict(mtime_address=0x0200bff8,mtime_before_pc=before[0],mcycle_begin_pc=cycles[0],mcycle_issue_pc=cycles[1],mcycle_drain_pc=cycles[2],mtime_after_pc=after[0],real_minstret_read_pcs=retired,fence_between_issue_and_drain_pc=fences[0],actual_static_order_verified=True,no_overhead_subtraction=True)

def instructions(e,name):
 start,size=e.syms[name];pc=start;out=[]
 while pc<start+size:
  half=int.from_bytes(e.read(pc,2),'little');n=4 if half&3==3 else 2
  out.append((pc,n,int.from_bytes(e.read(pc,n),'little')));pc+=n
 assert pc==start+size
 return out

def scalar_wire_proof(raw):
 e=Elf(raw);emit=instructions(e,'emit');main=instructions(e,'benchmark_main')
 # Reject vector arithmetic/config and vector-memory instructions in output.
 def vector(n,w):return n==4 and (w&127==0x57 or (w&127 in(7,39) and (w>>12)&7 in(0,5,6,7)))
 assert not any(vector(n,w) for _,n,w in emit)
 # Parent accidental block-copy used v1; all explicit kernels use v8/v16/v24.
 assert not any(n==4 and w&127 in(7,39) and (w>>12)&7 in(0,5,6,7) and (w>>7)&31==1 for _,n,w in main)
 stores=[]
 for pc,n,w in main:
  if n==4 and w&0x707f==0x3023 and (w>>15)&31==6:
   off=((w>>25)<<5)|((w>>7)&31)
   if off in range(0,136,8):stores.append((pc,off))
 assert [x[1]for x in stores]==list(range(0,136,8))
 # Actual startup branch: li a5,1; bgeu a5,a0 -> WFI self-loop.
 branches=[]
 for j,(pc,n,w)in enumerate(main):
  if n==4 and w&0x707f==0x7063 and (w>>15)&31==15 and (w>>20)&31==10:
   assert j and main[j-1][2]==0x4785
   imm=((w>>31)<<12)|(((w>>7)&1)<<11)|(((w>>25)&63)<<5)|(((w>>8)&15)<<1)
   if imm&4096:imm-=8192
   dst=pc+imm;assert e.read(dst,10)==bytes.fromhex('7300501073005010e5bf')
   branches.append(dict(branch_pc=pc,park_WFI_pc=dst,roles='unsigned hart<=1 parks forever; hart2 proceeds'))
 assert len(branches)==1
 firstvec=min(pc for pc,n,w in main if vector(n,w))
 assert branches[0]['branch_pc']<firstvec
 return dict(emit_address=e.syms['emit'][0],emit_bytes=e.syms['emit'][1],emit_vector_instructions=0,scalar_record_stores=[dict(pc=pc,offset=off)for pc,off in stores],record_scalar_fields=17,no_implicit_v1_block_copy=True,permanent_park=branches,boot_all3_before_hart2=True,scope='Static compiled branch/readiness protocol and actual seeded numerical executions; not a hardware PC/stall claim.')

def flatten(c):
 validate_corpus(c)
 return[dict(id=r['case_id'],active_harts=[2],expected_checksums_by_hart=[r['expected_checksum']]*3,parent_case_id=r['parent_case_id'],semantic_parent_case_id=r['semantic_parent_case_id'],trial_id=r['trial_id'],region='kernel',suite='rvv_identify',internal_split=r['internal_split'],corpus_split='iris-rvv-identify-v1')for r in c['cases']]

def qualify(b,n):
 c=json.loads((b/'corpus.json').read_text());built=json.loads((b/'build.json').read_text());layout=json.loads((b/'layout.json').read_text());raw=(b/'guest.elf').read_bytes()
 binary=inspect(raw,c,layout);phase=clint_proof(raw);wire=scalar_wire_proof(raw);ids=dict(built['input_sha256']);normal=[]
 for seed in(0,17):
  directory=ROOT/('build/rvv-hart2-only-functional-seed%d-v1'%seed);r=json.loads((directory/'run.json').read_text())
  assert r['pass']is True and r['normal_guest_exit_verified']is True and r['exit_status']==0 and r['timed_out']is False and r['elf_sha256']==sha(b/'guest.elf')
  proof=validate((directory/'stdout').read_text(),c);assert proof['checked_words']==41760
  for name,digest in r['input_sha256'].items():assert sha(name)==digest
  assert sha(directory/'stdout')==r['stdout_sha256']and sha(directory/'stderr')==r['stderr_sha256']
  normal.append(dict(seed=seed,report=str(directory/'run.json'),report_sha256=sha(directory/'run.json'),host_seconds=r['host_seconds']))
  ids.update(r['input_sha256']);ids.update({str(x):sha(x)for x in(directory/'run.json',directory/'stdout',directory/'stderr')})
 nd=ROOT/'build/rvv-hart2-only-omission-seed0-v1';neg=json.loads((nd/'run.json').read_text());assert neg['pass']is True and neg['exit_status']!=0 and neg['timed_out']is False and neg['proof']==dict(actual_omitted_kernel_detected=True,failed_regions=588)
 assert neg['elf_sha256']==sha(n/'guest.elf')
 ids.update(neg['input_sha256']);ids.update({str(x):sha(x)for x in(nd/'run.json',nd/'stdout',nd/'stderr')})
 rows=[json.loads(x.split(' ',1)[1])for x in (ROOT/'build/rvv-hart2-only-functional-seed0-v1/stdout').read_text().splitlines()if x.startswith('IRIS_REGION ')]
 controls=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,AssertionError,KeyError,TypeError,struct.error):controls.append(dict(name=name,rejected=True))
  else:raise ValueError('Corruption admitted '+name)
 def text(rr):return '\n'.join('IRIS_REGION '+json.dumps(x)for x in rr)+'\nIRIS_BATCH_DONE {"failed":0,"cases":588,"regions":588,"trials":3}\n'
 for key,value in [('hart',0),('hart',True),('kind',7),('sew',1),('lmul',3),('mode',17),('operations',1),('vl',0),('checked_words',True),('mismatch_or',1),('checksum',0),('expected_checksum',0),('msip_before',1),('msip_after',True),('end_cycle',0),('start_cycle',True),('issue_instret_delta',0),('trial_id',3)]:
  rr=copy.deepcopy(rows);rr[0][key]=value;reject(key+str(value),lambda:validate(text(rr),c))
 reject('missing-last-trial',lambda:validate(text(rows[:-1]),c));reject('duplicate-first',lambda:validate(text(rows+rows[:1]),c))
 e=Elf(raw);table=e.syms['experiments'][0]
 for name,off in [('ID',0),('kind',8),('sew',12),('lmul',16),('n',24),('hart',32),('VL',40)]:
  rr=bytearray(raw);rr[e.offset(table+off,1)]^=1;reject('compiled-'+name,lambda:inspect(bytes(rr),c,layout))
 rr=bytearray(raw);rr[e.offset(phase['fence_between_issue_and_drain_pc'],1)]^=1;reject('compiled-ROI-fence',lambda:clint_proof(bytes(rr)))
 rr=bytearray(raw);rr[e.offset(e.syms['completion'][0],1)]=1;reject('compiled-phase-zero',lambda:inspect(bytes(rr),c,layout))
 rr=bytearray(raw);at=e.offset(wire['emit_address'],4);rr[at:at+4]=bytes.fromhex('57000000');reject('compiled-vector-output',lambda:scalar_wire_proof(bytes(rr)))
 rr=bytearray(raw);at=e.offset(wire['scalar_record_stores'][0]['pc'],4);rr[at:at+4]=bytes.fromhex('13000000');reject('compiled-missing-scalar-field',lambda:scalar_wire_proof(bytes(rr)))
 scope=dict(schema='iris.rvv_hart2_only_scope.v1',**{'pass':True},parent_corpus_sha256=sha(ROOT/'build/rvv-identify-compact-v1/corpus.json'),parent_ELF_sha256=c['parent_ELF_sha256'],exact588_parent_case_IDs_geometry_goldens_splits_order=True,active_hart=2,permanently_parked_harts=[0,1],all3_boot_and_acknowledge=True,phase_handoffs=0,MSIP_wakeups=0,retained_hart2_LSU256_exclusion=True,new_exact_ELF_history_reference_required=True,old_timing_transfer=False,source_image_association_verified=False)
 protocol=dict(schema='iris.rvv_hart2_only_protocol.v1',**{'pass':True},source_sha256=sha(Path(__file__).with_name('guest.c')),compiled_role_proof=wire['permanent_park'],acknowledgements_before_active_loop=[0,1],inactive_harts_permanent_WFI=True,no_postmeasurement_phase_handoff=True,no_postmeasurement_vector_record_copy=True,actual_functional_schedules=[0,17],source_scope='Readiness is release/acquire; no MSIP sets; startup clears own MSIP and disables own timer. Functional schedules prove normal completion, not whole-hardware liveness.')
 for name,value in [('scope-proof.json',scope),('protocol-proof.json',protocol),('phase-proof.json',phase),('scalar-wire-proof.json',wire),('host-cases.json',flatten(c)),('review.json',dict(pass_=True,compiled_and_layout_proof=binary))]:(b/name).write_text(json.dumps(value,indent=2)+'\n')
 paths=[Path(__file__).resolve(),Path(__file__).with_name('run.py'),b/'build.json',b/'guest.elf',b/'layout.json',*[b/x for x in('scope-proof.json','protocol-proof.json','phase-proof.json','scalar-wire-proof.json','host-cases.json','review.json')]];ids.update({str(x):sha(x)for x in paths})
 for name,digest in ids.items():assert sha(name)==digest,name
 reserved=sum(x['internal_split']=='reserved_holdout'for x in c['cases']);q=dict(schema='iris.rvv_identify_qualification.v1',**{'pass':True},ELF_sha256=sha(b/'guest.elf'),functional=normal,actual_omitted_kernel=dict(report=str(nd/'run.json'),report_sha256=sha(nd/'run.json'),failed_regions=588),corruption_controls=controls,compiled_and_layout_proof=binary,compiled_counter_phase_proof=phase,scalar_wire_proof=wire,per_element_words_checked_per_schedule=41760,quiet_hart_protocol=protocol,train_regions=588-reserved,reserved_regions=reserved,normal_guest_exit_verified=True,input_sha256=ids,hardware_contacted=False)
 (b/'qualification.json').write_text(json.dumps(q,indent=2)+'\n')
 artifacts=['scope-proof.json','guest.elf','build.json','qualification.json','review.json','corpus.json','layout.json','host-cases.json','protocol-proof.json','phase-proof.json','scalar-wire-proof.json'];ready=dict(schema='iris.rvv_identify_ready.v1',status='ready_for_root_managed_preparation',source_frozen=True,ELF_sha256=sha(b/'guest.elf'),required_cases=588,required_regions=588,trials=3,all_output_after_measurements=True,all_output_after_own_hart_measurements=True,phase_handoffs=0,record_bytes=192,checked_words_per_schedule=41760,fitting_only=True,global_heldout=False,reserved_timing_labels_root_only=True,train_regions=588-reserved,reserved_regions=reserved,new_exact_reference_required=True,physical_LSU_requests_or_TL_transactions_measured=False,source_image_association_verified=False,artifact_sha256={name:sha(b/name)for name in artifacts})
 (b/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(pass_=True,ready_sha256=sha(b/'ready.json'),reserved=reserved,controls=len(controls))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--negative-build',type=Path,required=True);a=p.parse_args();qualify(a.build.resolve(),a.negative_build.resolve())
