#!/usr/bin/env python3
from pathlib import Path
import re,subprocess,json,hashlib,os
from generate_fpcomp_cases import NAMES
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 subprocess.run(['python3',str(HERE/'generate_fpcomp_cases.py')],check=True)
 for module in ['FPUDecoder','FPUDecoder_1','FPUDecoder_2','FPUDecoder_3','FPUDecoder_4']:
  subprocess.run(['python3',str(HERE/'audit_fpcomp_decoder.py')],env=dict(os.environ,IRIS_FPU_DECODER=module),check=True)
 source=HERE/'source';encoding=source/'riscv/encoding.h';text=encoding.read_text()
 for vm in [0,1]:
  rows=[]
  for i,name in enumerate(NAMES):
   key='MATCH_'+name.replace('.','_').upper();value=int(re.search(r'#define '+key+r' (0x[0-9a-f]+)',text)[1],16);value|=(8<<20)|((3 if name.endswith('.vf') else 16)<<15)|(24<<7)|(vm<<25)
   rows.append('case '+str(i)+':__asm__ volatile(".word '+hex(value)+'":::"memory");break;\n')
  (HERE/('fpcomp_unmasked_switch.h' if vm else 'fpcomp_masked_switch.h')).write_text(''.join(rows))
 compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');bench=ROOT/'benchmarks';elf=HERE/'benchmarks/fpcomp.elf'
 cmd=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-T',str(bench/'link.ld'),str(bench/'start.S'),str(bench/'runtime.c'),str(HERE/'fpcomp_guest.c'),'-lgcc','-o',str(elf)]
 subprocess.run(cmd,check=True)
 inputs=list(HERE.glob('fpcomp-FPUDecoder*-proof.json'))+list((HERE/'fpcomp-evidence').glob('*.fir'))+[HERE/'audit_fpcomp_decoder.py',HERE/'fpcomp-policy.json',HERE/'compile_fpcomp.py',HERE/'generate_fpcomp_cases.py',HERE/'fpcomp_cases.hpp',HERE/'fpcomp_guest.c',HERE/'fpcomp_unmasked_switch.h',HERE/'fpcomp_masked_switch.h',bench/'uart_drain.h',bench/'uart_drain.S',bench/'runtime.h',bench/'runtime.c',bench/'start.S',bench/'link.ld',encoding]
 (HERE/'benchmarks/fpcomp-build.json').write_text(json.dumps({'argv':cmd,'compiler_sha256':sha(compiler),'inputs':{str(p):sha(p) for p in inputs},'elf_sha256':sha(elf)},indent=2)+'\n')
if __name__=='__main__':main()
