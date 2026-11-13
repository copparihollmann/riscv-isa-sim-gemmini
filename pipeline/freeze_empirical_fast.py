#!/usr/bin/env python3
"""Compact source/byte closure for a fast native epoch; no certification inference."""
import argparse,hashlib,json,shlex,shutil,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--build',type=Path,default=ROOT/'build/spike-empirical-fast-v1');p.add_argument('--include',action='append',type=Path,default=[],help='Additional exact source/evidence file or directory to archive; relative to workspace.');p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
 if a.verify:
  m=json.loads((out/'manifest.json').read_text())
  for name,digest in m['artifact_sha256'].items():
   if sha(out/name)!=digest:raise ValueError('archived artifact changed: '+name)
  inventory=json.loads((out/'source-inventory.json').read_text())
  for name,digest in inventory.items():
   if sha(out/'src'/name)!=digest:raise ValueError('archived source changed: '+name)
  # Independently reconstruct the native source from the pinned unmodified base.
  with tempfile.TemporaryDirectory(prefix='iris-empirical-source-')as d:
   tree=Path(d);base=ROOT/'third_party/riscv-isa-sim'
   with(tree/'base.tar').open('wb')as f:subprocess.run(['git','-C',str(base),'archive',m['base_commit']],stdout=f,check=True)
   with tarfile.open(tree/'base.tar')as t:t.extractall(tree/'native',filter='data')
   subprocess.run(['git','apply','--unsafe-paths',str(out/'source-overlay.patch')],cwd=tree/'native',check=True)
   prefix=m['native_source_relative']+'/'
   native_count=0
   for name,digest in inventory.items():
    if name.startswith(prefix):
     if sha(tree/'native'/name[len(prefix):])!=digest:raise ValueError('reconstructed source mismatch: '+name)
     native_count+=1
  r=dict(schema='iris.empirical.source_closure_verification.v1',pass_=True,**{'pass':True},binary_sha256=m['binary_sha256'],uart_sha256=m['uart_sha256'],archived_sources_verified=len(inventory),reconstructed_native_sources_verified=native_count,manifest_sha256=sha(out/'manifest.json'),input_sha256={str(out/'manifest.json'):sha(out/'manifest.json'),str(out/'source-inventory.json'):sha(out/'source-inventory.json')},full_binary_rebuild_performed=False,source_or_timing_certified=False)
  (out/'verification.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return
 build=a.build.resolve();receipt=json.loads((build/'pipeline-build.json').read_text());source=Path(receipt['source']);before=sha(build/'spike'),sha(build/'libsifive_uart.so')
 if before!=(receipt['binary_sha256'],receipt['uart_sha256']):raise ValueError('build identity mismatch')
 out.mkdir(exist_ok=False,parents=True);src=out/'src';src.mkdir()
 paths={Path(__file__).resolve(),build/'pipeline-build.json'}
 for dep in build.glob('*.d'):
  text=dep.read_text().replace('\\\n',' ');tokens=shlex.split(text.split(':',1)[1])
  for token in tokens:
   if token.endswith(':'):continue
   q=Path(token);q=q if q.is_absolute()else build/q
   q=q.resolve()
   if q.is_file()and q.is_relative_to(ROOT):paths.add(q)
 # The source-overlay contains every modified/new native file; include its
 # currently uncompiled inputs too, rather than relying on a narrow MMD set.
 for token in subprocess.check_output(['git','-C',str(source),'diff','--name-only','HEAD'],text=True).splitlines():paths.add(source/token)
 owned=['empirical_engine.hpp','empirical_engine.cpp','empirical_history.hpp','empirical_memory_path.hpp','empirical_memory_path.cpp','empirical_scalar_memory.hpp','empirical_scalar_memory.cpp','empirical_counter_clock.hpp','build_native_empirical.py','uart-plugin-abi4.cc']
 paths.update(ROOT/'pipeline'/x for x in owned);paths.update(ROOT/'timing'/x for x in ['empirical_cache.hpp','empirical_cache.cpp'])
 paths.update(ROOT/x for x in ['build/empirical-runtime-first-v1/fast.fixture','calibration/empirical-v1/parameters.json','calibration/empirical-v1/fixture-draft-v1/residual.fixture','calibration/empirical-runtime-candidate-v1/cache-service.fixture','calibration/empirical-runtime-candidate-v1/mapping.json','build/saturn-native-frozen-16972504/manifest.json','build/empirical-counter-span-v1/check.cpp','build/empirical-counter-span-v1/stdout','build/empirical-cache-v1/report.json'])
 for extra in ['timing/empirical_vector_bypass_guest.c','timing/build_empirical_vector_bypass_guest.py','timing/check_empirical_vector_bypass.py','build/empirical-vector-bypass-guest-v1/guest.elf','build/empirical-vector-bypass-guest-v1/build.json','build/empirical-vector-bypass-proof-v1/report.json','build/empirical-vector-package-v1/report.json','timing/empirical_cache_v3.hpp','timing/empirical_cache_v3.cpp','build/empirical-cache-v3/report.json','timing/empirical_cache_v4.hpp','timing/empirical_cache_v4.cpp','build/empirical-cache-v4/report.json','timing/empirical_cache_v5.hpp','timing/empirical_cache_v5.cpp','build/empirical-cache-v5/report.json','build/empirical-icache-liveness-v5-v1/report.json','build/empirical-icache-v5-selftest-v3/check/report.json','build/empirical-icache-v5-selftest-v3/sensitivity.fixture','calibration/empirical-131c-runtime-v2/runtime.fixture','build/empirical-load-front-directed-v2/report.json','timing/empirical_cache_v2.hpp','timing/empirical_cache_v2.cpp','build/empirical-cache-v2/report.json','timing/empirical_compressed_memory_guest.c','timing/build_empirical_compressed_memory_guest.py','build/empirical-compressed-memory-guest-v1/build.json','build/empirical-compressed-memory-guest-v1/guest.elf','build/empirical-compressed-memory-guest-v1/disassembly.txt','build/empirical-compressed-memory-proof-v1/report.json','timing/empirical_async_irq_guest.c','timing/build_empirical_async_irq_guest.py','build/empirical-async-irq-guest-v1/guest.elf','build/empirical-async-irq-guest-v1/build.json','build/empirical-async-irq-v1/checks.json','build/empirical-async-irq-v1/results.json']:
  q=ROOT/extra
  if q.exists():paths.add(q)
 for extra in ['build/empirical-critical-cpu-fixes-selftest-v1/report.json','build/empirical-critical-cpu-fixes-async-v1/report.json','build/empirical-critical-cpu-guard-v1/report.json','build/empirical-critical-cpu-guard-v1/check.cpp','build/empirical-critical-cpu-guard-v1/stdout','build/empirical-boundary-retry-mixed-v1/report.json','build/empirical-boundary-retry-mixed-v1/independent-check.json','build/empirical-old6750-cancel-diagnostic-proof-v1/report.json']:
  paths.add(ROOT/extra)
 for extra in ['build/empirical-load-owner-coherence-v1/report.json','build/empirical-load-owner-package-v1/report.json','build/empirical-load-owner-async-guards-v1/report.json']:
  if (ROOT/extra).is_file():paths.add(ROOT/extra)
 for pattern in ['timing/empirical_async_two*.c','timing/build_empirical_async_two*.py','timing/empirical_load_front*.c','timing/build_empirical_load_front*.py']:
  paths.update(ROOT.glob(pattern))
 paths.add(ROOT/'pipeline/check_empirical_async_queue.py')
 for extra in ['build/empirical-next-queue2-first-v1/baseline.fixture','build/empirical-next-queue2-first-v1/mechanics-costed.fixture','build/empirical-next-queue2-first-v1/mechanics-slow.fixture','build/empirical-next-queue2-selftest-v1/report.json','build/empirical-next-queue2-vector-proof-v1/report.json','build/empirical-async-two-queue-guards-final-v2/report.json','build/empirical-load-front-final-v1/report.json']:
  paths.add(ROOT/extra)
 for folder in ['build/empirical-async-two-irq-unrolled-guest-v1','build/empirical-async-two-irq-shifted-guest-v1','build/empirical-load-front-guest-v2',*[f'build/empirical-load-front-undefined-h{h}-v1'for h in range(3)]]:
  for name in ['guest.elf','build.json']:paths.add(ROOT/folder/name)
 # Finite FADD successor evidence; older epochs retain their own archived tool.
 for pattern in ['timing/empirical_fadd_async*.c','timing/build_empirical_fadd_async_guest.py','pipeline/check_empirical_fadd_async.py']:
  paths.update(ROOT.glob(pattern))
 if (ROOT/'build/empirical-fadd-async-proof-v3/report.json').is_file():
  for folder in ['build/empirical-fadd-async-proof-v3','build/empirical-fadd-source-contract-v1','build/empirical-fadd-first-v1','build/empirical-fadd-async-guest-v3','build/empirical-fadd-opaque-guest-v3','build/empirical-fadd-irq-guest-v2','build/empirical-fadd-chain-guest-v2','build/empirical-fadd-alt-guest-v1',*[f'build/empirical-fadd-opaque-bad{h}-v2'for h in range(3)]]:
   paths.update(q for q in (ROOT/folder).rglob('*')if q.is_file())
  for name in ['manifest.json','verification.json','spike','libsifive_uart.so']:
   paths.add(ROOT/'build/empirical-fast-frozen-05775560'/name)
 if source.name=='riscv-isa-sim-empirical-optimized':
  paths.update(ROOT/'pipeline'/x for x in ['empirical_hazards.hpp','check_empirical_hazards.cpp','check_empirical_host_optimization.py','verify_empirical_host_evidence.py'])
  paths.update(q for q in (ROOT/'build/empirical-host-optimization-closure-v1').iterdir()if q.is_file())
  for name in ['manifest.json','verification.json']:
   paths.add(ROOT/'build/empirical-fast-frozen-28a0a52b'/name)
 for extra in a.include:
  extra=extra if extra.is_absolute()else ROOT/extra
  if not extra.exists()or not extra.resolve().is_relative_to(ROOT):raise ValueError('invalid additional workspace input '+str(extra))
  paths.update(q for q in extra.rglob('*')if q.is_file())if extra.is_dir()else paths.add(extra)
 inventory={}
 for q in sorted(paths):
  if not q.is_file():raise ValueError('missing source '+str(q))
  name=str(q.relative_to(ROOT));dest=src/name;dest.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(q,dest);inventory[name]=sha(dest)
 (out/'source-inventory.json').write_text(json.dumps(inventory,sort_keys=True,indent=2)+'\n')
 patch=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD']);(out/'source-overlay.patch').write_bytes(patch)
 for name in ['spike','libsifive_uart.so','pipeline-build.json']:shutil.copy2(build/name,out/name)
 parent=ROOT/'build/saturn-native-frozen-16972504/manifest.json'
 top=['source-inventory.json','source-overlay.patch','spike','libsifive_uart.so','pipeline-build.json']
 m=dict(schema='iris.empirical.fast_source_capsule.v1',status='frozen_experimental_fast_native_source_bytes',base_commit='72958551566a30f19444bd7e354552824e4d0a98',parent_manifest_sha256=sha(parent),binary_sha256=before[0],uart_sha256=before[1],native_source_relative=str(source.relative_to(ROOT)),source_overlay_sha256=sha(out/'source-overlay.patch'),source_count=len(inventory),artifact_sha256={n:sha(out/n)for n in top},input_sha256={str(parent):sha(parent),str(out/'source-overlay.patch'):sha(out/'source-overlay.patch'),str(out/'source-inventory.json'):sha(out/'source-inventory.json')},source_cuts_evaluated=False,calibration_scope='experimental_effective_services_not_full_model',timing_certified=False,held_out_2pct=False,full_binary_rebuild_performed=False)
 (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 if before!=(sha(build/'spike'),sha(build/'libsifive_uart.so')):raise ValueError('native changed while freezing')
 print(json.dumps(dict(binary_sha256=before[0],uart_sha256=before[1],sources=len(inventory),manifest_sha256=sha(out/'manifest.json'))))
if __name__=='__main__':main()
