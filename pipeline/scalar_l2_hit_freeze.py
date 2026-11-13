#!/usr/bin/env python3
"""Small successor capsule: exact parent inventory plus reconstructable delta."""
import argparse,difflib,hashlib,json,shutil,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'build/empirical-read-overlap-response-frozen-7bd58b4f'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(build,out):
    r=json.loads((build/'pipeline-build.json').read_text());source=Path(r['source'])
    for name,key in [('spike','binary_sha256'),('libsifive_uart.so','uart_sha256')]:
        if sha(build/name)!=r[key]:raise ValueError('Build pair changed')
    old=json.loads((PARENT/'manifest.json').read_text());inv=json.loads((PARENT/'source-inventory.json').read_text());prefix=old['native_source_relative']+'/'
    native={name[len(prefix):]:digest for name,digest in inv.items()if name.startswith(prefix)}
    current={name:sha(source/name)for name in native};changed=[name for name in native if current[name]!=native[name]]
    if set(changed)!={'riscv/iris_timing_adapter.h','riscv/iris_timing_adapter.cc','riscv/iris_memory_adapter.cc','riscv/iris_empirical_load.inc','riscv/iris_empirical_features.inc'}:raise ValueError('Unexpected native scope '+repr(changed))
    out.mkdir(parents=True,exist_ok=False);patch=''
    for name in sorted(changed):
        a=(PARENT/'src'/prefix/name).read_text().splitlines(True);b=(source/name).read_text().splitlines(True)
        patch+='diff --git a/'+name+' b/'+name+'\n'+''.join(difflib.unified_diff(a,b,fromfile='a/'+name,tofile='b/'+name))
    (out/'delta-on-7bd5.patch').write_text(patch)
    (out/'native-inventory.json').write_text(json.dumps(current,indent=2,sort_keys=True)+'\n')
    # Parent dependency references stay byte-bound; copy only changed/new small
    # integration sources, not gigabytes of already-frozen RTL oracle objects.
    external={};copied={}
    for dep in build.glob('*.d'):
        line=dep.read_text().replace('\\\n',' ').split('\n')[0]
        if ':'not in line:continue
        for token in line.split(':',1)[1].split():
            p=Path(token);p=p if p.is_absolute()else build/p;p=p.resolve()
            if p.is_file()and p.is_relative_to(ROOT)and not p.is_relative_to(source)and not p.is_relative_to(build):external[str(p)]=sha(p)
    for p in [Path(__file__).resolve(),ROOT/'pipeline/scalar_l2_hit_service.hpp',ROOT/'pipeline/test_scalar_l2_hit_service.cpp',ROOT/'timing/empirical_cache_v9.hpp',ROOT/'timing/empirical_cache_v9.cpp']:
        external[str(p)]=sha(p)
    for name,h in external.items():
        p=Path(name);rel=str(p.relative_to(ROOT))
        if inv.get(rel)==h:continue
        target=out/'src'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);copied[rel]=h
    for name in('spike','libsifive_uart.so','pipeline-build.json'):shutil.copy2(build/name,out/name)
    # Independent clean reconstruction of all2025 native files.
    with tempfile.TemporaryDirectory(prefix='scalar-L2hit-reconstruct-')as tmp:
        d=Path(tmp)
        with(d/'base.tar').open('wb')as f:subprocess.run(['git','-C',str(source),'archive',r['base_commit']],stdout=f,check=True)
        with tarfile.open(d/'base.tar')as t:t.extractall(d/'native',filter='data')
        subprocess.run(['git','apply','--unsafe-paths',str(PARENT/'source-overlay.patch')],cwd=d/'native',check=True)
        subprocess.run(['git','apply',str(out/'delta-on-7bd5.patch')],cwd=d/'native',check=True)
        for name,h in current.items():
            if sha(d/'native'/name)!=h:raise ValueError('Reconstruction differs '+name)
    m={'schema':'iris.scalar_L2_hit_compact_native_capsule.v1','pass':True,'source_frozen':True,
        'parent_manifest':str(PARENT/'manifest.json'),'parent_manifest_sha256':sha(PARENT/'manifest.json'),
        'parent_inventory_sha256':sha(PARENT/'source-inventory.json'),'base_commit':r['base_commit'],
        'binary_sha256':r['binary_sha256'],'uart_sha256':r['uart_sha256'],'native_sources_reconstructed':len(current),
        'native_changed_files':sorted(changed),'external_input_sha256':external,'new_copied_source_sha256':copied,
        'artifact_sha256':{name:sha(out/name)for name in('spike','libsifive_uart.so','pipeline-build.json','delta-on-7bd5.patch','native-inventory.json')},
        'source_cuts_evaluated':False,'timing_accuracy_certified':False,'full_binary_rebuild_performed':True,
        'scalar_L2_cost_default':'off','source_random_selector_default':'off',
        'random_scope':'0710 exact V9 Shuttle0/1 allocation-event proxy; no L2 or Rocket policy change'}
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps({'pass':True,'native':m['binary_sha256'],'uart':m['uart_sha256'],'manifest_sha256':sha(out/'manifest.json'),'changed':changed,'external_copied':len(copied)}))
if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.build.resolve(),a.output.resolve())
