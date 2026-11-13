#!/usr/bin/env python3
"""New source/byte capsule for the finite OPU queue/entry experiment."""
import argparse,difflib,hashlib,json,shlex,shutil,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'build/empirical-read-overlap-response-frozen-7bd58b4f'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--build',type=Path,required=True);ap.add_argument('--verify',action='store_true');a=ap.parse_args();o=a.output.resolve()
 if a.verify:
  m=json.load(open(o/'manifest.json'))
  assert sha(PARENT/'manifest.json')==m['parent_manifest_sha256']
  for name,h in m['artifact_sha256'].items():assert sha(o/name)==h,name
  for name,h in m['archived_source_sha256'].items():assert sha(o/'src'/name)==h,name
  source=Path(m['source']);inventory=json.load(open(o/'native-inventory.json'))
 else:
  b=a.build.resolve();receipt=json.load(open(b/'pipeline-build.json'));source=Path(receipt['source']);assert sha(b/'spike')==receipt['binary_sha256']and sha(b/'libsifive_uart.so')==receipt['uart_sha256'];parent=json.load(open(PARENT/'manifest.json'));inv=json.load(open(PARENT/'source-inventory.json'));prefix=parent['native_source_relative']+'/'
  old={name[len(prefix):]:digest for name,digest in inv.items()if name.startswith(prefix)}
  added=set(subprocess.check_output(['git','diff','--name-only','HEAD'],cwd=source,text=True).splitlines())-set(old)
  inventory={name:sha(source/name)for name in sorted(set(old)|added)};changed=[name for name in inventory if old.get(name)!=inventory[name]]
  expected={'riscv/iris_timing_adapter.h','riscv/iris_timing_adapter.cc','riscv/iris_empirical_async.inc','riscv/iris_shuttle_issue.cc','riscv/iris_counter_observations.cc','riscv/iris_empirical_features.inc','riscv/iris_opu_entry_overlap.inc'}
  assert set(changed)==expected,changed
  o.mkdir(parents=True,exist_ok=False);patch=''
  for name in sorted(changed):
   before=(PARENT/'src'/prefix/name).read_text().splitlines(True)if name in old else[];after=(source/name).read_text().splitlines(True)
   patch+='diff --git a/'+name+' b/'+name+'\n'+''.join(difflib.unified_diff(before,after,fromfile='a/'+name if name in old else'/dev/null',tofile='b/'+name))
  (o/'delta-on-7bd5.patch').write_text(patch);(o/'source-overlay.patch').write_bytes(subprocess.check_output(['git','diff','--binary','HEAD'],cwd=source));assert sha(o/'source-overlay.patch')==receipt['source_overlay_sha256']
  (o/'native-inventory.json').write_text(json.dumps(inventory,indent=2,sort_keys=True)+'\n')
  for name in('spike','libsifive_uart.so','pipeline-build.json'):shutil.copy2(b/name,o/name)
  paths={Path(__file__).resolve()}
  for dep in b.glob('*.d'):
   text=dep.read_text().replace('\\\n',' ')
   for token in shlex.split(text.split(':',1)[1]):
    if token.endswith(':'):continue
    p=Path(token);p=p if p.is_absolute()else b/p;p=p.resolve()
    if p.is_file()and p.is_relative_to(ROOT)and not p.is_relative_to(source)and not p.is_relative_to(b):paths.add(p)
  # Explicit source/evidence closure; avoid inspecting unrelated protected labels.
  paths.update(ROOT.glob('timing/overlap_completion*'))
  for folder in ['build/overlap-completion-queue-source-differential-v2','build/overlap-completion-entry-schedule-differential-v1','build/overlap-completion-entry-schedule-unit-v1','build/overlap-completion-OPU-entry-witness-v1','build/overlap-completion-fullcell-guards-guest-v1','build/overlap-completion-fullcell-guards-final-ON-v1','build/overlap-completion-idle-reaccept-final-v1','build/overlap-completion-refusal-guards-v5','build/overlap-completion-fetch-boundary-refusal-proof-v1','build/overlap-completion-entry-queue-final-ON-v1','build/overlap-completion-native-inputs-v4']:
   paths.update(p for p in(ROOT/folder).rglob('*')if p.is_file())
  copied={};external={}
  for p in sorted(paths):
   if not p.is_file():continue
   rel=str(p.relative_to(ROOT));external[rel]=sha(p)
   if inv.get(rel)==external[rel]:continue
   dst=o/'src'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst);copied[rel]=sha(dst)
  m={'schema':'iris.opu_entry_finite_native_capsule.v1','pass':True,'source_frozen':True,'source':str(source),'base_commit':receipt['base_commit'],'parent_manifest_sha256':sha(PARENT/'manifest.json'),'parent_manifest':str(PARENT/'manifest.json'),'binary_sha256':receipt['binary_sha256'],'uart_sha256':receipt['uart_sha256'],'native_changed_files':changed,'archived_source_sha256':copied,'external_source_sha256':external,'artifact_sha256':{n:sha(o/n)for n in('spike','libsifive_uart.so','pipeline-build.json','delta-on-7bd5.patch','source-overlay.patch','native-inventory.json')},'source_control_qualified':'conditional isolated MM TK1 stable defined VRF, VDQ4/IQ3/seq1, perentry FP8history; 321456 actual complete-unit comparisons','selector':'empirical_opu_entry source-VDQ4-IQ3-entry-MM-TK1-COMplus1-v2','selector_default':'off','CPU_bridge_scope':'Predict readiness for committed command at COM+1; conservative CPU admission without source PFC replay; not exact CPU/unitphase','FENCE_config_scope':'All physical writes drain conservatively; actual source backend_busy can clear before FP8 tail','IRQ_scope':'Active IRQ context phase unmodeled/refused','MM_CPU_fetch_scope':'Unsupported conservative MM fetch boundaries (including split4KiB) refused after older writes drain','calibrated':False,'full_timing_certified':False,'source_image_association':False,'held_out_2pct':False,'hardware_contacted':False,'clean_full_binary_rebuild_performed':False,'own_native_recompiled':True}
  (o/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 with tempfile.TemporaryDirectory(prefix='opu-entry-closure-')as tmp:
  d=Path(tmp)
  with(d/'base.tar').open('wb')as f:subprocess.run(['git','archive',m['base_commit']],cwd=source,stdout=f,check=True)
  with tarfile.open(d/'base.tar')as t:t.extractall(d/'native')
  subprocess.run(['git','apply','--unsafe-paths',str(PARENT/'source-overlay.patch')],cwd=d/'native',check=True);subprocess.run(['git','apply',str(o/'delta-on-7bd5.patch')],cwd=d/'native',check=True)
  for name,h in inventory.items():assert sha(d/'native'/name)==h,name
 report={'schema':'iris.opu_entry_source_reconstruction.v1','pass':True,'native_sources_reconstructed':len(inventory),'archived_sources_verified':len(m['archived_source_sha256']),'manifest_sha256':sha(o/'manifest.json'),'binary_sha256':m['binary_sha256'],'uart_sha256':m['uart_sha256'],'source_or_timing_certification':False,'hardware_contacted':False};(o/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
