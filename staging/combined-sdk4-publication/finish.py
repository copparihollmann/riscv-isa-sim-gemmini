#!/usr/bin/env python3
"""Finish source mirrors and SDK view hashes in an isolated publication candidate."""
import argparse,gzip,hashlib,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve();spike=root/'spike';release=(spike/'current').resolve();frozen=release/'evidence/combined';m=json.loads((frozen/'manifest.json').read_text())
 mirrors={'functional_fixture.cc':'build/definedness-dev/functional_fixture.cc','native_fp8_handlers_test.cc':'build/definedness-dev/native_fp8_handlers_test.cc','ieee_fma_handlers_test.cc':'build/definedness-dev/ieee_fma_handlers_test.cc','shared_fma_handlers_test.cc':'build/definedness-csr-dev/shared_fma_handlers_test.cc','fpcomp_handlers_test.cc':'build/definedness-csr-dev/fpcomp_handlers_test.cc','csr_handlers_test.cc':'build/definedness-dev/csr_handlers_test.cc','fpcomp_guest.c':'build/definedness-csr-dev/fpcomp_guest.c'}
 for target,name in mirrors.items():
  path=spike/target;historical=spike/'historical-5e6-dispatch'/target
  if path.exists()and not historical.exists():shutil.copyfile(path,historical)
  entry=m['files'][name];raw=(frozen/entry['object']).read_bytes();data=gzip.decompress(raw)if entry['compression']=='gzip'else raw
  if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Corrected source mirror corrupt')
  if target=='fpcomp_guest.c':data=data.replace(b'#include "runtime.h"',b'#include "../benchmarks/runtime.h"',1)
  path.write_bytes(data)
 shutil.copyfile(HERE/'README-primary.md',spike/'README.md');shutil.copyfile(HERE/'test_provider.py',spike/'tests/test_provider.py')
 # Preserve the live main Git checkout/object anchor. Current decoder/header
 # consumers select locked SDK4 source explicitly; reference archive remains
 # intentionally bound to the historical repository's exact base commit.
 retarget={
  'audit_fpcomp_decoder.py':[("ROOT/'third_party/riscv-isa-sim/riscv/encoding.h'","HERE/'source/riscv/encoding.h'")],
  'audit_shared_decoder.py':[("HERE.parent/'third_party/riscv-isa-sim/riscv/encoding.h'","HERE/'source/riscv/encoding.h'")],
  'compile_bitmanip.py':[("ROOT/'third_party/riscv-isa-sim/riscv'","HERE/'source/riscv'"),("ROOT/'third_party/riscv-isa-sim/riscv/encoding.h'","HERE/'source/riscv/encoding.h'")],
  'compile_fpcomp.py':[("ROOT/'third_party/riscv-isa-sim'","HERE/'source'")],
  'compile_ieee_fma.py':[("HERE.parent/'third_party/riscv-isa-sim/riscv/encoding.h'","HERE/'source/riscv/encoding.h'")],
  'compile_shared_fma.py':[("HERE.parent/'third_party/riscv-isa-sim/riscv/encoding.h'","HERE/'source/riscv/encoding.h'")],
  'compile_saturn.py':[("{HERE.parent}/third_party/riscv-isa-sim/riscv","{HERE}/source/riscv"),("HERE.parent/'third_party/riscv-isa-sim/riscv'","HERE/'source/riscv'"),("HERE.parent/'third_party/riscv-isa-sim/riscv/encoding.h'","HERE/'source/riscv/encoding.h'")]}
 for name,pairs in retarget.items():
  path=spike/name;text=path.read_text()
  for before,after in pairs:text=text.replace(before,after)
  path.write_text(text)
 # OOT source metadata describes current candidate bytes, not old test results.
 path=root/'integration/iris-mlir/provenance.json';record=json.loads(path.read_text())
 for item in record['files']:
  source=path.parent/item['path']
  if source.is_file():item['sha256']=sha(source)
 record['qualification']['sdk4_publication_candidate']=True
 record['qualification']['note']='Source metadata refreshed for launcher/native identity propagation; certification remains false. Fresh candidate gates are separate.'
 path.write_text(json.dumps(record,indent=2)+'\n')
 entries={}
 for directory in [release/'compat-sdk',release/'git-source']:
  for path in directory.rglob('*'):
   if path.is_file()and'.git'not in path.parts:entries[str(path.relative_to(release))]=sha(path)
 views={'schema':'iris.primary_sdk4.release_views.v1','input_sha256':entries,
  'native_device_abi':4,'scope':'Source-matched compatibility SDK and canonical Git inspection projection; native rebuild uses the locked portable source snapshot.',
  'canonical_overlay_sha256':'e33269e90102a8a9137473eb4d6a0c7c276a2553972ab4e668ab62f041a82060'}
 (release/'publication-inputs.json').write_text(json.dumps(views,indent=2)+'\n')
 print(release/'publication-inputs.json')
if __name__=='__main__':main()
