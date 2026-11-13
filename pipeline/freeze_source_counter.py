#!/usr/bin/env python3
"""Freeze the isolated source-counter successor and its exact code/evidence closure."""
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
    parent=ROOT/'build/frontend-live-frozen-778db044';pm=json.loads((parent/'manifest.json').read_text())
    if sha(parent/'manifest.json')!='73f9d9eaa6a39e8ab43b3f02879283a2523eb8b453dbfda290a7cf826bab31f9':raise ValueError('frozen ABI4 parent changed')
    source=ROOT/'pipeline/riscv-isa-sim-source-frontends';build=ROOT/'build/spike-source-frontends-v1';br=json.loads((build/'pipeline-build.json').read_text())
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
        hold=ROOT/'build/frontend-live-778-publication-input-hold/manifest.json'
        held=json.loads(hold.read_text())['files'].get(str(candidate))
        if held and held['sha256']==digest:return keep(Path(held['archive']),digest,str(candidate))
        relative=str(candidate.relative_to(ROOT)) if candidate.is_relative_to(ROOT) else str(path)
        row=pm['files'].get(relative) or pm['files'].get(str(candidate))
        if row and row['sha256']==digest:
            obj=pm['objects'][digest];encoded=parent/obj['path']
            if sha(encoded)!=obj['encoded_sha256']:raise ValueError('parent object changed')
            op=gzip.open if obj['encoding']=='gzip' else open
            target=out/'parent-input.tmp'
            with op(encoded,'rb') as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,1048576)
            h=keep(target,digest,str(candidate));target.unlink();return h
        raise ValueError('historical dependency unavailable: '+str(path))
    reports=['source-counter-native-gates-v3','source-counter-legacy-v2','source-counter-functional32-v2','source-counter-context-v1','source-counter-irq-v2','source-counter-zephyr-scalar-v1','source-counter-zephyr-mixed-v1']
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
        for path in folder.rglob('*'):
            if path.is_file() and not path.is_symlink():keep(path)
    unit=ROOT/'build/frontend-values-live-component-v3';u=json.loads((unit/'results.json').read_text());retain_inputs(u)
    for path in unit.rglob('*'):
        if path.is_file() and not path.is_symlink():keep(path)
    for dep in build.glob('*.d'):
        keep(dep)
        for word in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]):
            path=(build/word).resolve()
            if path.is_file():keep(path)
    retain_inputs(br)
    for path in [parent/'manifest.json',parent/'source-overlay.patch',ROOT/'pipeline/SOURCE_COUNTERS.md',ROOT/'pipeline/frontend-values.fixture',Path(__file__).resolve(),ROOT/'pipeline/build_native_source_frontends.py',ROOT/'pipeline/uart-plugin-abi4.cc',ROOT/'pipeline/FRONTEND.md',ROOT/'pipeline/frontend_values_live.hpp',ROOT/'build/frontend-components-frozen-v3/manifest.json']:
        keep(path)
    for name in ['frontend-engine-proof-v1','frontend-rtl-peer-component-v2','frontend-wfi-clock-proof-v1','source-counter-clock-component-v1']:
        for path in (ROOT/'build'/name).rglob('*'):
            if path.is_file():keep(path)
        r=json.loads((ROOT/'build'/name/'results.json').read_text());retain_inputs(r)
    for path in (build/'failed-abi1-plugin',ROOT/'build/spike-frontend-values-v1/failed-abi1-plugin'):
        if path.exists():
            for f in path.iterdir():
                if f.is_file():keep(f)
    profile=ROOT/'build/source-counter-mixed-profile-v2';summary=json.loads((profile/'summary.json').read_text())
    if len(summary['observed_regions'])!=9:raise ValueError('strict captured-CSR profile did not join9ROIs')
    for path in profile.iterdir():
        if path.is_file():keep(path)
    for path in (ROOT/'iris_model').glob('*.py'):keep(path)
    for name in ['source-counter-mixed-profile-v2.stdout','source-counter-mixed-profile-v2.stderr','source-counter-profiler-tests-v2.stdout','source-counter-profiler-tests-v2.stderr']:
        keep(ROOT/'build'/name)
    for path in (ROOT/'build/source-counter-irq-v1').iterdir():
        if path.is_file():keep(path)
    for path in (ROOT/'tests').glob('test*region*.py'):keep(path)
    for name in ['spike','libsifive_uart.so','pipeline-build.json','config.h','config.log','libriscv.a','libdisasm.a','libfesvr.a','libsoftfloat.a','libfdt.a']:
        keep(build/name)
    (out/'source-overlay.patch').write_bytes(full)
    for name in ['spike','libsifive_uart.so']:shutil.copy2(build/name,out/name)
    extension=out/'source-counters-on-frontend778.patch'
    names=subprocess.check_output(['git','-C',str(source),'diff','--name-only','HEAD'],text=True).splitlines()
    import difflib
    patch=''.join(''.join(difflib.unified_diff((ROOT/'pipeline/riscv-isa-sim-frontend-live'/name).read_text().splitlines(True) if (ROOT/'pipeline/riscv-isa-sim-frontend-live'/name).is_file() else [],(source/name).read_text().splitlines(True),fromfile='a/'+name if (ROOT/'pipeline/riscv-isa-sim-frontend-live'/name).is_file() else '/dev/null',tofile='b/'+name))for name in names if (source/name).is_file() and ((ROOT/'pipeline/riscv-isa-sim-frontend-live'/name).read_bytes() if (ROOT/'pipeline/riscv-isa-sim-frontend-live'/name).is_file() else b'')!=(source/name).read_bytes())
    extension.write_text(patch)
    manifest=dict(schema='iris.frontend.source_counter.closed.v1',status='closed_experimental_source_counter_frontend',base_git_sha=br['base_commit'],source=str(source),binary_sha256=br['binary_sha256'],uart_sha256=br['uart_sha256'],full_overlay_sha256=br['source_overlay_sha256'],extension_patch_sha256=sha(extension),
                  parent_manifest_sha256=sha(parent/'manifest.json'),parent_overlay_sha256=pm['full_overlay_sha256'],native_device_abi=4,files=files,objects=objects,reports=receipts,strict_profile_regions=9,
                  private_forwarded_values_optional=True,source_frontend_integrated=True,source_frontend_scope='saved-Iris-M-mode-Shuttle0/1',external_instruction_service='unknown-refused-or-explicit-synthetic',legacy_domain_label_requires_update=False,source_counter_policy='CSRFile-ungated-pre-edge-stall',source_counter_RTL_transactions=44,numeric_count_wfi='legacy-synthetic-only',architectural_effects_at_commit=True,bounded_live_records=True,constant_time_commit_order_guard=True,full_knownness_certified=False,rtl_certified=False,calibrated=False,held_out_2pct=False,deployed_image_association_verified=False,
                  limitations=['External memory/NoC/cache-coherence timing unknown; supplied tests use explicit synthetic service.','Rocket retains sequential frontend; FP/RVV/VME/data-memory paths retain conservative boundaries.','Frontend refill data must be fully known; unreset implementation-state seed is an explicit policy.','Interrupt lines use native pre-device-update phase; actual source interrupt crossing timing remains unqualified.','CEASE sticky state is component-tested; native hart2 CEASE retains the existing explicit unsupported-core-instruction refusal.','Saved Iris source is not an attestation of Ethan FireSim image.'])
    manifest['top_artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(status=manifest['status'],files=len(files),objects=len(objects),manifest_sha256=sha(out/'manifest.json'))))
if __name__=='__main__':main()
