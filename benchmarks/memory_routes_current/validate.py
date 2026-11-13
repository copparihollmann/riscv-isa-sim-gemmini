"""Independent route geometry/goldens and strict repeated-console validation."""
import json,struct
from pathlib import Path
REGIONS={'tcm0':(0x70000000,0x20000),'tcm1':(0x70020000,0x20000),'scratchpad':(0x580000000,0x20000),'dram':(0x84000000,0x20000)}
SCHEMA='iris.memory_routes_current_corpus.v1'

def canonical():
 rows=[]
 for target,(base,size)in REGIONS.items():
  for pattern,stride,spread in [('bank0',128,0),('hart-banks',128,1),('alternating',64,0)]:
   for kind,counts in [('chase',(33,257)),('read',(1,16)),('write',(1,16))]:
    for n in counts:
     for mask in range(1,8):rows.append((target,base,pattern,stride,spread,kind,n,mask))
 return rows

def golden(c,h):
 base=c['base']+h*0x8000+(64*(h%2)if c['spread']else 0)
 if c['kind']=='chase':return base+((13*c['n'])%64)*c['stride']
 if c['kind']=='read':return c['n']*sum(0x1000+256*h+i for i in range(64))
 if c['kind']=='write':return sum(c['n']*256+h for _ in range(64))
 raise ValueError('unknown memory kernel')

def admitted(corpus):
 if (corpus.get('schema')!=SCHEMA or corpus.get('physical_harts')!=3 or corpus.get('trials')!=3
     or corpus.get('expected_region_count')!=2592 or len(corpus.get('cases',[]))!=1512
     or corpus.get('fitting_only')is not True or corpus.get('global_heldout')is not False):raise ValueError('Complete three-trial fitting-only memory corpus required')
 for index,values in enumerate(canonical()):
  target,base,pattern,stride,spread,kind,n,mask=values
  parent=f'memroute.{target}.{pattern}.{kind}.{n}.mask{mask}'
  for trial in range(3):
   c=corpus['cases'][index*3+trial]
   expected={'target_region':target,'base':base,'stride':stride,'spread':spread,'kind':kind,'n':n,'mask':mask,
    'parent_case_id':parent,'trial_id':trial,'suite':'memory_routes_current','case_id':f'memroute.current.v1.{parent}.r{trial}',
    'semantic_parent_case_id':f'memroute.{target}.{pattern}.{kind}.mask{mask}'}
   if any(c.get(k)!=v for k,v in expected.items()):raise ValueError('Changed case order/identity/geometry')
   pointers=[base+h*0x8000+(64*(h%2)if spread else 0)for h in range(3)]
   if c['addresses_by_hart']!=pointers or c['expected_checksums']!=[golden(c,h)for h in range(3)]:raise ValueError('Independent pointer/value golden differs')
   if c['node_count']!=64 or c['window_bytes_per_hart']!=0x8000:raise ValueError('Node/window geometry changed')
   for h,p in enumerate(pointers):
    if p<base+h*0x8000 or p+63*stride+8>base+(h+1)*0x8000:raise ValueError('Overlapping/out-of-window addresses')
   if c['bank_bit6_sequence_by_hart']!=[[((p+i*stride)>>6)&1 for i in range(64)]for p in pointers]:raise ValueError('Address bank-bit trace differs')
 return corpus

def check_rows(rows,corpus):
 admitted(corpus);expected={(c['case_id'],h):c for c in corpus['cases']for h in range(3)if c['mask']&(1<<h)}
 if len(rows)!=2592:raise ValueError('Missing/extra measured region')
 seen=set()
 for r in rows:
  key=(r.get('case_id'),r.get('hart'))
  if key in seen or key not in expected:raise ValueError('Duplicate/unknown case/hart')
  seen.add(key);c=expected[key]
  if any(r.get(k)!=c[k]for k in ('parent_case_id','trial_id','suite'))or r.get('region')!='kernel':raise ValueError('Wrong repeat/parent identity')
  if any(type(r.get(k))is not int for k in ('hart','start_cycle','end_cycle','instret_delta','checksum','expected_checksum')):raise ValueError('Counter/checksum type')
  if not 0<=r['start_cycle']<r['end_cycle']<2**64 or not 0<r['instret_delta']<2**64:raise ValueError('Invalid counter interval')
  if r['checksum']!=golden(c,r['hart'])or r['expected_checksum']!=golden(c,r['hart'])or r.get('pass')is not True:raise ValueError('Independent numeric golden failed')
 return {'cases':1512,'semantic_parents':252,'regions':2592,'physical_harts':[0,1,2],'trials':3,'all_independent_goldens':True}

