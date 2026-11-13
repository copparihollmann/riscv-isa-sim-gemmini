#!/usr/bin/env python3
"""Build finite store-fault witness using an explicitly private trap handler."""
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mprv',action='store_true')
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    parent=ROOT/'build/empirical-owned-store-guest-v2/build.json'
    argv=json.loads(parent.read_text())['argv']
    common=ROOT/'benchmarks/runtime.c'
    text=common.read_text()
    text=text.replace('static unsigned arrivals, generation;',
      'volatile uint64_t expected_store_fault[3],store_fault_seen[3];\nstatic unsigned arrivals, generation;')
    marker='  fail(h,cause,pc,value);'
    assert text.count(marker)==1
    text=text.replace(marker,'  if ((cause==6 || cause==7) && expected_store_fault[h]==cause) {\n'
      '    expected_store_fault[h]=0; ++store_fault_seen[h]; return pc+4;\n  }\n'+marker)
    runtime=out/'private-runtime.c';runtime.write_text(text)
    guest=ROOT/'timing/empirical_owned_store_fault_guest.c'
    argv=[str(runtime) if x==str(common) else str(guest) if x==str(ROOT/'timing/empirical_owned_store_guest.c') else x for x in argv]
    argv[-1]=str(out/'guest.elf')
    argv.insert(1,'-DIRIS_STORE_TEST_MPRV='+str(int(a.mprv)))
    inputs=[Path(__file__).resolve(),parent,common,runtime,guest,Path(argv[0]),
      *[ROOT/'benchmarks'/n for n in ['start.S','runtime.h','link.ld','uart_drain.h']]]
    hashes={str(x):sha(x) for x in inputs}
    r=subprocess.run(argv,capture_output=True)
    (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
    assert r.returncode==0,r.stderr.decode()
    assert all(sha(p)==h for p,h in hashes.items())
    (out/'build.json').write_text(json.dumps({'pass':True,'argv':argv,'input_sha256':hashes,
      'elf_sha256':sha(out/'guest.elf'),'MPRV_refusal_control':a.mprv,
      'scope':'ROM/PMA, unmapped, misaligned store recovery; separate MPRV capability refusal; PMP configuration not qualified'},indent=2)+'\n')
    print(out/'guest.elf')
if __name__=='__main__':main()
