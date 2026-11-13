#!/usr/bin/env python3
"""Build the independently checked three-hart source journal observer control."""
import argparse,json,hashlib,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser(__doc__);a.add_argument('--output',type=Path,required=True);x=a.parse_args();out=x.output.resolve();out.mkdir(exist_ok=False)
 cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc').resolve();names=['start.S','runtime.c','runtime.h','uart_drain.h','link.ld'];src=ROOT/'timing/source_profile_smoke_v1.c';inputs=[Path(__file__).resolve(),src,cc,*[ROOT/'benchmarks'/n for n in names]];before={str(p):sha(p)for p in inputs}
 argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-fno-common','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks'),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(src),'-lgcc','-o',str(out/'guest.elf')]
 p=subprocess.run(argv,capture_output=True);(out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
 report=dict(schema='iris.source_profile_smoke_build.v1',argv=argv,exit_status=p.returncode,input_sha256=before,fitting_data=False)
 if p.returncode==0:report['ELF_sha256']=sha(out/'guest.elf')
 report['pass']=p.returncode==0 and all(sha(k)==v for k,v in before.items());(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['pass']else 1
if __name__=='__main__':raise SystemExit(main())