def validate(text,corpus):
 if 'IRIS_FATAL'in text:raise ValueError('Guest fatal')
 rows=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_REGION ')]
 result=check_rows(rows,corpus)
 done=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_BATCH_DONE ')]
 if done!=[{'failed':0,'cases':1512,'regions':2592}]:raise ValueError('Missing/wrong terminal contract')
 return result

class ELF:
 def __init__(self,path):
  self.raw=Path(path).read_bytes();r=self.raw
  if r[:7]!=b'\x7fELF\x02\x01\x01'or struct.unpack_from('<H',r,18)[0]!=243:raise ValueError('RISC-V little-endian ELF64 required')
  off=struct.unpack_from('<Q',r,32)[0];size,count=struct.unpack_from('<HH',r,54);self.loads=[]
  if size<56 or off+size*count>len(r):raise ValueError('ELF program table bounds')
  for i in range(count):
   typ,flags,pos,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',r,off+i*size)
   if typ==1:
    if fs>ms or pos+fs>len(r)or va!=pa:raise ValueError('ELF load extent')
    self.loads.append((pa,pos,fs,ms,flags))
  shoff=struct.unpack_from('<Q',r,40)[0];shsize,shnum=struct.unpack_from('<HH',r,58)
  if shsize<64 or shoff+shsize*shnum>len(r):raise ValueError('ELF section table bounds')
  sections=[struct.unpack_from('<IIQQQQIIQQ',r,shoff+i*shsize)for i in range(shnum)];self.symbols={}
  for section in sections:
   if section[1]!=2:continue
   strings=sections[section[6]];names=r[strings[4]:strings[4]+strings[5]]
   if section[9]!=24 or section[4]+section[5]>len(r):raise ValueError('ELF symbol table extent')
   for pos in range(section[4],section[4]+section[5],24):
    name,info,other,index,value,sz=struct.unpack_from('<IBBHQQ',r,pos)
    if index and name:
     end=names.find(b'\0',name)
     if end<0:raise ValueError('ELF symbol string')
     self.symbols[names[name:end].decode()]={'address':value,'size':sz,'info':info}
 def read(self,address,n):
  for base,pos,fs,ms,flags in self.loads:
   if base<=address and address+n<=base+fs:return self.raw[pos+address-base:pos+address-base+n]
  raise ValueError('Required bytes are not file-backed')
 def string(self,address):
  value=bytearray()
  for i in range(256):
   b=self.read(address+i,1)
   if b==b'\0':return value.decode()
   value+=b
  raise ValueError('Unbounded ELF string')

def check_elf(elf,corpus,layout):
 admitted(corpus);e=ELF(elf)
 for base,pos,fs,ms,flags in e.loads:
  if any(max(base,a)<min(base+ms,a+n)for a,n in REGIONS.values()):raise ValueError('ELF overlaps target window')
 table=e.symbols['experiments'];assert table['size']==1512*64
 for index,c in enumerate(corpus['cases']):
  ptr,base,kind,stride,spread,n,mask,*expected=struct.unpack('<QQIIIII4xQQQ',e.read(table['address']+index*64,64))
  if e.string(ptr)!=c['case_id']or(base,kind,stride,spread,n,mask)!=tuple([c['base'],['chase','read','write'].index(c['kind']),c['stride'],c['spread'],c['n'],c['mask']])or expected!=[golden(c,h)for h in range(3)]:raise ValueError('Compiled case table/independent golden differs')
 objects={k:e.symbols[k]for k in ('buffered_records','buffered_measurements_done','buffered_record_count','buffered_case_count')}
 if layout['objects']!={k:{'address':v['address'],'size':v['size']}for k,v in objects.items()}or objects['buffered_records']['size']!=2592*64:raise ValueError('Readback symbol geometry')
 if int.from_bytes(e.read(objects['buffered_measurements_done']['address'],8),'little')!=2**64-1:raise ValueError('Uninitialized completion sentinel')
 return {'compiled_table_records':1512,'independent_compiled_goldens':4536,'readback_records':2592}
