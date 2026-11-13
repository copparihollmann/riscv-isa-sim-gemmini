#!/usr/bin/env python3
"""Create a disjoint source-exact FADD+shape candidate, preserving every parent."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PIN='72958551566a30f19444bd7e354552824e4d0a98'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source=ROOT/'pipeline/riscv-isa-sim-fadd-shape-store-v2'
    build=ROOT/'build/spike-fadd-shape-store-v2'
    out=ROOT/'build/fadd-shape-store-composition-v2'
    parent=ROOT/'build/fadd-shape-frozen-7de1c02d'
    oldsource=ROOT/'pipeline/riscv-isa-sim-fadd-shape-v2'
    oldbuild=ROOT/'build/spike-fadd-shape-v2'
    base=ROOT/'build/empirical-rocket-RAS-frozen-52314001'
    store=ROOT/'build/empirical-owned-store-frozen-1aa8ca00'
    for p in (source,build,out):
        if p.exists():raise ValueError('Fresh composition paths required: '+str(p))
    if sha(parent/'manifest.json')!='776d4fa511daf4a9b15374bb42f33b78c18f5d987cc26733f15b853836a5fb1e':
        raise ValueError('FADD source/evidence capsule identity changed')
    m=json.loads((parent/'manifest.json').read_text())
    for name,digest in m['artifact_sha256'].items():
        if sha(parent/name)!=digest:raise ValueError('Parent artifact changed')
    if sha(oldbuild/'spike')!=m['binary_sha256']:raise ValueError('Reusable object build is not frozen parent epoch')
    out.mkdir(); commands=[]
    def run(argv,cwd=None):
        subprocess.run(argv,cwd=cwd,check=True);commands.append({'argv':argv,'cwd':str(cwd or ROOT),'exit_status':0})
    run(['git','clone','--shared','--no-checkout',str(ROOT/'third_party/riscv-isa-sim'),str(source)])
    run(['git','-C',str(source),'checkout','--detach',PIN])
    run(['git','-C',str(source),'apply',str(parent/'source-overlay.patch')])
    inventory=json.loads((parent/'source-inventory.json').read_text());prefix=m['native_source_relative']+'/'
    verified=0
    for name,digest in inventory.items():
        if name.startswith(prefix):
            rel=name[len(prefix):];p=source/rel
            if sha(p)!=digest or sha(oldsource/rel)!=digest:raise ValueError('Parent source reconstruction mismatch: '+rel)
            stat=(oldsource/rel).stat();os.utime(p,ns=(stat.st_atime_ns,stat.st_mtime_ns));verified+=1
    # Baseline files not selected by MMD are checked too before object reuse.
    for p in source.rglob('*'):
        if not p.is_file()or '.git'in p.relative_to(source).parts:continue
        rel=p.relative_to(source);q=oldsource/rel
        if not q.is_file()or p.read_bytes()!=q.read_bytes():raise ValueError('Complete source equality failed: '+str(rel))
        stat=q.stat();os.utime(p,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    companion_path=ROOT/'build/owned-store-companion-on-523-v1/report.json'
    companion=json.loads(companion_path.read_text())
    if sha(ROOT/'build/owned-store-companion-on-523-v1/owned-store-on-523.patch')!='72be305d86e5a34f542591d8e21155903b7b83c3c111531b3ad1f3ac42d3dc8f':
        raise ValueError('Frozen store companion changed')
    for name,digest in companion['external_helper_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('External store runtime/helper changed: '+name)
    base_prefix=json.loads((base/'manifest.json').read_text())['native_source_relative']
    store_prefix=json.loads((store/'manifest.json').read_text())['native_source_relative']
    merge_root=out/'merge-inputs';merge_root.mkdir();resolutions=[];conflicts=[]
    for f in companion['changed_native_files']:
        ours=source/f;theirs=store/'src'/store_prefix/f;ancestor=base/'src'/base_prefix/f
        if not ancestor.exists():
            if ours.exists():raise ValueError('Both parents add same new file: '+f)
            shutil.copy2(theirs,ours);resolutions.append({'path':f,'result':'exact-new-store-file','merged_sha256':sha(ours)});continue
        folder=merge_root/f.replace('/','_');folder.mkdir()
        for name,path in [('ours',ours),('base',ancestor),('theirs',theirs)]:shutil.copy2(path,folder/name)
        argv=['git','merge-file','--diff3','-p',str(folder/'ours'),str(folder/'base'),str(folder/'theirs')]
        result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        (folder/'stderr').write_bytes(result.stderr)
        if not 0<=result.returncode<128:raise ValueError('Threeway merge failed structurally: '+f)
        ours.write_bytes(result.stdout)
        resolutions.append({'path':f,'result':'clean-threeway'if result.returncode==0 else'manual-review-required',
            'ours_sha256':sha(folder/'ours'),'base_sha256':sha(ancestor),'theirs_sha256':sha(theirs),'merged_sha256':sha(ours)})
        if result.returncode:conflicts.append(f)
    (out/'merge-results.json').write_text(json.dumps(resolutions,indent=2)+'\n')
    if conflicts:
        (out/'unresolved.json').write_text(json.dumps({'conflicts':conflicts,'no_build_performed':True},indent=2)+'\n')
        raise ValueError('Explicit threeway review required: '+str(conflicts))
    delta=ROOT/'build/owned-store-companion-on-523-v1/owned-store-on-523.patch'
    # New files are part of the binary overlay; only this clone's index changes.
    run(['git','-C',str(source),'add','-N','.'])
    (out/'combined-overlay.patch').write_bytes(subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD']))
    # Ordinary copies/reflinks, never hardlinks, keep immutable parent objects
    # intact. Dependency paths and SDK symlinks refer to the new source only.
    shutil.copytree(oldbuild,build,symlinks=True,copy_function=shutil.copy2)
    changed=[]
    for p in build.rglob('*'):
        if p.is_symlink():
            target=os.readlink(p);new=target.replace(str(oldsource),str(source)).replace(str(oldbuild),str(build))
            if new!=target:p.unlink();p.symlink_to(new,target_is_directory=Path(new).is_dir())
        elif p.is_file()and(p.suffix in ('.d','.mk')or p.name in ('Makefile','config.status','config.log')):
            before=p.read_bytes();after=before.replace(str(oldsource).encode(),str(source).encode()).replace(str(oldbuild).encode(),str(build).encode())
            if before!=after:
                stat=p.stat();p.write_bytes(after);os.utime(p,ns=(stat.st_atime_ns,stat.st_mtime_ns));changed.append(str(p.relative_to(build)))
    objects={str(p.relative_to(oldbuild)):sha(p)for p in oldbuild.glob('*.o')}
    report={'schema':'iris.fadd_shape_native_composition.v1','pass':True,'source':str(source),'build':str(build),
        'base_commit':PIN,'parent_native_sha256':m['binary_sha256'],'parent_uart_sha256':m['uart_sha256'],
        'parent_reconstructed_native_sources':verified,'complete_parent_source_equality_before_changes':True,
        'store_exact_frozen_source_threeway_merge':resolutions,'source_frontend_policy_changed':False,
        'optional_storefront_included':True,'full_binary_rebuild_performed':False,
        'reused_parent_objects_sha256':objects,'rewritten_dependency_paths':changed,
        'commands':commands,'hardware_contacted':False,'global_heldout_timings_consumed':False,
        'input_sha256':{str(p):sha(p)for p in (Path(__file__).resolve(),parent/'manifest.json',parent/'source-overlay.patch',
            parent/'source-inventory.json',base/'manifest.json',store/'manifest.json',oldbuild/'pipeline-build.json',delta)},
        'combined_overlay_sha256':sha(out/'combined-overlay.patch')}
    (out/'composition.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'source':str(source),'build':str(build),'composition_sha256':sha(out/'composition.json')}))


if __name__=='__main__':main()
