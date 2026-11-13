#!/usr/bin/env python3
"""Real unknown-address refusals and wrongpath non-observation on all harts."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 source=ROOT/'timing/empirical_owned_store_unknown_guest.c';build=json.loads((ROOT/'build/empirical-owned-store-guest-v2/build.json').read_text())['argv'];base=json.loads((ROOT/'build/rocket-packet-native-first-v1/report.json').read_text())['argv'];records=[]
 for h in range(3):
  for wrongpath in (False,True):
   d=out/f'h{h}-wrongpath{int(wrongpath)}';d.mkdir();elf=d/'guest.elf';args=[str(source)if x==str(ROOT/'timing/empirical_owned_store_guest.c')else x for x in build];args[1:1]=[f'-DIRIS_BAD_HART={h}',f'-DIRIS_STORE_WRONGPATH={int(wrongpath)}'];args[-1]=str(elf);r=subprocess.run(args,capture_output=True);(d/'build.stdout').write_bytes(r.stdout);(d/'build.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr
   f=d/'fixture';f.write_text((ROOT/'build/rocket-packet-native-first-v1/first.fixture').read_text()+'\nempirical_store_front owned-dirty-L1-COM-v1\nempirical_read_overlap response-ready-L1-read-only-v2\nempirical_dcache_random shuttle-miss-allocation-proxy-v1\n');argv=[x for x in base if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))];argv[0]=str(a.binary.resolve());argv=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else x for x in argv];argv[-1]=str(elf);argv[-1:-1]=['--iris-timing-fixture='+str(f),'--iris-timing-trace='+str(d/'summary.json')];r=subprocess.run(argv,capture_output=True,timeout=60);(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr)
   if wrongpath:assert r.returncode==0 and b'IRIS_UNKNOWN_STORE_WRONGPATH_PASS' in r.stdout,(h,r.returncode,r.stderr)
   else:assert r.returncode==1 and b'IRIS_UNDEFINED_STATE'in r.stderr and b'unit=empirical-memory-address'in r.stderr and f'hart={h}'.encode()in r.stderr,(h,r.returncode,r.stderr)
   records.append({'hart':h,'wrongpath':wrongpath,'returncode':r.returncode,'argv':argv,'build_argv':args,'elf_sha256':sha(elf),'stderr_sha256':sha(d/'stderr')})
 report={'schema':'iris.owned_store_unknown_address_controls.v1','pass':True,'binary_sha256':sha(a.binary),'uart_sha256':sha(a.uart),'unknown_addresses_refused':3,'wrongpath_unknown_addresses_unobserved':3,'source_sha256':sha(source),'checker_sha256':sha(__file__),'records':records};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':main()
