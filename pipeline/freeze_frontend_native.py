#!/usr/bin/env python3
"""Close the optional live private-value epoch against its frozen ABI4 parent."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        m=json.loads((out/'manifest.json').read_text())
        for h,r in m['objects'].items():
            path=out/r['path']
            if sha(path)!=r['encoded_sha256']:raise ValueError('encoded source object changed')
            op=gzip.open if r['encoding']=='gzip' else open;d=hashlib.sha256()
            with op(path,'rb') as f:
                for b in iter(lambda:f.read(1048576),b''):d.update(b)
            if d.hexdigest()!=h:raise ValueError('decoded source object changed')
        for name,h in m['top_artifact_sha256'].items():
            if sha(out/name)!=h:raise ValueError('native closure artifact changed: '+name)
        print(json.dumps(dict(status='verified_closed_live_value_epoch',files=len(m['files']),objects=len(m['objects']))));return
    out.mkdir(exist_ok=False,parents=True);(out/'objects').mkdir();files={};objects={}
    parent=ROOT/'build/combined-frozen-35901887';pm=json.loads((parent/'manifest.json').read_text())
    if sha(parent/'manifest.json')!='ef1214f25a2db5a01b6dd9aa1180b002c0f4da74ec987ac0a5b90bff10ed7088':raise ValueError('frozen ABI4 parent changed')
    source=ROOT/'pipeline/riscv-isa-sim-frontend';build=ROOT/'build/spike-frontend-values-v2';br=json.loads((build/'pipeline-build.json').read_text())
    full=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD'])
    if hashlib.sha256(full).hexdigest()!=br['source_overlay_sha256'] or sha(build/'spike')!=br['binary_sha256'] or sha(build/'libsifive_uart.so')!=br['uart_sha256']:raise ValueError('native/source build changed')
    def keep(path,expected=None,label=None):
        path=Path(path);path=path if path.is_absolute() else ROOT/path;name=label or str(path);h=sha(path)
        if expected and h!=expected:raise ValueError('exact input changed: '+str(path))
        if name in files and files[name]['sha256']!=h:raise ValueError('inconsistent source epochs: '+name)
        files[name]=dict(sha256=h,bytes=path.stat().st_size)
        if h not in objects:
            zipped=path.stat().st_size>1048576;target=out/'objects'/(h+('.gz' if zipped else ''))
            if zipped:
                with path.open('rb') as src,target.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as dst:shutil.copyfileobj(src,dst,1048576)
            else:shutil.copy2(path,target)
            objects[h]=dict(path=str(target.relative_to(out)),encoding='gzip' if zipped else 'raw',encoded_sha256=sha(target))
        return h
    def retain(path,digest):
        path=Path(path);candidate=path if path.is_absolute() else ROOT/path
        if candidate.is_file() and sha(candidate)==digest:return keep(candidate,digest)
        relative=str(candidate.relative_to(ROOT)) if candidate.is_relative_to(ROOT) else str(path)
        row=pm['files'].get(relative)
        if row and row['sha256']==digest:
            encoded=parent/row['object']
            if sha(encoded)!=row['object_sha256']:raise ValueError('parent object changed')
            op=gzip.open if row['compression']=='gzip' else open
            target=out/'parent-input.tmp'
            with op(encoded,'rb') as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,1048576)
            h=keep(target,digest,str(candidate));target.unlink();return h
        raise ValueError('historical dependency unavailable: '+str(path))
    reports=['frontend-values-native-directed-v2','frontend-values-native-oracle-v2','frontend-values-native-memory-v2','frontend-values-native-initialized-live8-v2','frontend-values-native-uart-v2',
             'frontend-values-native-combined32-v2','frontend-values-native-zephyr-scalar-v2','frontend-values-native-zephyr-mixed-v2']
    receipts={}
    def retain_inputs(data):
        for field in ('input_sha256','source_sha256'):
            for path,digest in data.get(field,{}).items():retain(path,digest)
    for name in reports:
        folder=ROOT/'build'/name;rp=folder/'results.json';r=json.loads(rp.read_text())
        if not r['status'].startswith('passed') or r.get('binary_sha256')!=br['binary_sha256'] or r.get('uart_sha256')!=br['uart_sha256']:raise ValueError('gate not bound to candidate: '+name)
        receipts[name]=dict(sha256=sha(rp),status=r['status']);retain_inputs(r)
        for row in r.get('rows',r.get('results',r.get('cases',[]))):
            if row.get('pass',True) is not True:raise ValueError('failed nested guest')
            if 'argv' in row and 'elf_sha256' in row:retain(row['argv'][-1],row['elf_sha256'])
        if 'build_receipt_sha256' in r:
            zb=Path(r['argv'][-1]).parents[1];z=json.loads((zb/'build.json').read_text());keep(zb/'build.json',r['build_receipt_sha256'])
            for path,digest in z['input_sha256'].items():retain(path,digest)
            for path,digest in z['artifact_sha256'].items():keep(zb/path,digest)
        for path in folder.iterdir():
            if path.is_file() and not path.is_symlink():keep(path)
    unit=ROOT/'build/frontend-values-component-v2';u=json.loads((unit/'results.json').read_text());retain_inputs(u)
    for path in unit.rglob('*'):
        if path.is_file() and not path.is_symlink():keep(path)
    for dep in build.glob('*.d'):
        keep(dep)
        for word in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            path=(build/word).resolve()
            if path.is_file() and path.is_relative_to(ROOT):keep(path)
    retain_inputs(br)
    for path in [parent/'manifest.json',parent/'source-overlay.patch',ROOT/'pipeline/FRONTEND_VALUES.md',ROOT/'pipeline/frontend-values.fixture',Path(__file__).resolve(),ROOT/'pipeline/build_native_frontend.py',ROOT/'pipeline/uart-plugin-abi4.cc',ROOT/'pipeline/FRONTEND.md',ROOT/'pipeline/frontend_values.hpp',ROOT/'build/frontend-components-frozen-v3/manifest.json']:
        keep(path)
    for name in ['frontend-values-inherited-negative-controls-v3','frontend-values-native-functional32-v2','frontend-values-native-live8-v2']:
        for path in (ROOT/'build'/name).iterdir():
            if path.is_file():keep(path)
    for path in (build/'failed-abi1-plugin',ROOT/'build/spike-frontend-values-v1/failed-abi1-plugin'):
        if path.exists():
            for f in path.iterdir():
                if f.is_file():keep(f)
    profile=ROOT/'build/frontend-values-native-mixed-profile-v2';summary=json.loads((profile/'summary.json').read_text())
    if len(summary['observed_regions'])!=9:raise ValueError('strict captured-CSR profile did not join9ROIs')
    for path in profile.iterdir():
        if path.is_file():keep(path)
    for path in (ROOT/'iris_model').glob('*.py'):keep(path)
    for name in ['spike','libsifive_uart.so','pipeline-build.json','config.h','config.log','libriscv.a','libdisasm.a','libfesvr.a','libsoftfloat.a','libfdt.a']:
        keep(build/name)
    (out/'source-overlay.patch').write_bytes(full)
    for name in ['spike','libsifive_uart.so']:shutil.copy2(build/name,out/name)
    extension=ROOT/'build/frontend-values-native-directed-v2/pipeline-on-parent-epoch.patch';shutil.copy2(extension,out/'values-on-combined359.patch')
    manifest=dict(schema='iris.frontend.live_values.closed.v1',status='closed_experimental_live_value_foundation',base_git_sha=br['base_commit'],source=str(source),binary_sha256=br['binary_sha256'],uart_sha256=br['uart_sha256'],full_overlay_sha256=br['source_overlay_sha256'],extension_patch_sha256=sha(extension),
                  parent_manifest_sha256=sha(parent/'manifest.json'),parent_overlay_sha256=pm['source_overlay_sha256'],native_device_abi=4,files=files,objects=objects,reports=receipts,strict_profile_regions=9,
                  private_forwarded_values_optional=True,source_frontend_integrated=False,architectural_effects_at_commit=True,full_knownness_certified=False,rtl_certified=False,calibrated=False,held_out_2pct=False,deployed_image_association_verified=False,
                  limitations=['Pure ALU/zero-operand counter result values only; no live branch speculation/cache coupling.','Partial-bit knownness stays with inherited functional model.','Long unrolled blocks retain value history and current COM-order scan needs optimization.','Preserved historical5e6 failures are baseline-matched unknown-state controls, not qualified positive results.'])
    manifest['top_artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(status=manifest['status'],files=len(files),objects=len(objects),manifest_sha256=sha(out/'manifest.json'))))
if __name__=='__main__':main()
