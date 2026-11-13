#!/usr/bin/env python3
"""Build exact ordinary and pending-IRQ warm-store witnesses with common CRT."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--irq',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);receipt=ROOT/'build/empirical-async-two-irq-unrolled-guest-v1/build.json';argv=json.loads(receipt.read_text())['argv'];source=ROOT/'timing/empirical_owned_store_guest.c';argv=[str(source)if x==str(ROOT/'timing/empirical_async_two_irq_unrolled_guest.c')else x for x in argv];argv[-1]=str(out/'guest.elf');argv.insert(1,'-DIRIS_STORE_IRQ='+str(int(a.irq)));inputs=[Path(__file__).resolve(),source,receipt,Path(argv[0]),*[ROOT/'benchmarks'/n for n in['start.S','runtime.c','runtime.h','link.ld','uart_drain.h']]];before={str(x):sha(x)for x in inputs};r=subprocess.run(argv,capture_output=True);(out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr.decode();assert all(sha(p)==d for p,d in before.items());report={'schema':'iris.empirical.owned_store_guest.v1','pass':True,'argv':argv,'input_sha256':before,'elf_sha256':sha(out/'guest.elf'),'IRQ_enabled':a.irq,'fitting_usable':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'guest.elf')
if __name__=='__main__':main()
