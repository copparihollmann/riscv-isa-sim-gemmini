#!/usr/bin/env python3
"""Build the all-three-hart native FP8 regression, recording its exact inputs."""
from pathlib import Path
import argparse,subprocess,hashlib,json
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'));a=p.parse_args()
 for script in ['generate_native_fp8_cases.py','generate_native_guest.py','generate_wide_fp8_cases.py','generate_fp8_reduction_cases.py']:subprocess.run(['python3',str(HERE/script)],check=True)
 bench=HERE.parent/'benchmarks';out=HERE/'benchmarks/native-fp8.elf'
 cmd=[str(a.compiler),'-O2','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-T',str(bench/'link.ld'),str(bench/'start.S'),str(bench/'runtime.c'),str(HERE/'native_fp8_guest.c'),'-lgcc','-o',str(out)]
 subprocess.run(cmd,check=True)
 # Locate explicit source/output rather than depend on compiler argument offsets.
 wide_cmd=[str(HERE/'wide_reduce_fp8_guest.c') if x==str(HERE/'native_fp8_guest.c') else str(HERE/'benchmarks/wide-reduce-fp8.elf') if x==str(out) else x for x in cmd]
 subprocess.run(wide_cmd,check=True)
 inputs=[HERE/'native_fp8_guest.c',HERE/'native_guest_cases.h',HERE/'native_guest_switch.h',HERE/'native_guest_masked_switch.h',HERE/'generate_native_fp8_cases.py',HERE/'generate_native_guest.py',HERE/'generate_fp8_cases.py',HERE/'compile_native_fp8.py',bench/'uart_drain.h',bench/'uart_drain.S',bench/'runtime.h',bench/'runtime.c',bench/'start.S',bench/'link.ld',HERE/'wide_reduce_fp8_guest.c',HERE/'wide_guest_switch.h',HERE/'wide_fp8_cases.hpp',HERE/'fp8_reduction_cases.hpp',HERE/'generate_wide_fp8_cases.py',HERE/'generate_fp8_reduction_cases.py']
 (HERE/'benchmarks/native-fp8-build.json').write_text(json.dumps({'argv':cmd,'compiler_sha256':sha(a.compiler),'inputs':{str(p):sha(p) for p in inputs},'elf_sha256':sha(out),'wide_build_argv':wide_cmd,'wide_elf_sha256':sha(HERE/'benchmarks/wide-reduce-fp8.elf'),'executed':False},indent=2)+'\n')
if __name__=='__main__':main()
