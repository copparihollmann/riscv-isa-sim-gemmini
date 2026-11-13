#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args();o=Path(args.output).resolve();o.mkdir(parents=True,exist_ok=False)
 asm=['.text','.option norvc'];names=[]
 for fp in range(2):
  ns=[]
  for pattern in range(2):
   name=f'mm_{fp}_{pattern}';ns.append(name);asm+=['.balign 64',f'.globl {name}',f'.type {name},@function',name+':']
   for i in range(256):
    t=i%4 if pattern else i//64;raw=(0xf2001077 if fp else 0xf2000077)|(8<<20)|(16<<15)|(t<<10);asm.append(f'.4byte 0x{raw:08x}')
   asm+=['ret',f'.size {name},.-{name}']
  names.append(ns)
 asm+=['.balign 64','.globl wrongpath_kernel','.type wrongpath_kernel,@function','wrongpath_kernel:']
 for k in range(16):asm += [f'beq zero,zero,.Lskip{k}',f'.globl wrongpath_MM_{k}',f'wrongpath_MM_{k}:','.4byte 0xf2880077',f'.Lskip{k}:','addi zero,zero,0']
 asm+=['ret','.size wrongpath_kernel,.-wrongpath_kernel'];(o/'kernels.S').write_text('\n'.join(asm)+'\n')
 (o/'kernels.h').write_text('typedef void(*kernel_t)(void);\n'+''.join(f'extern void {n}(void);\n'for ns in names for n in ns)+'extern void wrongpath_kernel(void);\nstatic kernel_t kernels[2][2]={{'+','.join(names[0])+'},{'+','.join(names[1])+'}};\n')
 parent=json.load(open(ROOT/'build/overlap-completion-console-guest-v1/build.json'));cmd=parent['argv'];idx=cmd.index(str(ROOT/'benchmarks/overlap_completion_v1/guest_console.c'));cmd=cmd[:];cmd[idx]=str(ROOT/'timing/overlap_completion_guard_guest.c');cmd[idx+1]=str(o/'kernels.S');cmd[cmd.index('-o')+1]=str(o/'guard.elf');cmd=[('-I'+str(o)if x.startswith('-I')and'overlap-completion-console-guest-v1'in x else x)for x in cmd]
 r=subprocess.run(cmd,capture_output=True);(o/'build.stdout').write_bytes(r.stdout);(o/'build.stderr').write_bytes(r.stderr)
 if r.returncode:raise RuntimeError(r.stderr.decode())
 from timing.memory_routes_current_audit_v2 import Elf
 e=Elf(o/'guard.elf');obj={n:dict(zip(('address','size'),e.symbol(n)))for n in('opu_guard_done','opu_guard_errors','opu_guard_cases','opu_guard_words','opu_guard_wrong_words')};bad={n:e.symbol(n)[0]for n in[f'wrongpath_MM_{k}'for k in range(16)]}
 ins={str(Path(x).resolve()):sha(Path(x))for x in parent['input_sha256']if Path(x).is_file()and'cases.inc'not in x and'kernels.S'not in x and'guest_console.c'not in x and'build_console.py'not in x}
 ins.update({str(p.resolve()):sha(p)for p in(Path(__file__),ROOT/'timing/overlap_completion_guard_guest.c',o/'kernels.S',o/'kernels.h',o/'guard.elf')})
 j={'schema':'iris.opu_entry_guard_build.v1','pass':True,'ELF_sha256':sha(o/'guard.elf'),'argv':cmd,'input_sha256':ins,'objects':obj,'wrongpath_MM_PCs':bad,'numeric_scope':'Every4tiles×32rows×32columns, varied initial cells and row/column operands; INT8/E4M3×8/16/32×same/rotating, bothcompute harts; wrongpath16 sites/hart; fflags unchanged','hardware_contacted':False};(o/'build.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps({'pass':True,'ELF_sha256':j['ELF_sha256']}))
if __name__=='__main__':main()
