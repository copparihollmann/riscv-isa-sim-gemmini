#!/usr/bin/env python3
"""Close an isolated native epoch over exact source, guest and evidence bytes."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
REPORTS=['build/pipeline-rvc-directed-final/results.json','build/pipeline-rvc-memory/results.json',
         'build/pipeline-rvc-functional32/results.json','build/pipeline-rvc-uart/results.json',
         'build/pipeline-rvc-live8/results.json',
         'build/pipeline-rvc-zephyr-scalar/results.json','build/pipeline-rvc-zephyr-mixed/results.json',
         'build/pipeline-rvc-source-check/results.json']


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--snapshot',type=Path,default=ROOT/'build/pipeline-frozen-646538e0')
    parser.add_argument('--native-build',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next')
    parser.add_argument('--source',type=Path,default=ROOT/'pipeline/riscv-isa-sim-next')
    parser.add_argument('--parent-snapshot',type=Path,default=ROOT/'build/snapshot-5e6cc309')
    parser.add_argument('--reports',nargs='+',default=REPORTS)
    parser.add_argument('--extension',type=Path,default=ROOT/'build/pipeline-rvc-directed-final/pipeline-on-parent-epoch.patch')
    parser.add_argument('--extension-prerequisite',type=Path,help='Explicit prior closed epoch when the review delta is on a later isolated model')
    parser.add_argument('--profile-check',type=Path,default=ROOT/'build/pipeline-rvc-profile-check.json')
    parser.add_argument('--profile-dir',type=Path,default=ROOT/'build/pipeline-rvc-mixed-profile')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();out=args.snapshot.resolve();manifest_path=out/'manifest.json'
    if args.verify:
        manifest=json.loads(manifest_path.read_text())
        for name,digest in manifest['artifact_sha256'].items():
            if sha(out/name)!=digest:raise RuntimeError('snapshot artifact mismatch: '+name)
        for name,digest in manifest['input_sha256'].items():
            if sha(out/'inputs'/digest)!=digest:raise RuntimeError('snapshot input mismatch: '+name)
        for name,row in manifest['compressed_artifacts'].items():
            digest=hashlib.sha256()
            with gzip.open(out/row['stored_as'],'rb') as stream:
                for chunk in iter(lambda:stream.read(1048576),b''):digest.update(chunk)
            if digest.hexdigest()!=row['raw_sha256']:raise RuntimeError('compressed raw artifact mismatch: '+name)
        if not (out/'spike').stat().st_mode&0o100:raise RuntimeError('snapshot executable permission missing')
        print(json.dumps(dict(status='verified_closed_pipeline_epoch',inputs=len(manifest['input_sha256']),
                              artifacts=len(manifest['artifact_sha256']),calibrated=False)))
        return
    if manifest_path.exists():raise RuntimeError('closed snapshot already exists; verify it or choose a new output')
    out.mkdir(exist_ok=True,parents=True);(out/'inputs').mkdir(exist_ok=True)
    source=args.source.resolve();build=args.native_build.resolve();parent=args.parent_snapshot.resolve()
    identity=json.loads((parent/'manifest.json').read_text())
    for name,key in [('spike-iris-functional','binary_sha256'),('libsifive_uart.so','uart_sha256'),('iris.patch','overlay_sha256'),
                     ('provenance.json','provenance_sha256'),('source-and-evidence.tar.gz','archive_sha256')]:
        if sha(parent/name)!=identity[key]:raise RuntimeError('parent snapshot changed: '+name)
    native=json.loads((build/'pipeline-build.json').read_text())
    if sha(build/'spike')!=native['binary_sha256'] or sha(build/'libsifive_uart.so')!=native['uart_sha256']:
        raise RuntimeError('native/plugin differs from its build receipt')
    inputs={};compressed={}

    def store(name,path):
        target=out/name;target.parent.mkdir(exist_ok=True,parents=True)
        if path.stat().st_size>1048576 and path.suffix=='.json':
            encoded=Path(str(target)+'.gz')
            with path.open('rb') as src,gzip.open(encoded,'wb',compresslevel=1) as dst:shutil.copyfileobj(src,dst,1048576)
            compressed[name]=dict(stored_as=str(encoded.relative_to(out)),raw_sha256=sha(path))
        else:shutil.copy2(path,target)

    with tarfile.open(parent/'source-and-evidence.tar.gz') as archive:
        members={m.name:m for m in archive if m.isfile()}
        def retain(name,digest,extra=()):
            target=out/'inputs'/digest
            if target.exists() and sha(target)==digest:inputs[name]=digest;return
            path=Path(name);candidates=[path if path.is_absolute() else ROOT/path]+list(extra)
            for candidate in candidates:
                if candidate.is_file() and sha(candidate)==digest:
                    shutil.copy2(candidate,target);inputs[name]=digest;return
            relative=str(path.relative_to(ROOT)) if path.is_absolute() and path.is_relative_to(ROOT) else str(path)
            if relative in members:
                raw=archive.extractfile(members[relative]).read()
                if hashlib.sha256(raw).hexdigest()==digest:target.write_bytes(raw);inputs[name]=digest;return
            raise RuntimeError('historical input missing or changed: '+name)

        for report_name in args.reports:
            report=ROOT/report_name;data=json.loads(report.read_text())
            if not data['status'].startswith('passed'):raise RuntimeError('report failed: '+report_name)
            if 'binary_sha256' in data and data['binary_sha256']!=native['binary_sha256']:raise RuntimeError('different model in report: '+report_name)
            for field in ('source_sha256','input_sha256'):
                for name,digest in data.get(field,{}).items():retain(name,digest)
            if 'elf_sha256' in data and 'argv' in data:retain(data['argv'][-1],data['elf_sha256'])
            for path in report.parent.iterdir():
                if path.is_file():store('reports/'+report.parent.name+'/'+path.name,path)
            for case in data.get('results',data.get('cases',[])):
                if not case.get('pass',True):raise RuntimeError('failed nested case')
                for field,flag in [('elf_sha256',None),('binary_sha256',None)]:
                    if field in case and 'argv' in case:
                        path=case['argv'][-1 if field=='elf_sha256' else 0];retain(path,case[field])
            if 'mismatch_argv' in data:retain(data['mismatch_argv'][0],data['mismatch_binary_sha256'])
            if 'build_receipt_sha256' in data:
                zbuild=Path(data['argv'][-1]).parents[1];receipt=zbuild/'build.json'
                if sha(receipt)!=data['build_receipt_sha256']:raise RuntimeError('Zephyr build receipt changed')
                z=json.loads(receipt.read_text());store('reports/'+report.parent.name+'/build.json',receipt)
                for name,digest in z['input_sha256'].items():retain(name,digest,[zbuild/'input-snapshot'/name])
                for name,digest in z['artifact_sha256'].items():
                    if sha(zbuild/name)!=digest:raise RuntimeError('Zephyr artifact changed')
                    store('reports/'+report.parent.name+'/'+Path(name).name,zbuild/name)
            if 'source_evidence' in data:
                evidence=data['source_evidence']
                entries=evidence.items() if isinstance(evidence,dict) else ((row['path'],row) for row in evidence)
                for name,row in entries:
                    retain(name,row['sha256'],[report.parent/row['snapshot']])
        for dep in build.glob('*.d'):
            words=dep.read_text().replace('\\\n',' ').split()[1:]
            for word in words:
                if word.endswith(':'):continue
                path=(build/word).resolve()
                if path.is_file() and path.is_relative_to(ROOT):
                    if path.stat().st_mtime>dep.stat().st_mtime+1:raise RuntimeError('source changed after actual compilation: '+str(path))
                    retain(str(path),sha(path))
        for name,digest in native['input_sha256'].items():retain(name,digest)
        for path in (ROOT/'pipeline').glob('*'):
            if path.is_file() and path.suffix in ('.py','.cpp','.hpp','.fixture','.c','.S','.md'):retain(str(path),sha(path))
    full=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD'])
    if hashlib.sha256(full).hexdigest()!=native['source_overlay_sha256']:raise RuntimeError('native source overlay changed after build')
    (out/'iris-with-pipeline.patch').write_bytes(full)
    store('pipeline-on-parent-epoch.patch',args.extension.resolve())
    for name in ('spike','libsifive_uart.so','pipeline-build.json','config.log','config.h','libriscv.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a'):
        store(name,build/name)
    for name in ('iris.patch','provenance.json','manifest.json','source-and-evidence.tar.gz'):
        store('parent/'+name,parent/name)
    profile=args.profile_check.resolve()
    checked=json.loads(profile.read_text())
    if checked['exit_status']!=0:raise RuntimeError('strict mixed-region profiler failed')
    store('profiler/check.json',profile)
    for name in ('summary.json','timeline.json'):
        store('profiler/'+name,args.profile_dir.resolve()/name)
    artifacts={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and not p.is_relative_to(out/'inputs')}
    manifest=dict(schema='iris.shuttle.closed_epoch.v2',status='closed_experimental_pipeline_epoch',
                  base_git_sha='72958551566a30f19444bd7e354552824e4d0a98',source=str(source),parent_identity=identity,
                  binary_sha256=native['binary_sha256'],uart_sha256=native['uart_sha256'],
                  full_overlay_sha256=sha(out/'iris-with-pipeline.patch'),extension_patch_sha256=sha(out/'pipeline-on-parent-epoch.patch'),
                  input_sha256=inputs,artifact_sha256=artifacts,compressed_artifacts=compressed,reports=args.reports,
                  calibrated=False,rtl_certified=False,held_out_2pct=False,
                  scope='Source-backed RV64I/C pure-ALU multi-packet Shuttle domain; explicit sequential frontend fixture; finite clocked UART and inherited HPM/functional contracts. Not a complete pipeline/SoC model.')
    if args.extension_prerequisite:
        prerequisite=args.extension_prerequisite.resolve();record=json.loads((prerequisite/'manifest.json').read_text())
        manifest['extension_prerequisite']=dict(path=str(prerequisite),manifest_sha256=sha(prerequisite/'manifest.json'),
                                               binary_sha256=record['binary_sha256'],full_overlay_sha256=record['full_overlay_sha256'])
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status=manifest['status'],snapshot=str(out),inputs=len(inputs),artifacts=len(artifacts))))


if __name__=='__main__':main()
