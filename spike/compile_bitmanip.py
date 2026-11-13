#!/usr/bin/env python3
"""Build per-hart scalar/vector bitmanip probes without enabling scalar B globally."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    args=parser.parse_args();bench=ROOT/'benchmarks'
    base=[str(args.compiler.resolve()),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin',
         '-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei',
         '-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-I'+str(bench),
         '-I'+str(HERE/'source/riscv'),'-T',str(bench/'link.ld'),str(bench/'start.S'),
         str(bench/'runtime.c')]
    commands=[];outputs={}
    for name in ['bitmanip','cease','cpu_config']:
        elf=HERE/('benchmarks/'+name+'.elf');cmd=base+[str(HERE/(name+'_guest.c')),'-lgcc','-o',str(elf)]
        subprocess.run(cmd,check=True);commands.append(cmd);outputs[name]=sha(elf)
    inputs=[Path(__file__),HERE/'bitmanip_guest.c',HERE/'cease_guest.c',HERE/'cpu_config_guest.c',bench/'start.S',bench/'runtime.c',bench/'uart_drain.h',bench/'uart_drain.S',bench/'runtime.h',bench/'link.ld',
            HERE/'source/riscv/encoding.h']
    (HERE/'benchmarks/bitmanip-build.json').write_text(json.dumps({'commands':commands,'compiler_sha256':sha(args.compiler),
        'input_sha256':{str(path):sha(path) for path in inputs},'elf_sha256':outputs},indent=2)+'\n')
if __name__=='__main__':main()
