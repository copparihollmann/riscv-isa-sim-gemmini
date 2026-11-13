#!/usr/bin/env python3
"""Create an exact, explicitly patched Zephyr worktree without changing the base."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0'
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--base',type=Path,default=ROOT/'third_party/zephyr');p.add_argument('--output',type=Path,default=ROOT/'third_party/zephyr-iris');p.add_argument('--patch',type=Path,default=ROOT/'zephyr/patches/0002-iris-vme-context.patch');a=p.parse_args()
    base=a.base.resolve();out=a.output.resolve();patch=a.patch.resolve()
    def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args])
    if git(base,'rev-parse','HEAD').decode().strip()!=PIN or git(base,'status','--porcelain'):raise RuntimeError('Base must be the clean exact Zephyr pin')
    if not out.exists():
        subprocess.run(['git','-C',str(base),'worktree','add','--detach',str(out),PIN],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['git','-C',str(out),'apply',str(patch)],check=True)
        subprocess.run(['git','-C',str(out),'add','-N','.'],check=True)
    if git(out,'rev-parse','HEAD').decode().strip()!=PIN or git(out,'diff','--binary','HEAD')!=patch.read_bytes() or git(out,'ls-files','--others','--exclude-standard'):raise RuntimeError('Derived tree differs from the requested explicit patch')
    print(json.dumps({'status':'verified_exact_derived_tree','base_sha':PIN,'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),'worktree':str(out)}))
if __name__=='__main__':main()
