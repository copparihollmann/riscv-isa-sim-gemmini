#!/usr/bin/env python3
"""Close the isolated live Rocket/cache epoch and its independent evidence."""
import argparse
import difflib
import gzip
import hashlib
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        m=json.loads((out/'manifest.json').read_text())
        for digest,row in m['objects'].items():
            path=out/row['path']
            if sha(path)!=row['encoded_sha256']:raise ValueError('encoded closure object changed')
            h=hashlib.sha256();op=gzip.open if row['encoding']=='gzip'else open
            with op(path,'rb')as f:
                for b in iter(lambda:f.read(1048576),b''):h.update(b)
            if h.hexdigest()!=digest:raise ValueError('decoded closure object changed')
        for name,digest in m['top_artifact_sha256'].items():
            if sha(out/name)!=digest:raise ValueError('top artifact changed: '+name)
        if any(row['sha256']not in m['objects']for row in m['files'].values()):raise ValueError('missing content-addressed object')
        print(json.dumps(dict(status='verified_closed_live_Rocket_fabric_epoch',files=len(m['files']),objects=len(m['objects']))));return
    out.mkdir(exist_ok=False,parents=True);(out/'objects').mkdir();files={};objects={};receipts={}
    source=ROOT/'pipeline/riscv-isa-sim-rocket-fabric';build=ROOT/'build/spike-rocket-fabric-v1';parent=ROOT/'build/rocket-source-frozen-2539e85c';oldtree=ROOT/'pipeline/riscv-isa-sim-rocket-source';br=json.loads((build/'pipeline-build.json').read_text())
    if sha(parent/'manifest.json')!='ec79c830575a7909842834d445ec2b85779ea370ece3ae50933edc0242fd73d5':raise ValueError('frozen2539 identity changed')
    overlay=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD'])
    if hashlib.sha256(overlay).hexdigest()!=br['source_overlay_sha256']or sha(build/'spike')!=br['binary_sha256']or sha(build/'libsifive_uart.so')!=br['uart_sha256']:raise ValueError('native/source build identity changed')
    def keep(path,expected=None,label=None):
        path=Path(path);path=path if path.is_absolute()else ROOT/path;digest=sha(path)
        if expected and digest!=expected:raise ValueError('exact input changed: '+str(path))
        name=label or str(path)
        if name in files and files[name]['sha256']!=digest:raise ValueError('mixed source epoch: '+name)
        files[name]=dict(sha256=digest,bytes=path.stat().st_size)
        if digest not in objects:
            zipped=path.stat().st_size>1048576;target=out/'objects'/(digest+('.gz'if zipped else''))
            if zipped:
                with path.open('rb')as src,target.open('wb')as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0)as dst:shutil.copyfileobj(src,dst,1048576)
            else:shutil.copy2(path,target)
            objects[digest]=dict(path=str(target.relative_to(out)),encoding='gzip'if zipped else'raw',encoded_sha256=sha(target))
        return digest
    def tree(folder):
        for path in Path(folder).rglob('*'):
            if path.is_file():keep(path)
    def inputs(data,folder):
        for path,digest in data.get('input_sha256',{}).items():
            path=Path(path)
            if path.exists()and sha(path)==digest:keep(path,digest);continue
            archived=Path(folder)/'inputs'/digest
            if archived.exists()and sha(archived)==digest:keep(archived,digest,str(path)+'@'+digest);continue
            raise ValueError('source input unavailable: '+str(path))
    for name in ['rocket-fabric-load-gate-v7','rocket-fabric-directed-v6','rocket-fabric-functional32-v2','rocket-fabric-parent-replay-v1','rocket-fabric-support-v1','rocket-frontend-fabric-component-v6','rocket-dcache-arbiter-component-v3','rocket-fabric-whole-CPU-reference-v2','rocket-fabric-directed-whole-CPU-final']:
        folder=ROOT/'build'/name;rp=folder/'results.json';r=json.loads(rp.read_text())
        if not r['status'].startswith('passed'):raise ValueError('failed required gate: '+name)
        if r.get('binary_sha256')and name.startswith(('rocket-fabric-load-','rocket-fabric-directed-v','rocket-fabric-functional','rocket-fabric-parent'))and r['binary_sha256']!=br['binary_sha256']:raise ValueError('gate belongs to another native: '+name)
        receipts[name]=dict(status=r['status'],sha256=sha(rp));inputs(r,folder);tree(folder)
        for row in r.get('rows',[]):
            if row.get('pass_',True)is not True:raise ValueError('failed nested gate')
            if row.get('argv')and row.get('elf_sha256'):keep(row['argv'][-1],row['elf_sha256'])
    # The oracle used an earlier output directory containing identical ELF
    # bytes. Require that causal input identity rather than relabel its argv.
    live=json.loads((ROOT/'build/rocket-fabric-load-gate-v7/results.json').read_text());oracle=json.loads((ROOT/'build/rocket-fabric-whole-CPU-reference-v2/results.json').read_text())
    if oracle['elf_sha256']!=live['input_sha256'][live['argv'][-1]]:raise ValueError('whole-CPU live ELF differs')
    directed=json.loads((ROOT/'build/rocket-fabric-directed-v6/results.json').read_text());reference=json.loads((ROOT/'build/rocket-fabric-directed-whole-CPU-final/results.json').read_text())
    actual={r['name']:r['elf_sha256']for r in directed['rows']if not r['expected_diagnostic']}
    if {r['name']:r['elf_sha256']for r in reference['rows']}!=actual:raise ValueError('whole-CPU directed ELF identity differs')
    # Frozen external component capsules supply source/tool/generated-model
    # closure; these are copied as evidence, never mutated or republished.
    tree(parent);tree(ROOT/'build/memory-fabric-component-v1');tree(ROOT/'build/memory-fabric-component-v1-verify')
    for path in build.glob('*.d'):
        keep(path)
        for word in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1]):
            dep=(build/word).resolve()
            if dep.is_file():keep(dep)
    inputs(br,build)
    for path in (ROOT/'pipeline').glob('*'):
        if path.is_file()and(path.name.startswith(('rocket_fabric_','fabric_'))or path.name in ['frontend_values_fabric.hpp','test_frontend_values_fabric.cpp','test_fabric_engine.cpp','test_rocket_fabric_peer.cpp','freeze_rocket_fabric.py','ROCKET_FABRIC.md']):keep(path)
    for path in (ROOT/'hardware/rocket_memory_phase').glob('*.py'):keep(path)
    tree(ROOT/'build/rocket-memory-phase-proof-v2');tree(ROOT/'build/rocket-memory-phase-observer-v1');tree(ROOT/'build/rocket-memory-phase-reference-v1')
    # Counter/profile consumers are separate root-owned code, frozen by byte
    # identity so later edits do not reinterpret this historical graph.
    tree(ROOT/'build/rocket-fabric-load-profile-v2')
    for name in ['report.py','event_lifecycle.py','counter_regions.py','memory_profile.py']:keep(ROOT/'iris_model'/name)
    for name in ['spike','libsifive_uart.so','pipeline-build.json','config.h','config.log','Makefile','libriscv.a','libdisasm.a','libfesvr.a','libsoftfloat.a','libfdt.a']:keep(build/name)
    changed=sorted(set(subprocess.check_output(['git','-C',str(source),'diff','--name-only','HEAD'],text=True).splitlines())|set(subprocess.check_output(['git','-C',str(oldtree),'diff','--name-only','HEAD'],text=True).splitlines()))
    delta=[];native_files=[]
    for name in changed:
        before=oldtree/name;after=source/name;old=before.read_text()if before.exists()else'';new=after.read_text()if after.exists()else''
        if old==new:continue
        native_files.append(name);delta.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name if before.exists()else'/dev/null',tofile='b/'+name if after.exists()else'/dev/null'));keep(after)
    (out/'source-overlay.patch').write_bytes(overlay);(out/'delta-on-2539.patch').write_text(''.join(delta))
    with tempfile.TemporaryDirectory(prefix='iris-fabric-apply-')as temp:
        raw=subprocess.check_output(['git','-C',str(source),'archive','72958551566a30f19444bd7e354552824e4d0a98'])
        with tarfile.open(fileobj=io.BytesIO(raw))as tar:tar.extractall(temp,filter='data')
        for patch in [parent/'source-overlay.patch',out/'delta-on-2539.patch']:subprocess.run(['git','apply',str(patch)],cwd=temp,check=True,capture_output=True)
        if any(sha(Path(temp)/name)!=sha(source/name)for name in native_files):raise ValueError('minimal delta replay differs')
    for name in ['spike','libsifive_uart.so','pipeline-build.json']:shutil.copy2(build/name,out/name)
    top={name:sha(out/name)for name in ['source-overlay.patch','delta-on-2539.patch','spike','libsifive_uart.so','pipeline-build.json']}
    manifest=dict(schema='iris.rocket.live_fabric_capsule.v1',status='frozen_experimental_Rocket_scalar_cache_epoch',parent_manifest_sha256=sha(parent/'manifest.json'),binary_sha256=br['binary_sha256'],uart_sha256=br['uart_sha256'],source_overlay_sha256=br['source_overlay_sha256'],minimal_native_files=native_files,minimal_delta_applied_and_reconstructed=True,top_artifact_sha256=top,receipts=receipts,files=files,objects=objects,native_device_abi=4,full_internal_knownness_certified=False,all_three_hart_source_memory_coherence=False,new_path_IRQ_or_Zephyr_qualified=False,external_service='explicit synthetic post-cork/CBUS fixture; no Iris timing default',calibrated=False,RTL_certified=False,held_out_2pct=False,full_model_certified=False,loaded_image_association_verified=False,hardware_contacted=False)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(status=manifest['status'],binary_sha256=br['binary_sha256'],manifest_sha256=sha(out/'manifest.json'),files=len(files),objects=len(objects),minimal_native_files=len(native_files))))
if __name__=='__main__':main()
