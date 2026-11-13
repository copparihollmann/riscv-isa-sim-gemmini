#!/usr/bin/env python3
"""Build full companion patches from clean baselines in private Git projections."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args])
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 candidate=a.candidate.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);patches=candidate/'integration/patches';patches.mkdir(exist_ok=True)
 repos={}
 for name,pin in [('merlin','d56133b168bbee3d73cb8b4304d3622d4191fc6a'),('iris-mlir','8447703ae5805271911e8ef232d8fd1aa7b6947d')]:
  projection=out/name;subprocess.run(['git','clone','--no-checkout','--no-hardlinks',str(ROOT/'third_party'/name),str(projection)],check=True,capture_output=True)
  subprocess.run(['git','-C',str(projection),'checkout','--detach',pin],check=True,capture_output=True)
  subprocess.run(['git','-C',str(projection),'reset','--hard',pin],check=True,capture_output=True)
  changed=git(ROOT/'integration'/name,'diff','--name-only','HEAD').decode().splitlines()
  changed+=['src/merlin/runtime/backends/device_simulator.py']if name=='merlin'else['configure_model.py','simulator.py','provenance.json']
  for path in sorted(set(changed)):
   source=candidate/'integration'/name/path;target=projection/path
   if source.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
   elif target.exists():target.unlink()
  for namebytes in git(projection,'ls-files','--others','--exclude-standard','-z').split(b'\0'):
   if namebytes:subprocess.run(['git','-C',str(projection),'add','-N','--',namebytes.decode()],check=True)
  patch=patches/(name+'.patch');patch.write_bytes(git(projection,'diff','--binary','HEAD'))
  subprocess.run(['git','-C',str(ROOT/'third_party'/name),'apply','--check',str(patch)],check=True,capture_output=True)
  files=git(projection,'diff','--name-only','HEAD').decode().splitlines()
  repos[name]={'baseline_commit':pin,'pristine_baseline':str(ROOT/'third_party'/name),'candidate_projection':str(projection),
   'intended_derived_worktree':str(ROOT/'integration'/name),'patch':'integration/patches/'+name+'.patch','patch_sha256':sha(patch),
   'patch_applies':True,'source_sha256':{path:sha(projection/path)for path in files if(projection/path).is_file()}}
  if name=='merlin':
   mirror=candidate/'integration/merlin/merlin/python/merlin/runtime/backends/device_simulator.py'
   if sha(mirror)!=sha(projection/'src/merlin/runtime/backends/device_simulator.py'):raise ValueError('Merlin source/python mirror differs')
 historical=candidate/'integration/manifest-before-sdk4.json';shutil.copyfile(ROOT/'integration/manifest.json',historical)
 result={'schema':'iris.companion_integration.v2','status':'sdk4_publication_candidate_not_published','repositories':repos,
  'historical_parent':{'path':'integration/manifest-before-sdk4.json','sha256':sha(historical),'scope':'Unchanged historical source/test associations; not relabeled as current tests'},
  'native_sha256':'35901887c93ab80aa92e68aac2f26cefa6cc785ae8251d5dc283471aa97faf5d',
  'launcher_sha256':'ca007ad96ad93afbec0c2d062e735ed5de00668f224535f74ce306b9c41d5b44','native_device_abi':4,
  'validation':'Fresh source/default/selftest/provider/Merlin candidate receipts are bound in the separate publication review closure.',
  'whole_model_qualified':False,'rtl_certified':False,'timing_calibrated':False,'published':False}
 (candidate/'integration/manifest.json').write_text(json.dumps(result,indent=2)+'\n');(out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'results.json')
if __name__=='__main__':main()
