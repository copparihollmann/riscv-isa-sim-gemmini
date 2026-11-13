#!/usr/bin/env python3
"""Freeze isolated integer actor source and exact02b4 reconstruction."""
from pathlib import Path
import argparse,difflib,hashlib,json,shlex,shutil,subprocess,tarfile,tempfile
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--build',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();B=a.build.resolve();O=a.output.resolve();O.mkdir();b=json.loads((B/'pipeline-build.json').read_text());S=Path(b['source']);P=R/'build/C12-source-composite-frozen-02b4a9ab-v2';pm=json.loads((P/'manifest.json').read_text());PS=Path(pm['source']);old=json.loads((P/'native-inventory.json').read_text());inv={n:sha(S/n)for n in sorted(set(old)|{'riscv/iris_vadd_eg_actor.inc'})};changed=[n for n,h in inv.items()if old.get(n)!=h];patch=''
 for n in changed:patch+='diff --git a/'+n+' b/'+n+'\n'+('new file mode 100644\n'if n not in old else'')+''.join(difflib.unified_diff((PS/n).read_text().splitlines(True)if n in old else[],(S/n).read_text().splitlines(True),fromfile='a/'+n if n in old else'/dev/null',tofile='b/'+n))
 (O/'VADD-EG-on-02b4.patch').write_text(patch);overlay=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=S);assert hashlib.sha256(overlay).hexdigest()==b['source_overlay_sha256'];(O/'source-overlay.patch').write_bytes(overlay);(O/'native-inventory.json').write_text(json.dumps(inv,sort_keys=True,indent=2)+'\n')
 with tarfile.open(O/'native-source.tar.gz','w:gz')as t:
  for n in inv:t.add(S/n,arcname=n,recursive=False)
 external={}
 for p in B.glob('*.d'):
  for x in shlex.split(p.read_text().replace('\\\n',' ').split(':',1)[1]):
   if x.endswith(':'):continue
   d=Path(x);d=d if d.is_absolute()else B/d;d=d.resolve()
   if d.is_file()and d.is_relative_to(R)and not d.is_relative_to(S)and not d.is_relative_to(B):external[str(d)]=sha(d)
 component=R/'build/rvv-integer-EG-source-frozen-v1';assert external[str(R/'timing/rvv_integer_eg_source_v1.hpp')]==json.loads((component/'manifest.json').read_text())['runtime_header_sha256'];(O/'compiled-inputs.json').write_text(json.dumps(external,sort_keys=True,indent=2)+'\n')
 for n in('spike','libsifive_uart.so','pipeline-build.json','parent-object-reuse.json'):shutil.copy2(B/n,O/n)
 assert sha(O/'spike')==b['binary_sha256']and sha(O/'libsifive_uart.so')==b['uart_sha256']
 with tempfile.TemporaryDirectory(prefix='VADD-native-reconstruct-')as tmp:
  d=Path(tmp)
  with(d/'base.tar').open('wb')as f:subprocess.run(['git','archive',b['base_commit']],cwd=S,stdout=f,check=True)
  with tarfile.open(d/'base.tar')as t:t.extractall(d/'native')
  subprocess.run(['git','apply','--unsafe-paths',str(O/'source-overlay.patch')],cwd=d/'native',check=True)
  for n,h in inv.items():assert sha(d/'native'/n)==h,n
  base=d/'parent';base.mkdir()
  with tarfile.open(P/'native-source.tar.gz')as t:
   for n,h in old.items():
    assert not Path(n).is_absolute()and'..'not in Path(n).parts;p=base/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(n).read());assert sha(p)==h
  subprocess.run(['git','apply','--unsafe-paths',str(O/'VADD-EG-on-02b4.patch')],cwd=base,check=True)
  for n,h in inv.items():assert sha(base/n)==h,n
 for n,h in old.items():assert sha(PS/n)==h,n
 names=['spike','libsifive_uart.so','pipeline-build.json','parent-object-reuse.json','VADD-EG-on-02b4.patch','source-overlay.patch','native-inventory.json','native-source.tar.gz','compiled-inputs.json'];m=dict(schema='iris.C12_integer_VADD_EG_native_capsule.v1',**{'pass':True},source_frozen=True,source=str(S),base_commit=b['base_commit'],binary_sha256=b['binary_sha256'],uart_sha256=b['uart_sha256'],native_device_abi=4,native_sources_reconstructed=len(inv),companion_reconstructed_against_exact02b4=True,parent_manifest_sha256=sha(P/'manifest.json'),component_manifest_sha256=sha(component/'manifest.json'),source_controller_sha256=sha(component/'sdk/rvv_integer_eg_source_v1.hpp'),changed_files=changed,external_compiled_inputs=len(external),artifact_sha256={n:sha(O/n)for n in names},selector_default_OFF=True,selector='empirical_vadd_eg compute-VADD-VV-fullVL-COMplus1-v1',source_VADD_issue_to_write_edges=1,source_VDQ4_IQ3=True,mixed_VRF_unit_consumers_drain=True,readonly_counter_CSR_overlap=True,preedge_busy_FENCE_and_other_consumers_guard=True,active_IRQ_context_refused=True,unknown_VSET_inputs_use_unchanged_original_XPR_definedness_guard=True,CPU_COMplus1_bridge_qualified=False,scope='harts0/1 VADD.VV fullVLmax unmasked vstart0 alignedLMUL1/2/4/8 SEW8/16/32/64 Mmode definedoperands VSdirty; literal/source-functional-knownVSETgeometry; perEGversioned privateoracle publication; otheractors conservativelydrain; activeIRQ/contextrefused; h2unchanged',parameters_fitted=False,hardware_contacted=False,protected_timing_labels_consumed=False,source_image_association=False,timing_2pct_certified=False,runtime_qualification_pending=True,new_clean_build=False);(O/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(O/'verification.json').write_text(json.dumps(dict(schema='iris.C12_integer_VADD_EG_source_reconstruction.v1',**{'pass':True},manifest_sha256=sha(O/'manifest.json'),native_sources_reconstructed=len(inv),exact02b4_parent_unchanged=True,full_overlay_and_parent_delta_reconstructed=True),indent=2)+'\n');print(json.dumps({'pass':True,'binary':b['binary_sha256'],'UART':b['uart_sha256'],'manifest_sha256':sha(O/'manifest.json')}))
if __name__=='__main__':main()
