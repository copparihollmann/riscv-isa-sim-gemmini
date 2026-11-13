#!/usr/bin/env python3
"""Compile initialized three-hart CSR controls independently of Spike ISA labels."""
import argparse,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'));a=p.parse_args()
 text='/* Literal CSR numbers; source policy is reset-hpm-policy.json. */\n'
 for name,base,write in [('read_mhpm',0xb03,False),('write_mhpm',0xb03,True),('read_event',0x323,False),('write_event',0x323,True),('read_hpm',0xc03,False)]:
  text+=('static void '+name+'(unsigned slot,uint64_t value) { switch(slot) {\n' if write else 'static uint64_t '+name+'(unsigned slot) { uint64_t value=0; switch(slot) {\n')
  for slot in range(29):
   text+=(f'case {slot}:__asm__ volatile("csrw {hex(base+slot)},%0"::"r"(value):"memory");break;\n' if write else f'case {slot}:__asm__ volatile("csrr %0,{hex(base+slot)}":"=r"(value)::"memory");break;\n')
  text+='}'+('}\n' if write else 'return value;}\n')
 header=HERE/'csr_case_switch.h';header.write_text(text)
 bench=HERE.parent/'benchmarks';elf=HERE/'benchmarks/csr_config.elf'
 cmd=[str(a.compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-I'+str(bench),'-T',str(bench/'link.ld'),str(bench/'start.S'),str(bench/'runtime.c'),str(HERE/'csr_config_guest.c'),'-lgcc','-o',str(elf)]
 subprocess.run(cmd,check=True)
 inputs=[Path(__file__),header,HERE/'csr_config_guest.c',*[bench/name for name in ['runtime.h','runtime.c','start.S','link.ld','uart_drain.h','uart_drain.S']]]
 (HERE/'benchmarks/csr-config-build.json').write_text(json.dumps({'argv':cmd,'compiler_sha256':sha(a.compiler),'input_sha256':{str(p):sha(p) for p in inputs},'elf_sha256':sha(elf)},indent=2)+'\n')
if __name__=='__main__':main()
