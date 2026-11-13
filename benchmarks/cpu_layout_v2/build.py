#!/usr/bin/env python3
"""Rebuild the source-fixed layout batch into a NEW directory."""
import argparse,hashlib,json,pathlib,subprocess,sys
from generate import generate
ROOT=pathlib.Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--compiler',default='/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');x=a.parse_args();out=pathlib.Path(x.output).resolve()
 if (out/'batch.elf').exists():raise SystemExit('Refuse overwriting a completed ELF')
 generate(out);argv=[x.compiler,'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-fno-common','-mcmodel=medany','-mno-relax','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections,--no-relax','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks'),'-I'+str(out),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(ROOT/'benchmarks/cpu_layout_v2/main.c'),str(out/'layout.S'),'-lgcc','-o',str(out/'batch.elf')];r=subprocess.run(argv,text=True,capture_output=True);(out/'build.stdout').write_text(r.stdout);(out/'build.stderr').write_text(r.stderr)
 if r.returncode:raise SystemExit(r.stderr)
 inputs=[pathlib.Path(x.compiler),*[ROOT/('benchmarks/'+f) for f in ['start.S','runtime.c','runtime.h','uart_drain.h','link.ld','cpu_layout_v2/main.c','cpu_layout_v2/generate.py','cpu_layout_v2/build.py']],out/'layout.S',out/'functions.inc',out/'layout-meta.json'];(out/'build.json').write_text(json.dumps({'schema':'iris.cpu_layout_build.v1','argv':argv,'input_sha256':{str(p):sha(p) for p in inputs},'elf_sha256':sha(out/'batch.elf'),'fitting_only':True,'hardware_contacted':False},indent=2)+'\n');print(sha(out/'batch.elf'))
if __name__=='__main__':main()
