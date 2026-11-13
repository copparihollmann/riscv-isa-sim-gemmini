#!/usr/bin/env python3
"""Independent compiled matrix table/numeric golden/source closure; no hardware."""
import argparse,copy,hashlib,importlib.util,json,shutil,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ELF='e838e1c645b684aedbb9e1e474a9f3a22e0ff31274835d3fcb5ccb6d67e74338'
def need(x,why):
 if not x:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validator():
 p=ROOT/'benchmarks/pow2_matrix_v1/validate.py';spec=importlib.util.spec_from_file_location('matrix_oracle',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
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
    if key in['cases','kernel','matrix_records','matrix_measurements_done']:
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
def inspect(raw,corpus,golden):
 validator().check_corpus(corpus,golden);e=Elf(raw);address,size=e.syms['cases'];need(size==132*40,'Compiled132x40table');proof=[]
 for i,c in enumerate(corpus['cases']):
  ptr,m,n,k,fp8,h,trial,checksum=struct.unpack('<Q6IQ',e.read(address+40*i,40));need(e.string(ptr)==c['id']and(m,n,k,fp8,h,trial,checksum)==tuple(c[x]for x in('m','n','k','fp8','hart','trial','checksum')),'Actual compiled shape/dtype/hart/trial/golden');proof.append(dict(case_id=c['id'],address=address+40*i))
 kaddr,ksize=e.syms['kernel'];code=e.read(kaddr,ksize)
 # Both real sf.mm forms exist in the compiled kernel, not a scalar stand-in.
 for word in (0xf28800f7,0xf2881077):need(struct.pack('<I',word)in code,'Actual signedINT8/FP8 MAC opcode')
 raddr,rsize=e.syms['matrix_records'];saddr,ssize=e.syms['matrix_measurements_done'];need(rsize==132*64 and ssize==8 and e.read(saddr,8)==b'\xff'*8,'64Brecord132+file-backedunknown-completion sentinel')
 return dict(compiled_cases=132,case_stride=40,compiled_table=proof,kernel_address=kaddr,kernel_bytes=ksize,kernel_sha256=hashlib.sha256(code).hexdigest(),MAC_words=['f28800f7','f2881077'],record_address=raddr,record_bytes=64,records=132,sentinel_address=saddr,all_golden_words=len(golden)//4,full_word_independent_oracle=True,ELF_target_overlap=False)
def flatten(c):
 return [dict(id=x['id'],active_harts=[x['hart']],expected_checksums_by_hart=[x['checksum']if h==x['hart']else 0 for h in range(3)],parent_case_id=x['parent_case_id'],internal_split=x['internal_split'],semantic_parent_case_id=x['parent_case_id'],trial_id=x['trial'],region='kernel',suite='pow2_matrix',corpus_split=c['split_id'])for x in c['cases']]
def qualify(b,negative):
 out=b/'ready.json';need(not out.exists(),'Freshqualification only');built=json.loads((b/'build.json').read_text());c=json.loads((b/'corpus.json').read_text());gold=(b/'golden-words.bin').read_bytes();raw=(b/'matrix.elf').read_bytes();need(sha(b/'matrix.elf')==ELF==built['elf_sha256'],'Exact successful positiveELF');proof=inspect(raw,c,gold);ids=dict(built['input_sha256']);normal=[]
 for seed in(0,17):
  d=b/('seed%d'%seed);r=json.loads((d/'run.json').read_text());need(r['pass']is True and r['normal_guest_exit_verified']is True and r['exit_status']==0 and r['timed_out']is False and r['elf_sha256']==ELF and r['seed']==seed,'Real seeded normalexit');need(sha(d/'stdout')==r['stdout_sha256']and sha(d/'stderr')==r['stderr_sha256'],'Actualraw logs');validator().validate((d/'stdout').read_text(),c);normal.append(dict(seed=seed,report=str(d/'run.json'),report_sha256=sha(d/'run.json'),host_seconds=r['host_seconds']));ids.update(r['input_sha256']);ids.update({str(p):sha(p)for p in[d/'run.json',d/'stdout',d/'stderr']})
 nr=negative/'seed0/run.json';neg=json.loads(nr.read_text());need(neg['pass']is True and neg['expect_negative']is True and neg['exit_status']!=0 and neg['timed_out']is False and neg['proof']==dict(actual_omitted_kernel_detected=True,failed_regions=132),'Actualomissionall132fail');ids.update(neg['input_sha256']);ids.update({str(p):sha(p)for p in[nr,nr.parent/'stdout',nr.parent/'stderr']});controls=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,TypeError,KeyError,struct.error):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Acceptedmutation '+name)
 text=(b/'seed0/stdout').read_text();rows=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_REGION ')]
 def wire(rs,refusal=True,terminal=None):return('IRIS_HART2_VME_REFUSAL {"hart":2,"illegal_seen":1}\n'if refusal else'')+'\n'.join('IRIS_REGION '+json.dumps(r)for r in rs)+'\nIRIS_BATCH_DONE '+json.dumps(terminal or dict(failed=0,cases=132,regions=132,trials=3))+'\n'
 for key,val in[('hart',2),('trial_id',True),('m',1),('n',1),('k',1),('checksum',0),('expected_checksum',0),('words',1),('failed_words',False),('pass',1),('instret_delta',False),('mtime_before',False),('mtime_after',0),('mtime_hz',1000000),('dtype','e5m2'),('end_cycle',0)]:
  rs=copy.deepcopy(rows);rs[0][key]=val;reject(key,lambda:validator().validate(wire(rs),c))
 reject('missing-hart2-refusal',lambda:validator().validate(wire(rows,False),c));reject('missing-trial',lambda:validator().validate(wire(rows[:-44]),c));reject('terminal-bool',lambda:validator().validate(wire(rows,terminal=dict(failed=False,cases=132,regions=132,trials=3)),c))
 e=Elf(raw);t=e.syms['cases'][0]
 for name,offset in [('table-name',0),('table-M',8),('table-dtype',20),('table-hart',24),('table-golden',32)]:
  bad=bytearray(raw);bad[e.file_offset(t+offset,1)]^=1;reject(name,lambda:inspect(bytes(bad),c,gold))
 bad=bytearray(gold);bad[0]^=1;reject('independent-golden-word',lambda:inspect(raw,c,bytes(bad)))
 cases=flatten(c);need(len(cases)==132 and sum(len(x['active_harts'])for x in cases)==132,'Hostgeometry');(b/'host-cases.json').write_text(json.dumps(cases,indent=2)+'\n')
 ids.update({str(p):sha(p)for p in[Path(__file__).resolve(),ROOT/'benchmarks/pow2_matrix_v1/run.py',b/'build.json',b/'matrix.elf',b/'golden-words.bin',b/'host-cases.json']})
 for p,h in ids.items():need(sha(p)==h,'Inputchanged '+p)
 q=dict(schema='iris.pow2_single_matrix_qualification.v1',status='passed',ELF_sha256=ELF,full_words=1109760,regions=132,functional=normal,actual_omission=dict(report=str(nr),report_sha256=sha(nr),failed_regions=132),compiled_proof=proof,negative_controls=controls,input_sha256=ids,hardware_contacted=False,source_image_association_verified=False,timing_certified=False)
 (b/'qualification.json').write_text(json.dumps(q,indent=2)+'\n');ready=dict(schema='iris.pow2_single_matrix_ready.v1',status='ready_for_root_managed_preparation',source_frozen=True,ELF_sha256=ELF,regions=132,train_regions=96,reserved_regions=36,reserved_timing_labels_root_only=True,new_exact_reference_required=True,source_image_association_verified=False,artifact_sha256={n:sha(b/n)for n in['matrix.elf','corpus.json','build.json','golden-words.bin','qualification.json','host-cases.json']});out.write_text(json.dumps(ready,indent=2)+'\n');return ready
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--negative-build',type=Path,required=True);a=p.parse_args();qualify(a.build.resolve(),a.negative_build.resolve());print(json.dumps(dict(status='passed',ready_sha256=sha(a.build/'ready.json'))))
