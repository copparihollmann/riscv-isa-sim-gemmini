#!/usr/bin/env python3
"""Independent final-v4 ELF/full-word audit. Imports no packet oracle/validator."""
from pathlib import Path
import hashlib,json,re,struct,subprocess
R=Path(__file__).resolve().parents[1];S=R/'benchmarks/zephyr_hart2_pow2_v4';B=R/'build/zephyr-hart2-pow2-normal-v4'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class ELF:
 def __init__(self,data):
  self.data=data;h=struct.unpack_from('<16sHHIQQQIHHHHHH',data);assert h[0][:7]==b'\x7fELF\x02\x01\x01'and h[2]==243;self.sections=[struct.unpack_from('<IIQQQQIIQQ',data,h[6]+i*h[11])for i in range(h[12])];self.symbols={}
  for s in self.sections:
   if s[1]!=2:continue
   strings=self.content(self.sections[s[6]])
   for off in range(0,s[5],24):
    n,info,other,index,address,size=struct.unpack_from('<IBBHQQ',data,s[4]+off);name=strings[n:strings.index(b'\0',n)].decode()
    if 0<index<len(self.sections):self.symbols[name]=(address,size,index)
 def content(self,s):return self.data[s[4]:s[4]+s[5]]
 def raw(self,n):
  a,z,i=self.symbols[n];s=self.sections[i];return self.data[s[4]+a-s[3]:s[4]+a-s[3]+z]
 def offset(self,n):a,z,i=self.symbols[n];s=self.sections[i];return s[4]+a-s[3]
 def memory(self,a,z):
  ss=[s for s in self.sections if s[1]==1 and s[3]<=a and a+z<=s[3]+s[5]];assert len(ss)==1;s=ss[0];o=s[4]+a-s[3];return self.data[o:o+z]
 def cstring(self,a):
  out=bytearray()
  while self.memory(a+len(out),1)!=b'\0':out.extend(self.memory(a+len(out),1));assert len(out)<256
  return out.decode()
 @staticmethod
 def decode(data):
  out=[];o=0
  while o<len(data):lo=int.from_bytes(data[o:o+2],'little');n=4 if lo&3==3 else 2;out.append((o,int.from_bytes(data[o:o+n],'little'),n));o+=n
  assert o==len(data);return out
 def insns(self,n):return self.decode(self.raw(n))
def bodies(e):
 wanted={'packet_vadd':0x03840c57,'packet_mm_int':0xf2880077,'packet_mm_e4':0xf2881077,'packet_mm_e5':0xf28810f7};checked={}
 for n,op in wanted.items():
  words=[x[1]for x in e.insns(n)];assert words==[op]*16+[0x157d,0xfd5d,op,0x8082],n;assert len(e.raw(n))==74;checked[n]=dict(address=e.symbols[n][0],bytes=74,block_target_ops=16,tail_target_ops=1,scalar_loop_ops_per_block=2)
 w=[x[1]for x in e.insns('packet_measure')];a=w.index(0xb00029f3);assert w[a:a+7]==[0xb00029f3,0xb0202a73,0x000480e7,0xb0002af3,0x0330000f,0xb0002b73,0xb0202bf3];assert all(x&127 not in(3,0x23)for x in w[a:a+7]);return checked
VALUES=(1,2,3,4,5,6,7,8,10,12,14,16,20,24,28,32)
def signed(i):return VALUES[i%16]*(-1 if i%32>=16 else 1)
def golden(r):
 out=[];h=r['hart'];t=r['trial'];n=r['operations']
 for i in range(r['elements']):
  if r['kind']==0:v=(3+(5*i+7*t+11*h)%31+n*(1+2*((i+t+h)%2)))%2**r['sew']
  else:
   row,col=divmod(i,r['shape'])
   if r['format']==0:v=n*(1+(row+t+h)%3)*(1+(col+2*t+h)%4)
   else:v=int.from_bytes(struct.pack('<f',n*signed(row+3*t+5*h)*signed(col+7*t+3*h)),'little')
  out.append(v)
 return out
def fnv(values):
 h=14695981039346656037
 for v in values:h=((h^v)*1099511628211)%2**64
 return h
