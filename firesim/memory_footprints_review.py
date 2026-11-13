#!/usr/bin/env python3
"""Additive ELF-table/layout admission proof; original footprint inputs unchanged."""
import argparse,copy,hashlib,importlib.util,json,shutil,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PARENT_READY='bbf83dafad627f1a0379b38e1a4846a16572b69e888b896f6e104e75d78eb5a4'
ELF='c08adebd1852aab4ee6f1b508eb2c208d46b10a0e4eb9304973c7112a920981d'
SIZES=(2048,16384,131072,1048576,4194304)
def need(x,why):
 if not x:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def hb(x):return hashlib.sha256(x).hexdigest()
def validator():
 p=ROOT/'benchmarks/memory_footprints/validate.py';s=importlib.util.spec_from_file_location('frozen_footprint_validator',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class Elf:
 def __init__(self,raw):
  self.raw=raw;need(raw[:7]==b'\x7fELF\x02\x01\x01'and self.unpack('<H',18)[0]==243,'ELF64LE RISC-V');po=self.unpack('<Q',32)[0];ps,pn=self.unpack('<HH',54);need(ps==56 and pn>0,'ELFprogramheader');self.loads=[]
  for i in range(pn):
   f=self.unpack('<IIQQQQQQ',po+i*ps)
   if f[0]!=1:continue
   typ,flags,off,va,pa,fs,ms,align=f;need(va==pa and fs<=ms and off+fs<=len(raw),'Physicalfile-backed ELFbounds');need(0x80000000<=pa and pa+ms<=0x180000000,'ELFwithin declaredDRAM')
   need(all(not(max(pa,b)<min(pa+ms,b+4194304))for b in(0x90000000,0x92000000,0x94000000)),'ELFoverlap footprintwindow');self.loads.append((pa,off,fs,ms))
  so=self.unpack('<Q',40)[0];ss,sn=self.unpack('<HH',58);need(ss==64 and sn>0,'ELFsectionheader');secs=[self.unpack('<IIQQQQIIQQ',so+i*ss)for i in range(sn)];self.syms={}
  for s in secs:
   if s[1]!=2:continue
   need(s[9]==24 and s[5]%24==0 and s[6]<sn,'ELFsymboltable');st=secs[s[6]];names=raw[st[4]:st[4]+st[5]]
   for pos in range(s[4],s[4]+s[5],24):
    name,info,other,index,address,size=self.unpack('<IBBHQQ',pos)
    if not index or not name:continue
    end=names.find(b'\0',name);need(0<name<len(names)and end>=name,'ELFsymbolname');key=names[name:end].decode();value=(address,size)
    if key in['experiments','footprint_chase','footprint_records','footprint_record_count','footprint_measurements_done']:
     need(key not in self.syms or self.syms[key]==value,'AmbiguousELFsymbol');self.syms[key]=value
 def unpack(self,fmt,p):need(0<=p<=len(self.raw)-struct.calcsize(fmt),'ELFfieldbounds');return struct.unpack_from(fmt,self.raw,p)
 def read(self,address,n):
  rows=[(b,o)for b,o,fs,ms in self.loads if b<=address and address+n<=b+fs];need(n>=0 and len(rows)==1,'ELFfile-backedread');b,o=rows[0];return self.raw[o+address-b:o+address-b+n]
 def string(self,address):
  out=bytearray()
  for i in range(256):
   b=self.read(address+i,1)
   if b==b'\0':return out.decode()
   out+=b
  raise ValueError('UnterminatedcaseID')
 def file_offset(self,address,n):
  rows=[o+address-b for b,o,fs,ms in self.loads if b<=address and address+n<=b+fs];need(len(rows)==1,'Filebackedoffset');return rows[0]
def inspect(raw,corpus,layout):
 validator().validate_corpus(corpus);e=Elf(raw);table,bytes_=e.syms['experiments'];need(bytes_==105*24,'Actualcompiled105x24table');rows=[]
 for i,c in enumerate(corpus['cases']):
  name,nodes,mask,trial=struct.unpack('<QIII4x',e.read(table+i*24,24));need(e.string(name)==c['case_id']and (nodes,mask,trial)==(c['nodes'],c['mask'],c['trial_id']),'Compiledcaseorder/shape/mask/trial');rows.append(dict(case_index=i,case_id=c['case_id'],address=table+i*24,nodes=nodes,mask=mask,trial=trial))
 addr,size=e.syms['footprint_chase'];body=struct.pack('<IIII',0x00053503,0xfff58593,0xfe059ce3,0x00008067);need(size==16 and addr%4==0 and e.read(addr,size)==body,'ExactdependentLDloopbody')
 objects={name:dict(address=e.syms[name][0],size=e.syms[name][1])for name in['footprint_records','footprint_record_count','footprint_measurements_done']}
 need(layout.get('objects')==objects and all(type(x)is int for row in layout['objects'].values()for x in row.values()),'Actualbufferobjectlayout')
 need(objects['footprint_records']['size']==360*64 and objects['footprint_record_count']['size']==objects['footprint_measurements_done']['size']==8,'ActualbufferABI')
 intervals=[(row['address'],row['address']+row['size'])for row in objects.values()]
 need(all(max(a,c)>=min(b,d)for i,(a,b)in enumerate(intervals)for c,d in intervals[i+1:]),'Buffernonoverlap')
 for key,value in [('record_bytes',64),('records',360),('stop_sentinel_initial_value',2**64-1),('stop_sentinel_complete_value',0)]:need(type(layout.get(key))is int and layout[key]==value,'Typedlayout '+key)
 need(layout['fields']==['case_index','pass','hart','start','end','instret','checksum','expected']and layout['intentional_debugger_stop_is_normal_guest_exit']is False,'ReadbackABI/scope');need(e.read(objects['footprint_measurements_done']['address'],8)==b'\xff'*8,'Actualknownfile-backed sentinel')
 need(layout['elf_sha256']==hb(raw),'LayoutELFidentity');return dict(compiled_table=rows,compiled_case_records=105,compiled_table_stride=24,loop=dict(address=addr,bytes=16,sha256=hb(body),instructions=['ld a0,0(a0)','addi a1,a1,-1','bne a1,zero,-8','ret']),buffer_objects=objects,record_stride=64,record_array_alignment_bytes=8,record_array_64B_alignment_claimed=False,target_windows=dict(base_by_hart=[0x90000000,0x92000000,0x94000000],bytes_each_max=4194304),no_ELF_target_overlap=True,sentinel_file_bytes_verified=True)
def flatten(corpus):
 validator().validate_corpus(corpus);cases=[]
 for c in corpus['cases']:
  for p in range(2):cases.append(dict(id=c['case_id']+'.pass'+str(p),active_harts=c['active_harts'],expected_checksums_by_hart=c['expected_checksums_by_hart'],parent_case_id=c['case_id'],semantic_parent_case_id=c['semantic_parent_case_id'],trial_id=c['trial_id'],pass_index=p,region='chase',suite='memory_footprints',corpus_split=corpus['split_id'],internal_split=c['internal_split']))
 need(len(cases)==210 and sum(len(c['active_harts'])for c in cases)==360,'Flatten105cohorts*2passes');return cases
def review(parent,out):
 need(not out.exists(),'Freshreview packet');out.mkdir(parents=True);need(sha(parent/'ready.json')==PARENT_READY,'Exactparentv3ready');ready=json.loads((parent/'ready.json').read_text());built=json.loads((parent/'build.json').read_text());q=json.loads((parent/'qualification.json').read_text());corpus=json.loads((parent/'corpus.json').read_text());layout=json.loads((parent/'layout.json').read_text());raw=(parent/'footprints.elf').read_bytes();need(hb(raw)==ELF==ready['elf_sha256'],'Exactapprovedv3ELF');proof=inspect(raw,corpus,layout);cases=flatten(corpus);controls=[]
 def reject(name,body,meta):
  try:inspect(body,corpus,meta)
  except(ValueError,KeyError,TypeError,struct.error):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Corruptionaccepted '+name)
 e=Elf(raw);t=e.syms['experiments'][0]
 for name,off in [('tableIDpointer',0),('tablenodes',8),('tablemask',12),('tabletrial',16)]:
  b=bytearray(raw);p=e.file_offset(t+off,1);b[p]^=1;reject(name,bytes(b),dict(layout,elf_sha256=hb(b)))
 b=bytearray(raw);p=e.file_offset(e.syms['footprint_chase'][0],1);b[p]^=1;reject('loopopcode',bytes(b),dict(layout,elf_sha256=hb(b)))
 b=bytearray(raw);p=e.file_offset(e.syms['footprint_measurements_done'][0],1);b[p]=0;reject('sentinelbyte',bytes(b),dict(layout,elf_sha256=hb(b)))
 bad=copy.deepcopy(layout);bad['objects']['footprint_records']['size']-=64;reject('recordarraysize',raw,bad)
 bad=copy.deepcopy(layout);bad['record_bytes']=True;reject('recordstrideboolean',raw,bad)
 ids={str(Path(__file__).resolve()):sha(__file__)}
 for name in['ready.json','build.json','qualification.json','layout.json','corpus.json','cases.inc','footprints.elf']:ids[str(parent/name)]=sha(parent/name);shutil.copyfile(parent/name,out/('parent-ready.json'if name=='ready.json'else name))
 for mapping in[built['input_sha256'],q['input_sha256']]:
  for p,d in mapping.items():need(sha(p)==d,'Parentsourcechanged '+p);need(p not in ids or ids[p]==d,'Conflictingparentsource');ids[p]=d
 for entry in q['functional']:
  p=Path(entry['report']);r=json.loads(p.read_text());need(sha(p)==entry['report_sha256']and r['pass']is True and r['normal_guest_exit_verified']is True and r['exit_status']==0 and r['elf_sha256']==ELF,'Actualseededparentrun');validator().validate((p.parent/'stdout').read_text(),corpus)
 report=dict(schema='iris.memory_footprint_additive_source_binary_review.v1',**{'pass':True},parent_ready_sha256=PARENT_READY,ELF_sha256=ELF,no_source_or_ELF_recompile_or_change=True,compiled_and_layout_proof=proof,flattened_host_cases=210,cohorts=105,regions=360,source_findings=['Permutationis bijective on each poweroftwo nodecount; N dependentloads returnthe initialnode','All3harts prepare disjointfootprints oncepersize/trial; masks1..7 andbothpassesretainhistory','Inactiveharts use IRQmasked WFI+IPI publication; sourcecomplete/barrier accounting consistent','Counterregions includefence/call/counters; noinferredoverheadsubtraction','No flush or physicallyobservedcachehit/DRAMmiss claim'],corruption_controls=controls,input_sha256=ids,physical_miss_or_traffic_measured=False,fitting_only=True,global_heldout=False,hardware_contacted=False);(out/'review.json').write_text(json.dumps(report,indent=2)+'\n');(out/'host-cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 packet=dict(schema='iris.memory_footprint_reviewed_ready.v1',status='ready_for_root_managed_preparation',source_frozen=True,parent_ready_sha256=PARENT_READY,parent_ready_packet=str(parent/'ready.json'),elf=str(out/'footprints.elf'),elf_sha256=ELF,corpus_sha256=sha(out/'corpus.json'),build_sha256=sha(out/'build.json'),qualification_sha256=sha(out/'qualification.json'),layout_sha256=sha(out/'layout.json'),review_sha256=sha(out/'review.json'),host_cases_sha256=sha(out/'host-cases.json'),required_cohorts=105,declared_cases=210,required_regions=360,trials=3,passes=2,fitting_only=True,global_heldout=False,new_exact_reference_required=True,source_image_association_verified=False,original_v3_ELF_preserved=True);(out/'ready.json').write_text(json.dumps(packet,indent=2)+'\n');return packet
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=review(a.parent.resolve(),a.output.resolve());print(json.dumps(dict(status=r['status'],ready_sha256=sha(a.output/'ready.json'),ELF_sha256=ELF)))
