#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(out):
    out.mkdir(parents=True,exist_ok=False);old=json.loads((ROOT/'build/empirical-vector-bypass-guest-v1/build.json').read_text())
    for hart in range(3):
        d=out/str(hart);d.mkdir();argv=old['argv'][:];argv.insert(1,'-DACTIVE_HART='+str(hart));argv=[str(ROOT/'pipeline/scalar_outer_guard_guest_v2.c')if x.endswith('/timing/empirical_vector_bypass_guest.c')else x for x in argv];argv[-1]=str(d/'guest.elf');r=subprocess.run(argv,capture_output=True);(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr)
        if r.returncode:raise ValueError(r.stderr.decode())
        inputs=[Path(__file__).resolve(),ROOT/'pipeline/scalar_outer_guard_guest_v2.c',*[ROOT/'benchmarks'/n for n in('runtime.c','runtime.h','start.S','link.ld','uart_drain.h')]]
        (d/'build.json').write_text(json.dumps({'pass':True,'active_hart':hart,'ELF_sha256':sha(d/'guest.elf'),'argv':argv,'synthetic_mechanics_only':True,'input_sha256':{str(p):sha(p)for p in inputs}},indent=2)+'\n')
    print('built3 exact512-coldload solo guards')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);main(p.parse_args().output.resolve())
