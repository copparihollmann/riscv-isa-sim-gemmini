#!/usr/bin/env python3
"""Compile pinned Saturn directed and fused guests without changing its checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import shlex

HERE=Path(__file__).resolve().parent
SATURN_PIN='536774bd4c5e3bcd7813a4a0dc72fc87e5818532'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=HERE.parent/'third_party/saturn')
    parser.add_argument('--cc',default=shutil.which('riscv64-unknown-elf-gcc'))
    args=parser.parse_args()
    if not args.cc or not Path(args.cc).is_file():parser.error('--cc must identify a RISC-V bare-metal compiler')
    source=args.source.resolve()
    pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if pin!=SATURN_PIN:raise SystemExit('Unexpected Saturn revision')
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no']):raise SystemExit('Saturn sources are modified; preserve and audit changes first')
    out=HERE/'benchmarks';out.mkdir(exist_ok=True)
    flags=f'-I{HERE}/source/riscv -DPREALLOCATE=1 -mcmodel=medany -static -O2 -g -ffast-math -fno-common -fno-builtin-printf -fno-tree-loop-distribute-patterns -march=rv64gcv_zfh_zvfh -mabi=lp64d'
    cmd=['make','-B','-f',str(source/'benchmarks/Makefile'),f'src_dir={source}/benchmarks',f'RISCV_GCC={Path(args.cc).resolve()}',f'RISCV_COMMON_OPTS={flags}','VLEN=256','MX=0','vme-directed.riscv','vme-fused-lm2-gemm-transpose.riscv']
    with (out/'compile.log').open('w') as log:subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
    mx_cmd=cmd[:-4]+['VLEN=256','MX=1','vme-directed.riscv','vme-fp8-gemm.riscv']
    saved=(out/'vme-directed.riscv').read_bytes()
    with (out/'compile-mx.log').open('w') as log:subprocess.run(mx_cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
    (out/'vme-directed-mx.riscv').write_bytes((out/'vme-directed.riscv').read_bytes())
    (out/'vme-directed.riscv').write_bytes(saved)
    cc=[str(Path(args.cc).resolve())]+shlex.split(flags)+['-I'+str(source/'benchmarks/common'),'-I'+str(source/'benchmarks/vme-directed'),'-std=gnu99']
    common=[str(p) for folder in ['common','common/ara'] for p in sorted((source/'benchmarks'/folder).glob('*')) if p.suffix in ['.c','.S']]
    isolated=cc+[str(HERE/'fp8_directed.c'),*common,'-nostdlib','-nostartfiles','-static','-lm','-lgcc','-T',str(source/'benchmarks/common/test.ld'),'-o',str(out/'vme-fp8-directed.riscv')]
    subprocess.run(isolated,check=True)
    cpu_cmd=[str(Path(args.cc).resolve()),'-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-mabi=lp64d','-mcmodel=medany','-nostdlib','-static','-Wl,--build-id=none,--no-relax','-I'+str(HERE/'source/riscv'),'-T',str(HERE/'dma_guard.ld'),str(HERE/'cpu_dtypes.S'),'-o',str(out/'cpu-dtypes.elf')]
    subprocess.run(cpu_cmd,check=True)
    dma_inputs=[HERE/'dma_guard.S',HERE/'dma_guard.ld',HERE/'cpu_dtypes.S',HERE/'fp8_directed.c',HERE.parent/'benchmarks/uart_drain.S',HERE.parent/'benchmarks/uart_drain.h']
    for stem,defines in [('hart2-vector-arithmetic',[]),('hart2-vector-move',['-DDMA_TEST_MOVE=1'])]:
        dma_cmd=[str(Path(args.cc).resolve()),'-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-mcmodel=medany','-nostdlib','-static','-Wl,--build-id=none','-T',str(HERE/'dma_guard.ld'),*defines,str(HERE/'dma_guard.S'),'-o',str(out/f'{stem}.elf')]
        subprocess.run(dma_cmd,check=True)
    inputs=[source/'benchmarks/Makefile']
    encoding=HERE/'source/riscv/encoding.h'
    for folder in ['common','env','vme-directed','vme-fused-lm2-gemm-transpose','vme-fp8-gemm']:
        inputs.extend(p for p in (source/'benchmarks'/folder).rglob('*') if p.is_file())
    manifest={'saturn_sha':pin,'compiler':str(Path(args.cc).resolve()),'compiler_sha256':sha(args.cc),'argv':cmd,'mx_argv':mx_cmd,'fp8_directed_argv':isolated,'cpu_dtypes_argv':cpu_cmd,'source_inputs':{str(p.relative_to(source)):sha(p) for p in sorted(inputs)},'encoding_header_sha256':sha(encoding),'dma_guard_inputs':{str(p):sha(p) for p in dma_inputs},'hart2_outputs':{p.name:sha(p) for p in out.glob('hart2-vector-*.elf')},'cpu_dtype_output':sha(out/'cpu-dtypes.elf'),'outputs':{p.name:sha(p) for p in out.glob('*.riscv')},'MSTATUS_MS_note':'Pinned Spike encoding.h provides MSTATUS_MS; Iris mode does not require MS.'}
    (out/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()
