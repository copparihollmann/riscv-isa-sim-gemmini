#!/usr/bin/env python3
"""Make a verified optional owned-store delta on immutable523."""
import argparse,hashlib,json,shutil,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--target',type=Path,default=ROOT/'build/empirical-owned-store-frozen-1aa8ca00');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);target=a.target.resolve();parent=ROOT/'build/empirical-rocket-RAS-frozen-52314001';tm=json.loads((target/'manifest.json').read_text());pm=json.loads((parent/'manifest.json').read_text());ti=json.loads((target/'source-inventory.json').read_text());pi=json.loads((parent/'source-inventory.json').read_text());tp=tm['native_source_relative']+'/';pp=pm['native_source_relative']+'/';native={n[len(tp):]:h for n,h in ti.items()if n.startswith(tp)};old={n[len(pp):]:h for n,h in pi.items()if n.startswith(pp)}
 def base(d):
  with tempfile.TemporaryFile()as f:
   subprocess.run(['git','-C',str(ROOT/'third_party/riscv-isa-sim'),'archive',tm['base_commit']],stdout=f,check=True);f.seek(0)
   with tarfile.open(fileobj=f)as t:t.extractall(d,filter='data')
  subprocess.run(['git','apply','--unsafe-paths',str(parent/'source-overlay.patch')],cwd=d,check=True,capture_output=True)
  assert all(sha(d/n)==h for n,h in old.items())
 with tempfile.TemporaryDirectory(prefix='iris-store-companion-')as tmp:
  d=Path(tmp);base(d)
  for argv in[['git','init','-q'],['git','config','user.name','Iris source-only comparison'],['git','config','user.email','source-only@invalid'],['git','add','.'],['git','commit','-qm','Exact frozen523 baseline']]:subprocess.run(argv,cwd=d,check=True)
  changed=[]
  for n,h in native.items():
   if old.get(n)!=h:
    q=d/n;q.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(target/'src'/tp/n,q);changed.append(n)
  for n in old.keys()-native.keys():(d/n).unlink();changed.append(n)
  subprocess.run(['git','add','-N','.'],cwd=d,check=True);patch=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=d);(out/'owned-store-on-523.patch').write_bytes(patch)
 with tempfile.TemporaryDirectory(prefix='iris-store-companion-check-')as tmp:
  d=Path(tmp);base(d);subprocess.run(['git','apply','--unsafe-paths',str(out/'owned-store-on-523.patch')],cwd=d,check=True,capture_output=True);assert all(sha(d/n)==h for n,h in native.items())
 helpers=['pipeline/store_front_runtime/'+n for n in ['empirical_engine.hpp','empirical_engine.cpp','empirical_history.hpp','empirical_memory_path.hpp','empirical_memory_path.cpp','empirical_scalar_memory.hpp','empirical_scalar_memory.cpp']]+['timing/empirical_cache_v6.hpp','timing/empirical_cache_v6.cpp'];helper_hashes={}
 for n in helpers:
  source=target/'src'/n;assert sha(source)==ti[n];dest=out/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);helper_hashes[n]=sha(dest)
 inputs=[Path(__file__).resolve(),parent/'manifest.json',parent/'verification.json',parent/'source-overlay.patch',parent/'source-inventory.json',target/'manifest.json',target/'verification.json',target/'source-inventory.json'];report={'schema':'iris.empirical.owned_store.companion.v1','pass':True,'native_delta_on':'frozen source-frontend523','parent_binary_sha256':pm['binary_sha256'],'target_binary_sha256':tm['binary_sha256'],'target_uart_sha256':tm['uart_sha256'],'patch_sha256':sha(out/'owned-store-on-523.patch'),'changed_native_files':sorted(changed),'all_target_native_files_reconstructed':len(native),'external_helper_sha256':helper_hashes,'external_helper_note':'copy these exact files under workspace pipeline before building; remaining523 helper dependencies stay bound to parent; V6 prior-cache parity proof d273bd95 remains separate','input_sha256':{str(x):sha(x)for x in inputs},'full_binary_rebuild_performed':False,'source_geometry_ownership_is_approximate':True,'timing_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json'),'patch_sha256':report['patch_sha256'],'native_files':len(changed)}))
if __name__=='__main__':main()
