#!/usr/bin/env python3
import argparse,copy,json,struct,base64
from pathlib import Path
from build import ROOT,sha
from validate import validate,validate_corpus,checksum,validate_sections,validate_decoded
from codec import expand
from protocol import prove
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
     if name in('experiments','rvv_records','rvv_record_count','rvv_measurements_done','parked','completion','benchmark_main'):assert name not in self.syms;self.syms[name]=(address,size)
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
 validate_corpus(c);e=Elf(raw);table,size=e.syms['experiments'];assert size==1908*48
 kinds=['integer','fp','load','store','load_use','load_independent','store_compute','rowmove','matrix_int','matrix_fp8'];seen=set()
 for i,r in enumerate(c['cases']):
  name,*fields=struct.unpack('<Q10I',e.read(table+i*48,48));wanted=[r[k]for k in('kind_id','sew','lmul','mode','n','bytes','hart','trial_id','vl','streams')]
  assert e.string(name)==r['case_id']and fields==wanted and r['kind_id']==kinds.index(r['kind'])
  parent=f"rvv.identify.{r['kind']}.e{r['sew']}.m{r['lmul']}.mode{r['mode']}.n{r['n']}.b{r['bytes']}";assert r['semantic_parent_case_id']==parent and r['parent_case_id']==parent+f".hart{r['hart']}"and r['case_id']==parent+f".hart{r['hart']}.trial{r['trial_id']}"
  key=tuple(wanted);assert key not in seen;seen.add(key)
 objects={k:dict(address=e.syms[k][0],size=e.syms[k][1])for k in('rvv_records','rvv_record_count','rvv_measurements_done','parked','completion')};assert objects==layout['objects'];assert objects['rvv_records']['size']==1908*192 and objects['rvv_records']['address']%64==0 and objects['parked']['size']==384 and objects['completion']['size']==128
 assert layout['record_bytes']==192 and type(layout['record_bytes'])is int and layout['records']==1908 and len(layout['fields'])==17 and e.read(objects['rvv_measurements_done']['address'],8)==b'\xff'*8 and e.read(objects['completion']['address'],4)==bytes(4)
 spans=[(r['address'],r['address']+r['size'])for r in objects.values()];assert all(max(a,c)>=min(b,d)for i,(a,b)in enumerate(spans)for c,d in spans[i+1:]);assert all(objects[k]['address']%128==0 for k in('parked','completion'))
 return dict(compiled_case_records=1908,table_stride=48,compiled_geometry_counts_roles_and_unique_IDs=True,record_stride=192,record_fields=layout['fields'],buffer_objects=objects,source_count_loop_and_225888_per_element_goldens_verified=True,known_filebacked_sentinel=True,padded_controls_and_records_disjoint=True)
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
def flatten(c):
 validate_corpus(c);return[dict(id=r['case_id'],active_harts=[r['hart']],expected_checksums_by_hart=[r['expected_checksum']]*3,parent_case_id=r['parent_case_id'],semantic_parent_case_id=r['semantic_parent_case_id'],trial_id=r['trial_id'],region='kernel',suite='rvv_identify',internal_split=r['internal_split'],corpus_split='iris-rvv-identify-v1')for r in c['cases']]
