#!/usr/bin/env python3
"""Build the independent three-hart FADD numeric/publication witness."""
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--variant',choices=('numeric','opaque','irq','chain','alt'),default='numeric');p.add_argument('--bad-hart',type=int,choices=(0,1,2));a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc').resolve()
 source=ROOT/('timing/empirical_fadd_async'+(''if a.variant=='numeric'else'_'+a.variant)+'_guest.c');inputs=[Path(__file__).resolve(),source,cc,*[ROOT/('benchmarks/'+n)for n in('start.S','runtime.c','runtime.h','link.ld','uart_drain.h')]];before={str(x):sha(x)for x in inputs}
 argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffunction-sections','-fdata-sections','-fno-common','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks'),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(source),'-lgcc','-o',str(o/'guest.elf')]
 if a.bad_hart is not None:
  if a.variant!='opaque':raise ValueError('Unknown-consumer negatives apply only to opaque variant')
  argv.insert(1,'-DIRIS_FADD_BAD_HART='+str(a.bad_hart))
 r=subprocess.run(argv,capture_output=True);(o/'stdout').write_bytes(r.stdout);(o/'stderr').write_bytes(r.stderr)
 report={'schema':'iris.empirical.fadd_async_guest_build.v1','argv':argv,'exit_status':r.returncode,'input_sha256':before,'timing_or_fitting_usable':False,'unchanged':all(sha(x)==s for x,s in before.items())}
 if not r.returncode:report['input_sha256'][str(o/'guest.elf')]=sha(o/'guest.elf')
 (o/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
 if r.returncode or not report['unchanged']:raise SystemExit(1)
if __name__=='__main__':main()
