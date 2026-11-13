#!/usr/bin/env python3
"""Prove the minimal native delta on immutable7108 and archive its boundaries."""
from pathlib import Path
import difflib,hashlib,json,subprocess,tarfile,tempfile
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/rvv-vector-store-actor-companion-v2';o.mkdir(exist_ok=False);parent=R/'build/warm-OPU-frozen-7108a6ec-v1';native=R/'build/rvv-vector-store-actor-frozen-f9526584-v1';m=json.loads((native/'manifest.json').read_text());archived_final=native/'src'/m['native_source_relative'];oldmap=json.loads((parent/'native-inventory.json').read_text());changed=[];patch=[]
 with tempfile.TemporaryDirectory(prefix='iris-vse-parent-')as d:
  root=Path(d);d=root/'old';final=root/'new';d.mkdir();final.mkdir()
  with tarfile.open(parent/'native-source.tar.gz')as t:t.extractall(d,filter='data')
  with(root/'base.tar').open('wb')as f:subprocess.run(['git','-C',str(R/'third_party/riscv-isa-sim'),'archive',m['base_commit']],stdout=f,check=True)
  with tarfile.open(root/'base.tar')as t:t.extractall(final,filter='data')
  subprocess.run(['git','apply','--unsafe-paths',str(native/'source-overlay.patch')],cwd=final,check=True)
  for path in archived_final.rglob('*'):
   if path.is_file()and sha(path)!=sha(final/path.relative_to(archived_final)):raise ValueError('Archivedfinalsource mismatch')
  for name,digest in oldmap.items():
   if sha(d/name)!=digest:raise ValueError('Frozenparent archive mismatch '+name)
  names=set(oldmap)|{str(p.relative_to(final))for p in final.rglob('*')if p.is_file()}
  for name in sorted(names):
   a=d/name;b=final/name
   if a.exists()and b.exists()and sha(a)==sha(b):continue
   changed.append(name);before=a.read_text().splitlines(keepends=True)if a.exists()else[];after=b.read_text().splitlines(keepends=True)if b.exists()else[];patch.extend(difflib.unified_diff(before,after,fromfile='a/'+name if a.exists()else'/dev/null',tofile='b/'+name if b.exists()else'/dev/null'))
  p=o/'vector-store-on-7108.patch';p.write_text(''.join(patch));subprocess.run(['git','apply','--unsafe-paths',str(p)],cwd=d,check=True)
  for name in names:
   a=d/name;b=final/name
   if a.exists()!=b.exists()or(a.exists()and sha(a)!=sha(b)):raise ValueError('Companionreconstruction mismatch '+name)
 inputs=[Path(__file__),parent/'manifest.json',parent/'native-inventory.json',parent/'native-source.tar.gz',native/'manifest.json',native/'verification.json',o/'vector-store-on-7108.patch',R/'timing/rvv_store_sequence.hpp',R/'timing/rvv_store_sequence.cpp',R/'build/rvv-store-sequence-component-v1/report.json'];report=dict(schema='iris.finite_VSE32_companion_reconstruction.v1',status='passed',changed_native_files=changed,exact_frozen7108_parent_verified=True,exact_f952_successor_reconstructed=True,new_external_helpers=['timing/rvv_store_sequence.hpp','timing/rvv_store_sequence.cpp'],activation='DefaultOFF; guarded manualfixture only; no currentprovider/native/FPGA/source changes',conditional_boundaries=['CPU-frontCOMjoin','VRFread-to-A2edgefixturepath','effectiveboundedcreditVMU/TLpeer, notexactcompactor/segmenter/addressqueues','explicitrequiredsyntheticACK/Aservice'],input_sha256={str(p):sha(p)for p in inputs});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':'passed','changed_files':len(changed),'report_sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
