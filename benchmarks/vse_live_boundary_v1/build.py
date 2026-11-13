#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,subprocess
H=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--hart',type=int,choices=[0,1],default=0);p.add_argument('--negative',choices=['IRQ_ENABLE','PENDING_IRQ','BUSY_PEER','UNKNOWN_SOURCE','MISALIGNED','WRONG_EEW']);a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False)
 c=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');rt=H/'runtime';elf=o/'guest.elf'
 cmd=[str(c),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none','-DIRIS_HARTS=3','-DIRIS_ACTIVE_HART='+str(a.hart),'-I'+str(rt),'-T',str(rt/'link.ld'),str(rt/'start.S'),str(rt/'runtime.c'),str(H/'guest.c'),'-lgcc','-o',str(elf)]
 if a.negative:cmd.insert(1,'-DIRIS_TEST_'+a.negative)
 r=subprocess.run(cmd,capture_output=True);(o/'stdout').write_bytes(r.stdout);(o/'stderr').write_bytes(r.stderr)
 if r.returncode:raise RuntimeError(r.stderr.decode())
 inputs=[Path(__file__),H/'guest.c',c,*rt.iterdir()];report=dict(schema='iris.VSE_live_boundary_guest.v1',argv=cmd,elf_sha256=sha(elf),hart=a.hart,negative=a.negative,checked_words=512,stored_words=193,independent_expected_checksum=sum(13+11*j+i if i<n else 0xa5a5a5a5 for j,n in enumerate([1,4,8,16,32,64,64,4]) for i in range(64)),input_sha256={str(x):sha(x)for x in inputs});(o/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(elf))
if __name__=='__main__':main()
