#!/usr/bin/env python3
"""Finite power-of-two single-hart vector/VME issue-versus-drain probe."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 cases=[];functions={}
 for h in (0,1):
  for fp8 in (0,1):
   for edge in (8,16,32):
    for n in (16,64):
     for rotate in (0,1):
      name=f'kernel_{fp8}_{n}_{rotate}';functions[name]=(fp8,n,rotate)
      for trial in range(3):cases.append(dict(id=len(cases),case_id=f'overlap.v1.h{h}.vme.{fp8}.edge{edge}.n{n}.rotate{rotate}.trial{trial}',hart=h,fp8=fp8,edge=edge,count=n,rotate=rotate,trial=trial,kernel=name))
 for edge in (16,32,64,128):
  for n in(16,64):
   name=f'kernel_vector_{n}';functions[name]=(2,n,0)
   for trial in range(3):cases.append(dict(id=len(cases),case_id=f'overlap.v1.h2.rvv.e8.vl{edge}.n{n}.trial{trial}',hart=2,fp8=0,edge=edge,count=n,rotate=0,trial=trial,kernel=name))
 assembly=['.text','.option norvc']
 for name,(fp8,n,rotate)in functions.items():
  assembly += ['.balign 64',f'.globl {name}',f'.type {name},@function',name+':']
  for i in range(n):
   if fp8==2:assembly.append('vadd.vv v8,v8,v16')
   else:
    tile=i%4 if rotate else 0
    # Canonical header funct7=0x79, A=v8(rs2), B=v16(rs1).
    raw=(0xf2001077 if fp8 else 0xf2000077)|(8<<20)|(16<<15)|(tile<<10)
    assembly.append(f'.4byte 0x{raw:08x}')
  assembly+=['ret',f'.size {name},.-{name}']
 (out/'kernels.S').write_text('\n'.join(assembly)+'\n')
 inc=['enum{CASE_COUNT='+str(len(cases))+'};']+[f'extern void {n}(void);'for n in functions]
 inc+=['static const case_t cases[CASE_COUNT]={']+[f'{{{c["hart"]},{c["fp8"]},{c["edge"]},{c["count"]},{c["rotate"]},{c["trial"]},{c["kernel"]}}},'for c in cases]+['};']
 (out/'cases.inc').write_text('\n'.join(inc)+'\n')
 compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
 argv=[str(compiler),'-O2','-g','-Wall','-Wextra','-Wno-misleading-indentation','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(out),'-I'+str(ROOT/'benchmarks'),'-I'+str(ROOT/'third_party/saturn/benchmarks/common'),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(Path(__file__).with_name('guest_console.c')),str(out/'kernels.S'),'-lgcc','-o',str(out/'overlap.elf')]
 q=subprocess.run(argv,capture_output=True);(out/'build.stdout').write_bytes(q.stdout);(out/'build.stderr').write_bytes(q.stderr)
 if q.returncode:raise RuntimeError('compile failed')
 from timing.memory_routes_current_audit_v2 import Elf
 elf=Elf(out/'overlap.elf');objects={n:dict(zip(('address','size'),elf.symbol(n)))for n in ('overlap_done','overlap_failed','overlap_finished','overlap_records','overlap_words')}
 if objects['overlap_records']['size']!=len(cases)*128 or objects['overlap_words']['size']!=len(cases)*512:raise ValueError('layout differs')
 if elf.read(objects['overlap_done']['address'],8)!=b'\xff'*8:raise ValueError('sentinel not file-backed known')
 layout={'schema':'iris.overlap_completion_readback.v1','elf_sha256':sha(out/'overlap.elf'),'cases':len(cases),'record_stride':128,'word_stride':512,'objects':objects,'row_fields':['hart','fp8','edge','count','rotate','trial','start','issue_end','fence_end','drain_end','instret','checksum','failed','expected']}
 (out/'readback-layout.json').write_text(json.dumps(layout,indent=2)+'\n');(out/'corpus.json').write_text(json.dumps({'schema':'iris.overlap_completion_corpus.v1','cases':cases,'single_active_hart_per_case':True,'other_harts_WFI_then_MSIP_wake':True,'regions':len(cases),'hardware_contacted':False,'timing_reference_available':False},indent=2)+'\n')
 inputs=[Path(__file__),Path(__file__).with_name('guest_console.c'),out/'kernels.S',out/'cases.inc',compiler,*[ROOT/'benchmarks'/n for n in('start.S','runtime.c','runtime.h','uart_drain.h','link.ld')],ROOT/'third_party/saturn/benchmarks/common/vme.h']
 report={'schema':'iris.overlap_completion_console_build.v1','pass':True,'elf_sha256':sha(out/'overlap.elf'),'argv':argv,'cases':len(cases),'canonical_MM_funct7':121,'actual_result_row_words_per_compute_case':128,'hardware_contacted':False,'input_sha256':{str(p.resolve()):sha(p)for p in inputs}}
 parent=ROOT/'build/overlap-completion-guest-v2/overlap.elf'
 old=Elf(parent);identity=[]
 for name in functions:
  address,size=elf.symbol(name);before,bsize=old.symbol(name)
  if size!=bsize or elf.read(address,size)!=old.read(before,size):raise ValueError('Measured kernel instruction bytes changed')
  identity.append({'function':name,'old_address':before,'new_address':address,'size':size,'instruction_sha256':hashlib.sha256(elf.read(address,size)).hexdigest()})
 report['measured_kernel_bytes_equal_parent']=identity;report['parent_P_only_ELF_sha256']=sha(parent);report['postmeasurement_console_only']=True
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'cases':len(cases),'ELF_sha256':report['elf_sha256']}))
if __name__=='__main__':main()
