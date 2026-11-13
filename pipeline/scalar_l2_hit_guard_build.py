#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(out):
    out.mkdir(parents=True,exist_ok=False);old=json.loads((ROOT/'build/empirical-vector-bypass-guest-v1/build.json').read_text());argv=old['argv'][:]
    argv=[str(ROOT/'pipeline/scalar_l2_hit_guard_guest.c')if x.endswith('/timing/empirical_vector_bypass_guest.c')else x for x in argv];argv[-1]=str(out/'guest.elf')
    paths=[Path(__file__).resolve(),ROOT/'pipeline/scalar_l2_hit_guard_guest.c',*[ROOT/'benchmarks'/n for n in('start.S','runtime.c','runtime.h','uart_drain.h','link.ld')],Path(argv[0])]
    r=subprocess.run(argv,capture_output=True);(out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
    if r.returncode:raise ValueError(r.stderr.decode())
    (out/'build.json').write_text(json.dumps({'pass':True,'argv':argv,'ELF_sha256':sha(out/'guest.elf'),'input_sha256':{str(p):sha(p)for p in paths},'synthetic_mechanics_only':True},indent=2)+'\n');print(sha(out/'guest.elf'))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);main(p.parse_args().output.resolve())
