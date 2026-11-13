#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,subprocess
H=Path(__file__).resolve().parent;R=H.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--negative',choices=['IRQ','busy-peer','pending-IRQ','killed']);p.add_argument('--hart',type=int,choices=[0,1,2],default=0);a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False);c=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');rt=H/'runtime';elf=o/'guest.elf'
 cmd=[str(c),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none','-DIRIS_HARTS=3','-DIRIS_ACTIVE_HART='+str(a.hart),'-I'+str(rt),'-T',str(rt/'link.ld'),str(rt/'start.S'),str(rt/'runtime.c'),str(H/'guest.c'),'-lgcc','-o',str(elf)]
 if a.negative:cmd.insert(1,'-DIRIS_TEST_'+{'IRQ':'IRQ_ENABLE','busy-peer':'BUSY_PEER','pending-IRQ':'PENDING_IRQ','killed':'KILLED_STORE'}[a.negative])
 r=subprocess.run(cmd,capture_output=True);(o/'build.stdout').write_bytes(r.stdout);(o/'build.stderr').write_bytes(r.stderr)
 if r.returncode:raise ValueError(r.stderr.decode())
 paths=[Path(__file__),H/'guest.c',c,*rt.iterdir()];(o/'build.json').write_text(json.dumps(dict(schema='iris.vector_store_quarantine_guest.v1',argv=cmd,elf_sha256=sha(elf),negative=a.negative,physical_harts=3,active_hart=a.hart,active_words=256,checked_words=256,input_sha256={str(x):sha(x)for x in paths}),indent=2)+'\n');print(sha(elf))
if __name__=='__main__':main()