def console(text,regions,negative):
 rows={};chunks={};batch=[];control=[]
 for line in text.splitlines():
  if line.startswith('IRIS_REGION '):
   x=json.loads(line[12:]);rid=x['region_index'];assert rid not in rows;rows[rid]=x
  elif line.startswith('IRIS_DATA '):
   x=json.loads(line[10:]);chunks.setdefault(x['region_index'],[]).append(x)
  elif line.startswith('IRIS_BATCH_DONE '):batch.append(json.loads(line[16:]))
  elif line.startswith('IRIS_H2_CONTROL_DONE '):control.append(json.loads(line[21:]))
 assert sorted(rows)==list(range(648))and sorted(chunks)==list(range(648));assert len(batch)==len(control)==1
 words=0;nonidentity=0
 for rid,r in enumerate(regions):
  x=rows[rid];want=golden(r);assert x['case_id']==r['case_id']and x['hart']==x['logical_cpu']==x['pin']==r['hart'];assert x['hart_mask']==r['hart_mask']and x['operations']==r['operations'];assert x['checked_elements']==r['elements']and x['guard_ok']is True;assert x['failed_elements']==(r['elements']if negative else 0)
  data=bytearray()
  for c in chunks[rid]:assert c['hart']==r['hart']and c['offset']==len(data);raw=bytes.fromhex(c['little_endian_hex']);assert 0<len(raw)<=128;data.extend(raw)
  assert len(data)==r['bytes'];vals=[int.from_bytes(data[i:i+r['element_bytes']],'little')for i in range(0,len(data),r['element_bytes'])];assert fnv(vals)==x['checksum']
  if negative:assert all(a!=b for a,b in zip(vals,want));nonidentity+=1
  else:assert vals==want,(rid,next((i for i,(a,b)in enumerate(zip(vals,want))if a!=b),None))
  words+=len(vals)
 assert words==181440 and batch[0]==dict(failed=648 if negative else 0,cases=486,regions=648,elements=181440,trials=3)
 assert control[0]==dict(physical_hart=2,logical_cpu=2,dispatches=486,acknowledgements=648,checked_elements=181440,scalar_only=True)
 return dict(regions=648,words=words,all_omission_regions_nonidentity=nonidentity)
