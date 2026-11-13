#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');common=HERE.parent
 elf=out/'scalar.elf';start=ROOT/'board/rtl-loader/start-loader-bss.S'
 argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-mcmodel=medany','-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-nostdlib','-static','-Wl,--build-id=none','-I'+str(common),'-T',str(common/'link.ld'),str(start),str(HERE/'guest.c'),str(HERE/'streams.S'),'-lgcc','-o',str(elf)]
 r=subprocess.run(argv,capture_output=True,text=True);(out/'build.log').write_text(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError('compiler failed')
 symbols=subprocess.check_output([cc.with_name('riscv64-unknown-elf-nm'),'-n',elf],text=True);(out/'nm.txt').write_text(symbols)
 addresses={line.split()[-1]:int(line.split()[0],16) for line in symbols.splitlines() if len(line.split())==3}
 if addresses['begin_signature']!=addresses['mailbox'] or addresses['end_signature']-addresses['begin_signature']!=448:raise ValueError('signature layout mismatch')
 libgcc=Path(subprocess.check_output([cc,'-print-libgcc-file-name'],text=True).strip())
 paths=[cc,libgcc,start,HERE/'guest.c',HERE/'streams.S',HERE/'build.py',HERE/'collect.py',common/'runtime.h',common/'link.ld',ROOT/'hardware/manifest.json']
 receipt={'schema':'iris.scalar_reference_build.v1','argv':argv,'elf':str(elf),'elf_sha256':sha(elf),'input_sha256':{str(x):sha(x) for x in paths},'signature_bytes':448,
          'boot_abi':'explicit FESVR PT_LOAD zero fill, compact standalone RTL probe CRT; both model/reference use identical ELF','timing_calibrated':False}
 (out/'inputs').mkdir()
 for path,digest in receipt['input_sha256'].items():(out/'inputs'/digest).write_bytes(Path(path).read_bytes())
 (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(elf)
if __name__=='__main__':main()