def qualify(build,negative):
 c=json.loads((build/'corpus.json').read_text());b=json.loads((build/'build.json').read_text());layout=json.loads((build/'layout.json').read_text());raw=(build/'guest.elf').read_bytes();binary=inspect(raw,c,layout);phase=clint_proof(raw);ids=dict(b['input_sha256']);normal=[]
 for seed in(0,17):
  d=build/('seed%d'%seed);r=json.loads((d/'run.json').read_text());assert r['pass']is True and r['normal_guest_exit_verified']is True and r['exit_status']==0 and not r['timed_out'];v=validate((d/'stdout').read_text(),c);assert v['checked_words']==225888 and r['elf_sha256']==b['ELF_sha256'];ids.update(r['input_sha256']);ids.update({str(p):sha(p)for p in(d/'run.json',d/'stdout',d/'stderr')});normal.append(dict(seed=seed,report=str(d/'run.json'),report_sha256=sha(d/'run.json'),host_seconds=r['host_seconds']))
 neg=negative/'seed0/run.json';n=json.loads(neg.read_text());assert n['pass']is True and n['expect_negative']is True and not n['timed_out']and n['exit_status']!=0 and n['proof']==dict(actual_omitted_kernel_detected=True,failed_regions=1908);ids.update(n['input_sha256']);ids.update({str(p):sha(p)for p in(neg,neg.parent/'stdout',neg.parent/'stderr')})
 rows=[json.loads(l.split(' ',1)[1])for l in expand((build/'seed0/stdout').read_text(),c).splitlines()if l.startswith('IRIS_REGION ')];controls=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,AssertionError,KeyError,TypeError,struct.error):controls.append(dict(name=name,rejected=True))
  else:raise ValueError('Corruption admitted '+name)
 def wire(rr):
  lines=[]
  for i,r in enumerate(rr):
   lines.append('IRIS_REGION '+json.dumps(r))
   if i<len(c['cases'])and (i+1==len(c['cases'])or c['cases'][i+1]['hart']!=c['cases'][i]['hart']):
    h=c['cases'][i]['hart'];lines.append('IRIS_HART_SECTION '+json.dumps(dict(hart=h,regions=sum(x['hart']==h for x in c['cases']),failed=0)))
  return '\n'.join(lines)+'\nIRIS_BATCH_DONE {"failed":0,"cases":1908,"regions":1908,"trials":3}\n' 
 for key,value in [('hart',True),('kind',9),('sew',1),('lmul',3),('mode',17),('operations',1),('vl',0),('checked_words',True),('mismatch_or',1),('checksum',0),('expected_checksum',0),('msip_before',1),('msip_after',True),('end_cycle',0),('issue_instret_delta',0),('trial_id',3)]:
  changed=copy.deepcopy(rows);changed[0][key]=value;reject(key,lambda:validate_decoded(wire(changed),c))
 reject('truncated',lambda:validate_decoded(wire(rows[:-1]),c));reject('duplicated',lambda:validate_decoded(wire(rows+rows[:1]),c))
 e=Elf(raw);table=e.syms['experiments'][0]
 for name,off in [('tableID',0),('tablekind',8),('tablesew',12),('tablelmul',16),('tablen',24),('tablehart',32),('tableVL',40)]:
  changed=bytearray(raw);changed[e.offset(table+off,1)]^=1;reject(name,lambda:inspect(bytes(changed),c,layout))
 changed=bytearray(raw);changed[e.offset(phase['fence_between_issue_and_drain_pc'],1)]^=1;reject('compiled-phase-fence',lambda:clint_proof(bytes(changed)))
 actual_text=expand((build/'seed0/stdout').read_text(),c)
 lines=actual_text.splitlines();first_section=next(x for x in lines if x.startswith('IRIS_HART_SECTION '))
 reject('missing-hart-section',lambda:validate_decoded(actual_text.replace(first_section+'\n','',1),c))
 section=json.loads(first_section.split(' ',1)[1]);section['regions']-=1;reject('wrong-section-count',lambda:validate_decoded(actual_text.replace(first_section,'IRIS_HART_SECTION '+json.dumps(section),1),c))
 reject('section-before-rows',lambda:validate_decoded(first_section+'\n'+actual_text,c))
 changed=bytearray(raw);changed[e.offset(e.syms['completion'][0],1)]=1;reject('compiled-phase-zero',lambda:inspect(bytes(changed),c,layout))
 raw_text=(build/'seed0/stdout').read_text();first=next(l for l in raw_text.splitlines()if l.startswith('IRIS_BIN '));parts=first.split(' ');payload=base64.b64decode(parts[2]);assert len(payload)==136
 def changed_word(word,value):
  values=list(struct.unpack('<17Q',payload));values[word]=value;line=parts[0]+' '+parts[1]+' '+base64.b64encode(struct.pack('<17Q',*values)).decode();return raw_text.replace(first,line,1)
 reject('raw-wrong-caseindex',lambda:validate(raw_text.replace(first,first.replace('IRIS_BIN 0 ','IRIS_BIN 1 '),1),c))
 reject('raw-truncated-base64',lambda:validate(raw_text.replace(first,first[:-1],1),c))
 reject('raw-wrong-hart',lambda:validate(changed_word(1,2),c))
 reject('raw-changed-checksum',lambda:validate(changed_word(8,0),c))
 reject('raw-changed-mismatch',lambda:validate(changed_word(10,1),c))
 reject('raw-changed-VL',lambda:validate(changed_word(12,0),c))
 reject('raw-noncanonical-padbits',lambda:validate(raw_text.replace(first,first[:-3]+'B==',1),c))
 padded=parts[0]+' '+parts[1]+' '+base64.b64encode(payload+bytes(56)).decode();reject('raw-192B-padding',lambda:validate(raw_text.replace(first,padded,1),c))
 parent=ROOT/'build/rvv-identify-TK-v4/corpus.json';oldcases=json.loads(parent.read_text())['cases'];excluded=[r for r in oldcases if r['hart']==2 and r['kind']in('load','store')and r['bytes']==256];retained=[r for r in oldcases if r not in excluded]
 retained.sort(key=lambda r:r['hart'])
 assert len(excluded)==12 and retained==c['cases'] and all(r['internal_split']=='train'for r in excluded)
 assert sorted(r['case_id']for r in oldcases if r['internal_split']=='reserved_holdout')==sorted(r['case_id']for r in retained if r['internal_split']=='reserved_holdout')
 for kind in('load','store'):
  changed=copy.deepcopy(c);changed['cases'][0]=next(r for r in excluded if r['kind']==kind);reject('excluded-hart2-256B-'+kind,lambda:validate_corpus(changed))
 scope=dict(schema='iris.rvv_identify_1908_scope.v1',**{'pass':True},parent_corpus_sha256=sha(parent),retained_case_ID_geometry_and_goldens_identical=True,new_stable_hart_grouped_order=True,reserved_case_IDs_identical=True,excluded_case_IDs=[r['case_id']for r in excluded],excluded_all_TRAIN=True,removed_checked_words=768,retained_checked_words=225888,new_exact_reference_required=True,scope='Exclude hart2 256B standalone vector loads/stores only; observed load stall/store unqualified risk; not an illegal ISA claim or posthoc filtering.')
 (build/'scope-proof.json').write_text(json.dumps(scope,indent=2)+'\n');ids.update({str(p):sha(p)for p in[parent,ROOT/'build/rvv-identify-TK-v4/ready.json',ROOT/'calibration/rvv-identify-compact-v1/fit-plan.json',build/'scope-proof.json']})
 protocol=prove(Path(__file__).with_name('guest.c'));assert protocol['pass_']is True and protocol['deadlocks']==0 and protocol['foreign_writes_during_window']==0
 (build/'protocol-proof.json').write_text(json.dumps(protocol,indent=2)+'\n');(build/'host-cases.json').write_text(json.dumps(flatten(c),indent=2)+'\n');(build/'phase-proof.json').write_text(json.dumps(phase,indent=2)+'\n')
 paths=[Path(__file__).resolve(),Path(__file__).with_name('run.py'),build/'build.json',build/'guest.elf',build/'layout.json',build/'host-cases.json',build/'protocol-proof.json',build/'phase-proof.json',Path(__file__).with_name('protocol.py')];ids.update({str(p):sha(p)for p in paths})
 for p,h in ids.items():assert sha(p)==h,p
 reserved=sum(r['internal_split']=='reserved_holdout'for r in c['cases']);q=dict(schema='iris.rvv_identify_qualification.v1',**{'pass':True},ELF_sha256=sha(build/'guest.elf'),functional=normal,actual_omitted_kernel=dict(report=str(neg),report_sha256=sha(neg),failed_regions=1908),corruption_controls=controls,compiled_and_layout_proof=binary,compiled_counter_phase_proof=phase,per_element_words_checked_per_schedule=225888,quiet_hart_protocol=protocol,train_regions=1908-reserved,reserved_regions=reserved,normal_guest_exit_verified=True,input_sha256=ids,hardware_contacted=False)
 (build/'qualification.json').write_text(json.dumps(q,indent=2)+'\n');(build/'review.json').write_text(json.dumps(dict(pass_=True,compiled_and_layout_proof=binary),indent=2)+'\n')
 artifacts=['scope-proof.json','guest.elf','build.json','qualification.json','review.json','corpus.json','layout.json','host-cases.json','protocol-proof.json','phase-proof.json'];ready=dict(schema='iris.rvv_identify_ready.v1',status='ready_for_root_managed_preparation',source_frozen=True,ELF_sha256=sha(build/'guest.elf'),required_cases=1908,required_regions=1908,trials=3,all_output_after_measurements=False,all_output_after_own_hart_measurements=True,phase_handoffs=2,record_bytes=192,checked_words_per_schedule=225888,fitting_only=True,global_heldout=False,reserved_timing_labels_root_only=True,train_regions=1908-reserved,reserved_regions=reserved,new_exact_reference_required=True,physical_LSU_requests_or_TL_transactions_measured=False,source_image_association_verified=False,artifact_sha256={name:sha(build/name)for name in artifacts})
 (build/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(pass_=True,ready_sha256=sha(build/'ready.json'),reserved=reserved,controls=len(controls))))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--negative-build',type=Path,required=True);a=p.parse_args();qualify(a.build.resolve(),a.negative_build.resolve())
