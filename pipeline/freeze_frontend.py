#!/usr/bin/env python3
"""Freeze frontend source, read-only RTL proof and exact component artifacts."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1048576),b''):h.update(data)
    return h.hexdigest()

def decoded_digest(path,encoding):
    h=hashlib.sha256();opener=gzip.open if encoding=='gzip' else open
    with opener(path,'rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');p.add_argument('--report',action='append',default=[]);p.add_argument('--proof',type=Path,default=ROOT/'build/frontend-phase-proof-interface512-v4');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        m=json.loads((out/'manifest.json').read_text())
        for h,obj in m['objects'].items():
            path=out/obj['path']
            if digest(path)!=obj['encoded_sha256'] or decoded_digest(path,obj['encoding'])!=h:raise ValueError('closed frontend content changed: '+h)
        if any(item['sha256'] not in m['objects'] for item in m['files'].values()):raise ValueError('missing source object')
        print(json.dumps(dict(status='verified_closed_frontend_components',files=len(m['files']),objects=len(m['objects']))));return
    out.mkdir(exist_ok=False,parents=True);(out/'objects').mkdir();files={};objects={}
    def keep(path,logical=None,expected=None):
        path=Path(path).resolve();h=digest(path)
        if expected and h!=expected:raise ValueError('input changed before freeze: '+str(path))
        label=str(logical or path)
        if label in files and files[label]['sha256']!=h:raise ValueError('inconsistent source identity: '+label)
        files[label]=dict(sha256=h,bytes=path.stat().st_size)
        if h not in objects:
            compressed=path.stat().st_size>1048576
            target=out/'objects'/(h+('.gz' if compressed else ''))
            if compressed:
                with path.open('rb') as source,target.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,compresslevel=1) as dest:shutil.copyfileobj(source,dest,1048576)
            else:shutil.copy2(path,target)
            objects[h]=dict(path=str(target.relative_to(out)),encoding='gzip' if compressed else 'raw',encoded_sha256=digest(target))
        return h
    reports=['frontend-cache-component-v1','frontend-queue-component-v2','frontend-cache-pipeline-component-v1','frontend-parcel-component-v1','frontend-select-component-v1']+a.report
    identities={}
    for name in reports:
        folder=ROOT/'build'/name;report=folder/'results.json';r=json.loads(report.read_text());identities[name]=dict(report_sha256=digest(report),status=r['status'])
        for key in ('input_sha256','inputs_sha256','source_sha256'):
            for path,h in r.get(key,{}).items():
                path=Path(path);path=path if path.is_absolute() else ROOT/path
                keep(path,expected=h)
        # Retain compiled binaries, generated sources/objects, exact traces,
        # negative controls and stdout/stderr. No symbolic-link traversal.
        for path in sorted(folder.rglob('*')):
            if path.is_file() and not path.is_symlink():keep(path)
    proof=a.proof.resolve();r=json.loads((proof/'report.json').read_text())
    for path,h in r['input_sha256'].items():keep(proof/'inputs'/h,logical=path,expected=h)
    for path,h in r['artifact_sha256'].items():keep(proof/path,expected=h)
    proof_sha=keep(proof/'report.json')
    for path in ['pipeline/FRONTEND.md','pipeline/freeze_frontend.py','hardware/frontend_phase/build_interface.py']:
        keep(ROOT/path)
    source_evidence=[]
    for repo,relative,lines in [('shuttle','ifu/ICache.scala',[[49,76],[90,120],[155,175],[207,216]]),('shuttle','ifu/Frontend.scala',[[133,199],[259,326],[328,383]]),
                              ('shuttle','ifu/FetchBuffer.scala',[[16,39],[76,129]]),('shuttle','exu/Core.scala',[[690,748]]),('rocket-chip','rocket/RVC.scala',[[19,43],[77,111],[145,169],[183,186]]),('rocket-chip','rocket/BTB.scala',[[59,63]])]:
        path=ROOT/'third_party'/repo/'src/main/scala'/relative
        source_evidence.append(dict(repository=repo,path=str(path),sha256=keep(path),lines=lines))
    m=dict(schema='iris.frontend.components.closed.v1',status='closed_source_components_not_native_integration',files=files,objects=objects,reports=identities,whole_cpu_proof_sha256=proof_sha,
           source_pins=dict(chipyard='b4542facf6cc9457f6e358e8f80a8b3a0ff5df19',shuttle='a536ed1df91a0f65770e36758291d02a8cb929c4',rocket_chip='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0'),
           source_fir_sha256='f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4',source_evidence=source_evidence,
           native_integration=False,hardware_contacted=False,timing_parameters={},calibrated=False,full_functional_certified=False,full_timing_certified=False,held_out_2pct=False,ethan_image_association_verified=False,
           limitations=['Continuous reset-only reconstruction applies to cache/tag control, not the whole frontend.','Queue/selector tests supply each actual pre-state; predecode tests supply the saved RVC RTL oracle.','Predictor/translation/data-array and live native line-beat coupling remain separate work.','This capsule freezes recorded inputs and generated test artifacts; it does not claim all operating-system/compiler-runtime inputs constitute a hermetic compiler distribution.'])
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(dict(status=m['status'],files=len(files),objects=len(objects),manifest_sha256=digest(out/'manifest.json'))))
if __name__=='__main__':main()
