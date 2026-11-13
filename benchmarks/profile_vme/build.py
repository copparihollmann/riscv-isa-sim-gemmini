#!/usr/bin/env python3
"""Build a short three-hart profiling ELF from the existing matrix helpers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 original=ROOT/'benchmarks/v2/batch.c';source=original.read_text();helpers=source[source.index('static void matrix_mac('):source.index('static void prepare(')]
 guest=(ROOT/'benchmarks/profile_vme/guest.c').read_text().replace('/* SOURCE_MATRIX_HELPERS */',helpers)
 (out/'guest.c').write_text(guest)
 compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
 command=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks'),'-I'+str(ROOT/'third_party/saturn/benchmarks/common'),'-I'+str(ROOT/'third_party/riscv-isa-sim/riscv'),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(out/'guest.c'),'-lgcc','-o',str(out/'profile-vme.elf')]
 deps=[Path(__file__).resolve(),ROOT/'benchmarks/profile_vme/guest.c',original,out/'guest.c',compiler,*[ROOT/'benchmarks'/n for n in('start.S','runtime.c','runtime.h','uart_drain.h','link.ld')],ROOT/'third_party/saturn/benchmarks/common/vme.h',ROOT/'third_party/riscv-isa-sim/riscv/encoding.h']
 inputs={str(x):sha(x)for x in deps};r=subprocess.run(command,capture_output=True);(out/'compile.stdout').write_bytes(r.stdout);(out/'compile.stderr').write_bytes(r.stderr)
 report={'schema':'iris.short_VME_profile_build.v1','pass':r.returncode==0,'compiler_exit_status':r.returncode,'argv':command,'input_sha256':inputs,'source_helpers_byteequal':True,'source_helper_sha256':hashlib.sha256(helpers.encode()).hexdigest(),'physical_harts':3,'matrix_workers':[0,1],'vector_worker':2,'cases':['uint8-int32','E4M3-FP32'],'regions':6,'expected_output_words':144,'timing_calibration':False,'hardware_contacted':False}
 if r.returncode==0:report['elf_sha256']=sha(out/'profile-vme.elf')
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'elf_sha256':report.get('elf_sha256')}))
 if r.returncode:raise SystemExit(1)


if __name__=='__main__':main()
