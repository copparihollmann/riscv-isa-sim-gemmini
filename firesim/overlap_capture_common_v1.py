#!/usr/bin/env python3
"""Source/binary guard for frozen finite overlap console packet."""
import hashlib,importlib.util,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ELF='deec529e973d47413de419018d328582564a18b979c7e6b93f6c323507b27940'
PARENT_READY='c9d1e880d8bd392acb2333e12c5554f12b10358bcfa7238dc5cbe4d719b19fc3'
SPLIT_SHA='da74dbbb73f8b322192aae419925acec0c276284d155cdc70595d351cda439fb'
def need(ok,why):
 if not ok:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validator():
 p=ROOT/'benchmarks/overlap_completion_v1/validate_console.py';s=importlib.util.spec_from_file_location('overlap_console_oracle',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
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
    if key in ['cases','overlap_done','overlap_failed','overlap_finished','overlap_records','overlap_words'] or key.startswith('kernel_'):
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

def canonical():
 rows=[]
 for h in(0,1):
  for fp8 in(0,1):
   for edge in(8,16,32):
    for count in(16,64):
     for rotate in(0,1):
      for trial in range(3):rows.append(dict(id=len(rows),case_id='overlap.v1.h%d.vme.%d.edge%d.n%d.rotate%d.trial%d'%(h,fp8,edge,count,rotate,trial),hart=h,fp8=fp8,edge=edge,count=count,rotate=rotate,trial=trial,kernel='kernel_%d_%d_%d'%(fp8,count,rotate)))
 for edge in(16,32,64,128):
  for count in(16,64):
   for trial in range(3):rows.append(dict(id=len(rows),case_id='overlap.v1.h2.rvv.e8.vl%d.n%d.trial%d'%(edge,count,trial),hart=2,fp8=0,edge=edge,count=count,rotate=0,trial=trial,kernel='kernel_vector_%d'%count))
 return rows

def check_corpus(corpus):
 need(corpus.get('schema')=='iris.overlap_completion_corpus.v1'and corpus.get('regions')==168 and corpus.get('single_active_hart_per_case')is True and corpus.get('other_harts_WFI_then_MSIP_wake')is True,'Exact finite console corpus scope')
 need(corpus['cases']==canonical(),'Canonical168 independent semantic identities')
 for c in corpus['cases']:
  need(all(type(c[k])is int for k in('id','hart','fp8','edge','count','rotate','trial')),'No bool in source geometry')

def expected_word(c,j):
 if c['hart']==2:return c['count']+1
 tile,col=divmod(j,32)
 if col>=c['edge']:return 0
 count=c['count']//4 if c['rotate']else c['count']if tile==0 else 0
 # Exact mathematical binary32 integer bits; no Spike/source validator import.
 if not c['fp8']or not count:return count
 exponent=count.bit_length()-1
 return((exponent+127)<<23)|((count<<(23-exponent))&0x7fffff)

def is_reserved(c):return(c['hart']<2 and c['edge']==16)or(c['hart']==2 and c['edge']==64)
def host_cases(corpus):
 check_corpus(corpus);rows=[]
 for c in corpus['cases']:
  words=c['edge']if c['hart']==2 else 128
  gold=sum(expected_word(c,j)for j in range(words));rows.append(dict(id='overlap.v1.case.'+str(c['id']),active_harts=[c['hart']],expected_checksums_by_hart=[gold if h==c['hart']else 0 for h in range(3)],parent_case_id=c['case_id'].rsplit('.trial',1)[0],semantic_source_case_id=c['case_id'],trial_id=c['trial'],internal_split='reserved_validation'if is_reserved(c)else'train',region='total',suite='source_overlap',corpus_split='iris-overlap-mechanism-validation-v1'))
 return rows

def inspect(raw,corpus,layout):
 check_corpus(corpus);e=Elf(raw);address,size=e.syms['cases'];need(size==168*56,'Actual168x56compiledtable');kernels={};entries=[]
 for i,c in enumerate(corpus['cases']):
  fields=struct.unpack('<7Q',e.read(address+i*56,56));want=tuple(c[k]for k in('hart','fp8','edge','count','rotate','trial'))+(e.syms[c['kernel']][0],);need(fields==want,'Actualcompiledcasegeometry/kernelpointer');entries.append(dict(index=i,address=address+i*56,kernel=c['kernel']));kernels[c['kernel']]=c
 codeproof=[]
 for name,c in sorted(kernels.items()):
  addr,n=e.syms[name];words=[]
  for i in range(c['count']):
   if c['hart']==2:word=0x02880457 # vadd.vv v8,v8,v16
   else:word=(0xf2001077 if c['fp8']else 0xf2000077)|(8<<20)|(16<<15)|((i%4 if c['rotate']else 0)<<10)
   words.append(word)
  words.append(0x00008067);body=struct.pack('<%dI'%len(words),*words);need(n==len(body)and e.read(addr,n)==body,'Actual contiguousinstruction stream '+name);codeproof.append(dict(name=name,address=addr,bytes=n,sha256=hashlib.sha256(body).hexdigest(),real_ops=c['count']))
 objects={name:dict(address=e.syms[name][0],size=e.syms[name][1])for name in['overlap_done','overlap_failed','overlap_finished','overlap_records','overlap_words']};need(layout['objects']==objects and layout['record_stride']==128 and layout['word_stride']==512 and layout['cases']==168,'Actualreadbacklayout');need(objects['overlap_records']['size']==168*128 and objects['overlap_words']['size']==168*512 and e.read(objects['overlap_done']['address'],8)==b'\xff'*8,'Filebackedknown sentinel/fullbuffer');need(layout['elf_sha256']==hashlib.sha256(raw).hexdigest(),'LayoutactualELF')
 return dict(compiled_table_cases=168,stride=56,entries=entries,exact_measured_kernels=codeproof,objects=objects,record_stride=128,word_stride=512,known_filebacked_completion_sentinel=True,matrix_coverage='row0of4tiles;32wordseachincludinginactivecolumns',vector_console_coverage='activeVLbytesonly; nopaddingclaim',full_MRF_rows_claimed=False,CLINT_not_sampled=True,subwindow_instret_not_available=True)
