#!/usr/bin/env python3
import argparse,pathlib,json,struct,hashlib,re,itertools
ROOT=pathlib.Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def elf_layout(elf,nm):
 import subprocess
 data=pathlib.Path(elf).read_bytes();symbols={}
 for line in subprocess.check_output([str(nm),'-an',str(elf)],text=True).splitlines():
  m=re.match(r'^([0-9a-fA-F]+)\s+\S\s+(\S+)$',line)
  if m:symbols[m[2]]=int(m[1],16)
 phoff=struct.unpack_from('<Q',data,32)[0];phsize,phnum=struct.unpack_from('<HH',data,54);segments=[]
 for i in range(phnum):
  typ,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',data,phoff+i*phsize)
  if typ==1:segments.append((va,off,filesz))
 def read(addr,n):
  for va,off,size in segments:
   if va<=addr and addr+n<=va+size:return int.from_bytes(data[off+addr-va:off+addr-va+n],'little')
  raise ValueError('Address outside ELF loaded bytes')
 return symbols,read

def inspect(folder,toolroot):
 folder=pathlib.Path(folder);meta=json.loads((folder/'layout-meta.json').read_text());elf=folder/'batch.elf';sym,read=elf_layout(elf,pathlib.Path(toolroot)/'riscv64-unknown-elf-nm');rows=[]
 for f in meta['functions']:
  pc=sym[f['loop_symbol']];begin=sym[f['begin_symbol']];end=sym[f['end_symbol']];assert pc%64==f['offset'];assert begin==pc-4;assert end==pc+sum(f['instruction_widths']);words=[];at=pc
  for width in f['instruction_widths']:
   w=read(at,width);assert width==(2 if w&3!=3 else 4);words.append(w);at+=width
  assert words[:2]==([0x0705,0x078d] if f['mode']=='compact' else [0x00170713,0x00378793]),(f,words)
  branch=words[-1];assert branch&127==0x63 and (branch>>12)&7==1 and (branch>>15)&31==14 and (branch>>20)&31==13
  imm=((branch>>31)&1)<<12|((branch>>7)&1)<<11|((branch>>25)&63)<<5|((branch>>8)&15)<<1
  if imm&4096:imm-=8192
  assert pc+sum(f['instruction_widths'][:2])+imm==pc
  assert read(begin,4)>>20==0xb00 and read(end,4)>>20==0xb00
  rows.append(dict(f,loop_pc=pc,begin_pc=begin,end_pc=end,opcode_words=words,branch_pc=end-4,branch_crosses_fetch8=(end-4)%8==6,loop_spans_fetch8=(pc//8!=(end-1)//8)))
 return {'schema':'iris.cpu_layout_binary_proof.v1','status':'passed','elf_sha256':sha(elf),'functions':rows,'noop':{'loop_pc':sym['layout_noop_loop'],'begin_pc':sym['layout_noop_begin'],'end_pc':sym['layout_noop_end']},'all64_actual_loop_offsets_and_opcode_widths_verified':True,'fitting_only':True,'hardware_contacted':False}

def validate(lines,proof):
 table={(r['mode'],r['offset']):r for r in proof['functions']};expected={(m,o,n,rep,h) for m,o,n,rep,h in itertools.product(('compact','wide'),range(0,64,2),(16,64,256,1024),range(3),range(3))};expected|={('noop',8,0,rep,h) for rep,h in itertools.product(range(3),range(3))};seen=set();rows=[];done=[]
 for line in lines:
  if line.startswith('IRIS_BATCH_DONE '):done.append(json.loads(line[len('IRIS_BATCH_DONE '):]));continue
  if not line.startswith('IRIS_REGION '):continue
  r=json.loads(line[len('IRIS_REGION '):]);key=(r['mode'],r['loop_offset'],r['n'],r['repeat'],r['hart'])
  if key not in expected or key in seen:raise ValueError('Unexpected/duplicate layout tuple')
  seen.add(key);want=r['hart']+1+3*r['n'];meta=proof['noop'] if r['mode']=='noop' else table[(r['mode'],r['loop_offset'])]
  if r.get('pass') is not True or r['checksum']!=want or r['expected_checksum']!=want or r['counter_end']!=r['n']:raise ValueError('Numeric loop formula/counter mismatch')
  for field in ('loop_pc','begin_pc','end_pc'):
   if r[field]!=meta[field]:raise ValueError('Actual loop/counter PC mismatch')
  if r['end_cycle']<r['start_cycle'] or (r['n'] and r['end_cycle']==r['start_cycle']) or r['instret_delta']!=3*r['n']+(3 if r['hart']==2 else 2):raise ValueError('Counter range/heterogeneous CSR phase mismatch')
  rows.append(r)
 if seen!=expected or len(done)!=1 or done[0]!={'failed':0,'regions':2313}:raise ValueError('Incomplete layout corpus')
 return rows
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--output',default=str(ROOT/'build/cpu-layout-v1'));a.add_argument('--toolroot',default='/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin');args=a.parse_args();p=pathlib.Path(args.output);proof=inspect(p,args.toolroot);(p/'binary-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print('all64offsets/widths/PCsPASS',sha(p/'binary-proof.json'))
