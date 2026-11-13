#!/usr/bin/env python3
"""Build the independent hart2 shared-FPU corpus with concurrent compute harts."""
from pathlib import Path
import argparse,subprocess,hashlib,json,re
from generate_ieee_fma_cases import NAMES
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'));a=p.parse_args()
 for script in ['generate_shared_fma_cases.py','audit_shared_decoder.py']:subprocess.run(['python3',str(HERE/script)],check=True)
 encoding=HERE/'source/riscv/encoding.h';text=encoding.read_text();rows=[]
 for i,name in enumerate(NAMES):
  value=int(re.search(r'#define MATCH_'+name.replace('.','_').upper()+r' (0x[0-9a-f]+)',text)[1],16);vf=name.endswith(('.vf','.wf'));value|=(8<<20)|((3 if vf else 16)<<15)|(24<<7)
  rows.append('case '+str(i)+':__asm__ volatile(".word '+hex(value)+'":::"memory");break;\n')
 (HERE/'shared_guest_switch.h').write_text(''.join(rows))
 bench=HERE.parent/'benchmarks';out=HERE/'benchmarks/shared-fpu.elf'
 cmd=[str(a.compiler),'-O2','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-T',str(bench/'link.ld'),str(bench/'start.S'),str(bench/'runtime.c'),str(HERE/'shared_fma_guest.c'),'-lgcc','-o',str(out)]
 subprocess.run(cmd,check=True)
 inputs=[HERE/'compile_shared_fma.py',HERE/'generate_shared_fma_cases.py',HERE/'generate_ieee_fma_cases.py',HERE/'generate_native_fp8_cases.py',HERE/'generate_fp8_cases.py',HERE/'audit_shared_decoder.py',HERE/'shared-decoder-proof.json',HERE/'shared-evidence/fpu-decoder4.fir',HERE/'shared_fma_guest.c',HERE/'shared_fma_cases.hpp',HERE/'shared_guest_switch.h',bench/'uart_drain.h',bench/'uart_drain.S',bench/'runtime.h',bench/'runtime.c',bench/'start.S',bench/'link.ld',encoding]
 (HERE/'benchmarks/shared-fpu-build.json').write_text(json.dumps({'argv':cmd,'compiler_sha256':sha(a.compiler),'inputs':{str(p):sha(p) for p in inputs},'elf_sha256':sha(out)},indent=2)+'\n')
if __name__=='__main__':main()