def main():
 o=R/'build/zephyr-hart2-pow2-separate-review-v1';o.mkdir();elf=B/'zephyr/zephyr.elf';assert sha(elf)=='d47bec0012e4beea0df17b8f1d1c0aa0dc53f07f2a2dc9e8ed0fd5b5bbb49430';e=ELF(elf.read_bytes());kernels=bodies(e);corpus=json.loads((S/'corpus.json').read_text());groups=corpus['groups'];regions=corpus['regions'];assert len(groups)==486 and len(regions)==648
 # Independently regenerate order/geometry; no producer function is imported.
 expected_groups=[];expected_regions=[];offset=0
 for kind in(0,1):
  geometries=[(sew,lmul,0,0)for sew in(8,16,32)for lmul in(1,2,4,8)]if not kind else[(8,1,size,fmt)for size in(8,16,32)for fmt in range(5)]
  for sew,lmul,size,fmt in geometries:
   for n in(17,65):
    for mask in(1,2,3):
     for trial in range(3):
      gid=len(expected_groups);expected_groups.append((kind,sew,lmul,size,fmt,n,mask,trial,len(expected_regions)))
      for h in(0,1):
       if mask&(1<<h):
        cells=256*lmul//sew if not kind else size*size;width=sew//8 if not kind else 4;offset=((offset+135)//128)*128-8;expected_regions.append((gid,h,offset,cells*width,cells,width));offset+=cells*width+16
 assert offset==corpus['storage_bytes']==755720
 assert list(struct.iter_unpack('<9I',e.raw('groups')))==expected_groups
 assert list(struct.iter_unpack('<6I',e.raw('descriptors')))==expected_regions
 ids=[e.cstring(x[0])for x in struct.iter_unpack('<Q',e.raw('case_ids'))];assert ids==[g['case_id']for g in groups]
 for rid,(r,d)in enumerate(zip(regions,expected_regions)):
  assert (r['group'],r['hart'],r['offset'],r['bytes'],r['elements'],r['element_bytes'])==d and r['region_index']==rid and r['data_offset']%128==0
 assert sum(r['elements']for r in regions)==181440
 split=json.loads((S/'split.json').read_text());reserved=[i for i,r in enumerate(regions)if(r['lmul']==4 if not r['kind']else r['shape']==16)];assert split['protected_validation']==reserved and len(reserved)==192;assert split['training_eligible']==[i for i in range(648)if i not in reserved]and len(split['training_eligible'])==456
 # The entire controller TU is scalar, including compiler-created helper loops.
 obj=B/'CMakeFiles/app.dir/src/main.c.obj';objelf=ELF(obj.read_bytes());scalar=0
 for section in objelf.sections:
  if section[2]&4:
   for off,raw,n in ELF.decode(objelf.content(section)):
    assert not(n==4 and raw&127 in(0x07,0x27,0x43,0x47,0x4b,0x4f,0x53,0x57,0x77)),hex(raw);scalar+=1
 for n in('controller','emit','packet_reset_output'):
  assert all(not(size==4 and raw&127 in(7,0x27,0x43,0x47,0x4b,0x4f,0x53,0x57,0x77))for off,raw,size in e.insns(n))
 objdump='/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-objdump';dis=subprocess.check_output([objdump,'-d',str(elf)],text=True);(o/'disassembly.txt').write_text(dis)
 assert re.search(r'sd\s+zero,[^\n]*<packet_measurements_done>\n\s*[0-9a-f]+:\s+0330000f\s+fence\s+rw,rw\n\s*[0-9a-f]+:[^\n]*jal\s+[^\n]*<emit>',dis)
 assert sum('<emit>'in l and'jal\t'in l for l in dis.splitlines())==1
 assert 'packet_record_count' in dis and e.raw('packet_measurements_done')==b'\xff'*8
 # Setup/selection/warm call/output re-poison/reset all precede packet_measure.
 source=(S/'src/compute.c').read_text();assert source.index('fn(blocks);')<source.index('packet_reset_output(rid);')<source.index('vl=setup(g,h);')<source.index('packet_measure(')
 assert source.index('vme_vsettnt_e8w4(32)')<source.index('VME_VTZERO(0)')<source.index('g->format==2||g->format==4')
 assert re.search(r'for\(unsigned row=0;row<g->shape;\+\+row\).*?VME_VTMV_V_T\(24,',source,re.S)
 execution=[];inputs=[Path(__file__),elf,obj,S/'corpus.json',S/'split.json',S/'src/compute.c',S/'src/main.c',S/'src/kernels.S',S/'src/packet.h',B/'build.json']
 for negative in(False,True):
  for seed in(0,17):
   d=R/('build/zephyr-hart2-pow2-%s-seed%d-v4'%('skip'if negative else'normal',seed));report=json.loads((d/'report.json').read_text());assert report['pass']is True and report['exit_status']==(1 if negative else 0)and not report['timed_out'];text=(d/'stdout').read_text();assert sha(d/'stdout')==report['stdout_sha256'];execution.append(dict(seed=seed,negative=negative,**console(text,regions,negative)));inputs.extend([d/'report.json',d/'stdout',d/'stderr'])
 # Independent nonidentity check, including e8 modular arithmetic.
 assert all((r['operations']*a)%256!=0 for r in regions if not r['kind']and r['sew']==8 for a in(1,3))
 controls=[];normal=(R/'build/zephyr-hart2-pow2-normal-seed0-v4/stdout').read_text();lines=normal.splitlines();idx=next(i for i,x in enumerate(lines)if x.startswith('IRIS_DATA '));x=json.loads(lines[idx][10:]);x['little_endian_hex']=('%02x'%(int(x['little_endian_hex'][:2],16)^1))+x['little_endian_hex'][2:];mutants={'changed-word':lines[:idx]+['IRIS_DATA '+json.dumps(x)]+lines[idx+1:],'truncated':lines[:-2]}
 idx2=next(i for i,x in enumerate(lines)if x.startswith('IRIS_REGION '));x=json.loads(lines[idx2][12:]);x['hart']=2;mutants['wrong-role']=lines[:idx2]+['IRIS_REGION '+json.dumps(x)]+lines[idx2+1:];mutants['duplicate']=lines[:idx2]+[lines[idx2]]+lines[idx2:]
 for n,text in mutants.items():
  try:console('\n'.join(text)+'\n',regions,False)
  except(AssertionError,KeyError,ValueError):controls.append(n)
  else:raise AssertionError('independent parser admitted '+n)
 damaged=bytearray(e.data);damaged[e.offset('packet_vadd')]^=0x80
 try:bodies(ELF(bytes(damaged)))
 except AssertionError:controls.append('changed-target-opcode')
 else:raise AssertionError('body corruption admitted')
 result=dict(schema='iris.Zephyr_hart2_pow2_separate_ELF_golden_review.v1',**{'pass':True},ELF_sha256=sha(elf),kernels=kernels,groups=486,regions=648,full_independent_words=181440,protected_regions=192,training_eligible=456,actual_masks=[1,2,3],roles='mask1=hart0;mask2=hart1;mask3=both;h2 controller only',scalar_controller_TU_instructions=scalar,controller_application_no_FP_or_vector=True,OS_transitive_context_code_not_claimed_scalar=True,source_FP8_A_bit='rd0,vs2=v8',source_FP8_B_bit='actual vtype.altfmt;format2/4',all_result_rows_only_after_all_measurements=True,pre_UARTrender_controlled_stop=dict(symbol='emit',address=e.symbols['emit'][0],sentinel='packet_measurements_done',sentinel_address=e.symbols['packet_measurements_done'][0],value=0,count_symbol='packet_record_count',count=648,normal_HW_run_still_requires_full_UART_and_exit=True,controlled_stop_no_E2E_claim=True),source_FENCE_is_requested_not_absolute_VMU_completion_certified=True,executions=execution,independent_refusal_controls=controls,hardware_or_timing_labels_accessed=False,input_sha256={str(p):sha(p)for p in inputs},source_image_or_timing_certified=False)
 (o/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
