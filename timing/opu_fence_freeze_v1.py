#!/usr/bin/env python3
import argparse,difflib,hashlib,json,shlex,shutil,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--build',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();b=Path(a.build).resolve();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False);r=json.load(open(b/'pipeline-build.json'));s=Path(r['source']);parent=ROOT/'build/warm-OPU-TK124-frozen-c12a08f7-v1';pm=json.load(open(parent/'manifest.json'));pi=json.load(open(parent/'native-inventory.json'));expected={'riscv/iris_timing_adapter.h','riscv/iris_timing_adapter.cc','riscv/iris_opu_entry_overlap.inc','riscv/iris_opu_fence.inc'}
 assert sha(parent/'manifest.json')=='f89633ec15161cae9e6ed9ec030d4b9986d61cae8c1e65b8b81ade0087e1be0e'
 assert sha(b/'spike')==r['binary_sha256']and sha(b/'libsifive_uart.so')==r['uart_sha256']
 assert sha(parent/'native-source.tar.gz')==pm['artifact_sha256']['native-source.tar.gz']
 inv={n:sha(s/n)for n in set(pi)|expected};changed={n for n in inv if pi.get(n)!=inv[n]};assert changed==expected,changed;patch=''
 with tarfile.open(parent/'native-source.tar.gz')as t:
  for n in sorted(changed):
   before=t.extractfile(n).read().decode().splitlines(True)if n in pi else[];after=(s/n).read_text().splitlines(True);patch+='diff --git a/'+n+' b/'+n+'\n'+('new file mode 100644\n'if n not in pi else'')+''.join(difflib.unified_diff(before,after,fromfile='a/'+n if n in pi else'/dev/null',tofile='b/'+n))
 (o/'OPU-FM0-fence-on-C12.patch').write_text(patch);full=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=s);(o/'source-overlay.patch').write_bytes(full);assert sha(o/'source-overlay.patch')==r['source_overlay_sha256'];(o/'native-inventory.json').write_text(json.dumps(inv,sort_keys=True,indent=2)+'\n')
 with tarfile.open(o/'native-source.tar.gz','w:gz')as t:
  for n in sorted(inv):t.add(s/n,arcname=n,recursive=False)
 external={};old=json.load(open(parent/'compiled-inputs.json'))
 for dep in b.glob('*.d'):
  text=dep.read_text().replace('\\\n',' ')
  for x in shlex.split(text.split(':',1)[1]):
   if x.endswith(':'):continue
   p=Path(x);p=p if p.is_absolute()else b/p;p=p.resolve()
   if p.is_file()and p.is_relative_to(ROOT)and not p.is_relative_to(s)and not p.is_relative_to(b):external[str(p)]=sha(p)
 for p,h in external.items():assert old.get(p)==h,'unreviewed compiled external change: '+p
 (o/'compiled-inputs.json').write_text(json.dumps(external,sort_keys=True,indent=2)+'\n')
 for n in('spike','libsifive_uart.so','pipeline-build.json'):shutil.copy2(b/n,o/n)
 with tempfile.TemporaryDirectory(prefix='OPU-FENCE-reconstruct-')as tmp:
  d=Path(tmp)
  with(d/'base.tar').open('wb')as f:subprocess.run(['git','archive',r['base_commit']],cwd=s,stdout=f,check=True)
  with tarfile.open(d/'base.tar')as t:t.extractall(d/'native')
  subprocess.run(['git','apply','--unsafe-paths',str(o/'source-overlay.patch')],cwd=d/'native',check=True)
  for n,h in inv.items():assert sha(d/'native'/n)==h,n
  # Independently apply the small review companion to the exact parent archive.
  with tarfile.open(parent/'native-source.tar.gz')as t:t.extractall(d/'parent')
  subprocess.run(['git','apply','--unsafe-paths',str(o/'OPU-FM0-fence-on-C12.patch')],cwd=d/'parent',check=True)
  for n,h in inv.items():assert sha(d/'parent'/n)==h,n
 evidence=[ROOT/'build/opu-fence-source-v1/report.json',ROOT/'build/opu-fence-phase-v1/report.json',ROOT/'build/opu-fence-refusals-v2/report.json',*[ROOT/f'build/opu-fence-ON-fullcell-TK{tk}-v1/report.json'for tk in(2,4)],*[ROOT/f'build/opu-fence-finite-ON-seed{seed}-v2/report.json'for seed in(0,17)]]
 for p in evidence:assert json.load(open(p))['pass']is True,p
 artifacts=('spike','libsifive_uart.so','pipeline-build.json','OPU-FM0-fence-on-C12.patch','source-overlay.patch','native-inventory.json','native-source.tar.gz','compiled-inputs.json')
 m={'schema':'iris.OPU_FM0_FENCE_native_capsule.v1','pass':True,'source_frozen':True,'source':str(s),'base_commit':r['base_commit'],'binary_sha256':r['binary_sha256'],'uart_sha256':r['uart_sha256'],'native_device_abi':4,'parent_manifest_sha256':{str(parent/'manifest.json'):sha(parent/'manifest.json')},'changed_files_on_C12':sorted(changed),'native_sources_reconstructed':len(inv),'companion_reconstructed_against_exact_parent':True,'external_compiled_inputs':len(external),'all_external_compiled_inputs_identical_C12':True,'new_clean_native_build':True,'artifact_sha256':{n:sha(o/n)for n in artifacts},'qualification_sha256':{str(p):sha(p)for p in evidence},'selector_default':'OFF','selector':'source-MM-only-FM0-busy-not-numeric-tail-v1','qualified_encodings':[0x0330000f,0x0ff0000f],'unchanged_CPU_to_unit_bridge':'successfulCOM+1','full_CPU_VU_memory_phase_qualified':False,'memory_FADD_IRQ_consumer_guards_preserved':True,'parameters_fitted':False,'hardware_contacted':False,'source_image_association':False,'timing_2pct_certified':False,'scope':'Finite M-mode compute-hart MM-only busy-vs-numeric-tail FENCE admission. Exact source Core predicate and whole saved-unit tail witness; conservative CPU/scoreboard/memory/FADD quiescence. Other barriers and all consumers drain pending MRF versions. No universal FENCE/memory timing certification.'};(o/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');v={'schema':'iris.OPU_FM0_FENCE_reconstruction.v1','pass':True,'manifest_sha256':sha(o/'manifest.json'),'native_sources_reconstructed':len(inv),'companion_parent_source_exact':True,'compiled_external_inputs_unchanged':True,'source_or_timing_certification':False};(o/'verification.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'pass':True,'native':r['binary_sha256'],'UART':r['uart_sha256'],'manifest_sha256':sha(o/'manifest.json'),'companion_sha256':sha(o/'OPU-FM0-fence-on-C12.patch')}))
if __name__=='__main__':main()
