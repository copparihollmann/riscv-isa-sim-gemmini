#!/usr/bin/env python3
"""Make a verified, reviewable native delta on immutable source-frontend901."""
import argparse,hashlib,json,shutil,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--target',type=Path,default=ROOT/'build/empirical-rocket-packets-frozen-cdeeca09');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);target=a.target.resolve();parent=ROOT/'build/fast-source-frontend-frozen-901cecd9';tm=json.loads((target/'manifest.json').read_text());pm=json.loads((parent/'manifest.json').read_text());ti=json.loads((target/'source-inventory.json').read_text());pi=json.loads((parent/'source-inventory.json').read_text());tp=tm['native_source_relative']+'/';pp=pm['native_source_relative']+'/';native={n[len(tp):]:h for n,h in ti.items()if n.startswith(tp)};old={n[len(pp):]:h for n,h in pi.items()if n.startswith(pp)}
 def base(d):
  with tempfile.TemporaryFile()as f:
   subprocess.run(['git','-C',str(ROOT/'third_party/riscv-isa-sim'),'archive',tm['base_commit']],stdout=f,check=True);f.seek(0)
   with tarfile.open(fileobj=f)as t:t.extractall(d,filter='data')
  subprocess.run(['git','apply','--unsafe-paths',str(parent/'source-overlay.patch')],cwd=d,check=True,capture_output=True)
  assert all(sha(d/n)==h for n,h in old.items())
 with tempfile.TemporaryDirectory(prefix='iris-Rocket-companion-')as tmp:
  d=Path(tmp);base(d)
  for argv in[['git','init','-q'],['git','config','user.name','Iris source-only comparison'],['git','config','user.email','source-only@invalid'],['git','add','.'],['git','commit','-qm','Exact frozen901 baseline']]:subprocess.run(argv,cwd=d,check=True)
  changed=[]
  for n,h in native.items():
   if old.get(n)!=h:
    q=d/n;q.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(target/'src'/tp/n,q);changed.append(n)
  for n in old.keys()-native.keys():(d/n).unlink();changed.append(n)
  subprocess.run(['git','add','-N','.'],cwd=d,check=True);patch=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=d);(out/'Rocket-packets-on-901.patch').write_bytes(patch)
 with tempfile.TemporaryDirectory(prefix='iris-Rocket-companion-check-')as tmp:
  d=Path(tmp);base(d);subprocess.run(['git','apply','--unsafe-paths',str(out/'Rocket-packets-on-901.patch')],cwd=d,check=True,capture_output=True);assert all(sha(d/n)==h for n,h in native.items())
 helpers=['pipeline/fast_rocket_ibuf.hpp','pipeline/fast_rocket_ibuf.cpp','pipeline/fast_rocket_rvc_fields.hpp','pipeline/fast_rocket_packets.hpp','pipeline/fast_rocket_packets_checked.cpp'];helper_hashes={}
 for n in helpers:
  source=target/'src'/n;assert sha(source)==ti[n];dest=out/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);helper_hashes[n]=sha(dest)
 inputs=[Path(__file__).resolve(),parent/'manifest.json',parent/'verification.json',parent/'source-overlay.patch',parent/'source-inventory.json',target/'manifest.json',target/'verification.json',target/'source-inventory.json'];report={'schema':'iris.empirical.Rocket_packet.companion.v1','pass':True,'native_delta_on':'frozen source-frontend901','parent_binary_sha256':pm['binary_sha256'],'target_binary_sha256':tm['binary_sha256'],'target_uart_sha256':tm['uart_sha256'],'patch_sha256':sha(out/'Rocket-packets-on-901.patch'),'changed_native_files':sorted(changed),'all_target_native_files_reconstructed':len(native),'external_helper_sha256':helper_hashes,'external_helper_note':'copy these exact files under workspace pipeline before building; existing sourceRVCtable and prior901 dependencies remain bound to parent closure','input_sha256':{str(x):sha(x)for x in inputs},'full_binary_rebuild_performed':False,'full_Rocket_frontend_translated':False,'timing_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json'),'patch_sha256':report['patch_sha256'],'native_files':len(changed)}))
if __name__=='__main__':main()
