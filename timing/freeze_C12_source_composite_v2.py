#!/usr/bin/env python3
"""Byte-bound reproducible composite; no inherited runtime qualification."""
import argparse,difflib,hashlib,json,shlex,shutil,subprocess,tarfile,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--build',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();B=a.build.resolve();O=a.output.resolve();O.mkdir(parents=True,exist_ok=False);b=json.loads((B/'pipeline-build.json').read_text());S=Path(b['source']);C=R/'build/warm-OPU-TK124-frozen-c12a08f7-v1';old=json.loads((C/'native-inventory.json').read_text());ps=Path(json.loads((C/'manifest.json').read_text())['source']);names=set(old)|{'riscv/iris_async_RRD_wake.inc','riscv/iris_opu_fence.inc','riscv/iris_fadd_eg_actor.inc'};inv={n:sha(S/n)for n in sorted(names)};changed=[n for n,h in inv.items()if old.get(n)!=h];patch=''
 for n in changed:
  before=(ps/n).read_text().splitlines(True)if n in old else[];patch+='diff --git a/'+n+' b/'+n+'\n'+('new file mode 100644\n'if n not in old else'')+''.join(difflib.unified_diff(before,(S/n).read_text().splitlines(True),fromfile='a/'+n if n in old else'/dev/null',tofile='b/'+n))
 (O/'source-corrections-on-C12.patch').write_text(patch);overlay=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=S);assert hashlib.sha256(overlay).hexdigest()==b['source_overlay_sha256'];(O/'source-overlay.patch').write_bytes(overlay);(O/'native-inventory.json').write_text(json.dumps(inv,indent=2,sort_keys=True)+'\n')
 with tarfile.open(O/'native-source.tar.gz','w:gz')as t:
  for n in sorted(inv):t.add(S/n,arcname=n,recursive=False)
 external={}
 for d in B.glob('*.d'):
  text=d.read_text().replace('\\\n',' ')
  for x in shlex.split(text.split(':',1)[1]):
   if x.endswith(':'):continue
   p=Path(x);p=p if p.is_absolute()else B/p;p=p.resolve()
   if p.is_file()and p.is_relative_to(R)and not p.is_relative_to(S)and not p.is_relative_to(B):external[str(p)]=sha(p)
 assert external[str(R/'timing/rvv_fadd_eg_source_v1.hpp')]=='eeb8abc8d15b1275895709179ad634ea66c072294fd5eba4175e494bbb3ff232'
 (O/'compiled-inputs.json').write_text(json.dumps(external,sort_keys=True,indent=2)+'\n')
 for n in('spike','libsifive_uart.so','pipeline-build.json','parent-object-reuse.json'):shutil.copy2(B/n,O/n)
 assert sha(O/'spike')==b['binary_sha256']and sha(O/'libsifive_uart.so')==b['uart_sha256']
 with tempfile.TemporaryDirectory(prefix='C12-composite-reconstruct-')as tmp:
  d=Path(tmp)
  with(d/'base.tar').open('wb')as f:subprocess.run(['git','archive',b['base_commit']],cwd=S,stdout=f,check=True)
  with tarfile.open(d/'base.tar')as t:t.extractall(d/'source')
  subprocess.run(['git','apply','--unsafe-paths',str(O/'source-overlay.patch')],cwd=d/'source',check=True)
  for n,h in inv.items():assert sha(d/'source'/n)==h,n
  parent=d/'parent';parent.mkdir()
  with tarfile.open(C/'native-source.tar.gz')as t:
   for n,h in old.items():
    assert not Path(n).is_absolute()and'..'not in Path(n).parts;p=parent/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(n).read());assert sha(p)==h
  subprocess.run(['git','apply','--unsafe-paths',str(O/'source-corrections-on-C12.patch')],cwd=parent,check=True)
  for n,h in inv.items():assert sha(parent/n)==h,n
 for n,h in old.items():assert sha(ps/n)==h,n
 parents=[C,R/'build/C12-pending-base-frozen-2c40dca7-v1',R/'build/C12-async-RRD-wake-frozen-8fcf4e98-v2',R/'build/opu-fence-frozen-ee65eee0-v1',R/'build/FADD-EG-actor-corrective-frozen-v2',R/'build/FADD-EG-counterCSR-frozen-cb668b7f-v1',R/'build/FADD-EG-counterCSR-frozen-8a8cf119-v2',R/'build/C12-source-composite-frozen-cb21e2d6-v1'];prep=R/'build/C12-composite-preparation-v2';files=['spike','libsifive_uart.so','pipeline-build.json','parent-object-reuse.json','source-corrections-on-C12.patch','source-overlay.patch','native-inventory.json','native-source.tar.gz','compiled-inputs.json']
 m=dict(schema='iris.C12_source_composite_native_capsule.v2',**{'pass':True},source_frozen=True,source=str(S),base_commit=b['base_commit'],binary_sha256=b['binary_sha256'],uart_sha256=b['uart_sha256'],native_device_abi=4,native_sources_reconstructed=len(inv),companion_reconstructed_against_exact_C12=True,external_compiled_inputs=len(external),changed_files_on_C12=changed,artifact_sha256={n:sha(O/n)for n in files},parent_manifest_sha256={str(p/'manifest.json'):sha(p/'manifest.json')for p in parents},composition_input_sha256={str(p):sha(p)for p in [Path(__file__).resolve(),*[p for p in prep.glob('*.json')]]},selectors_default_OFF=True,late_ALU_included=False,scalar_cache_alpha_beta_and_Shuttle_random_unchanged=True,FADD_FENCE_preedge_final_write_busy_preserved=True,FADD_independent_counter_CSR_optin=True,scope='harts0/1 pending-base-RRD retry + legacy async eligibility wake + finite MM-only FENCE + saved HSD fullVL flags0 FADD perEG controller with independent cycle-instret CSR; successfulCOM+1 CPU-unit bridge remains experimental; FADD/MM activeIRQ and unsupported context refuse; no full CPU or timing certificate',runtime_qualification_pending=True,parameters_fitted=False,hardware_contacted=False,source_image_association=False,timing_2pct_certified=False)
 (O/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(O/'verification.json').write_text(json.dumps(dict(schema='iris.C12_source_composite_reconstruction.v2',**{'pass':True},manifest_sha256=sha(O/'manifest.json'),native_sources_reconstructed=len(inv),exact_C12_parent_unchanged=True,source_companion_and_full_overlay_reconstructed=True,inherited_runtime_qualification=False),indent=2)+'\n');print(json.dumps({'pass':True,'native':b['binary_sha256'],'UART':b['uart_sha256'],'manifest_sha256':sha(O/'manifest.json')}))
if __name__=='__main__':main()
