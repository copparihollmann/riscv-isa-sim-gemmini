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
    source=ROOT/'pipeline/riscv-isa-sim-fadd-shape-v1'
    build=ROOT/'build/spike-fadd-shape-v1'
    out=ROOT/'build/fadd-shape-composition-v1'
    parent=ROOT/'build/scalar-fadd-phase-qualified-9b4932fe-v1'
    oldsource=ROOT/'pipeline/riscv-isa-sim-scalar-fadd'
    oldbuild=ROOT/'build/spike-scalar-fadd-v1'
    base=ROOT/'build/empirical-rocket-RAS-frozen-52314001'
    shape=ROOT/'build/empirical-vme-work-frozen-525cc4af'
    for p in (source,build,out):
        if p.exists():raise ValueError('Fresh composition paths required: '+str(p))
    if sha(parent/'manifest.json')!='e17b9308b1391bdfa0fb30a5e9af9cea75e06f5748422962588ed62a09270877':
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
    tiny=[]
    for f in ('riscv/iris_timing_adapter.h','riscv/iris_timing_adapter.cc','riscv/iris_empirical_features.inc'):
        a=base/'src'/json.loads((base/'manifest.json').read_text())['native_source_relative']/f
        b=shape/'src'/json.loads((shape/'manifest.json').read_text())['native_source_relative']/f
        tiny.extend(difflib.unified_diff(a.read_text().splitlines(True),b.read_text().splitlines(True),fromfile='a/'+f,tofile='b/'+f))
    delta=out/'shape-on-523.patch';delta.write_text(''.join(tiny))
    run(['git','-C',str(source),'apply','--check',str(delta)])
    run(['git','-C',str(source),'apply',str(delta)])
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
        'tiny_shape_exact_three_file_patch_applied':True,'source_frontend_policy_changed':False,
        'optional_storefront_included':False,'full_binary_rebuild_performed':False,
        'reused_parent_objects_sha256':objects,'rewritten_dependency_paths':changed,
        'commands':commands,'hardware_contacted':False,'global_heldout_timings_consumed':False,
        'input_sha256':{str(p):sha(p)for p in (Path(__file__).resolve(),parent/'manifest.json',parent/'source-overlay.patch',
            parent/'source-inventory.json',base/'manifest.json',shape/'manifest.json',oldbuild/'pipeline-build.json',delta)},
        'combined_overlay_sha256':sha(out/'combined-overlay.patch')}
    (out/'composition.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'source':str(source),'build':str(build),'composition_sha256':sha(out/'composition.json')}))


if __name__=='__main__':main()
