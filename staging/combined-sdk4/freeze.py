#!/usr/bin/env python3
"""Freeze a source-built SDK4 review package and evidence. No publication."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def signature(value):return(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
def module(path):
    spec=importlib.util.spec_from_file_location('sdk4_review_provider',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--acceptance',type=Path,required=True)
    p.add_argument('--deployment',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
    package=a.package.resolve();accept=a.acceptance.resolve();deployment=a.deployment.resolve();out=a.output.resolve()
    if a.verify:
        r=json.loads((out/'report.json').read_text())
        for name,value in r['input_sha256'].items():
            if sha(Path(name))!=value:raise ValueError('Review input changed: '+name)
        for name,value in r['artifact_sha256'].items():
            if sha(out/name)!=value:raise ValueError('Review artifact changed: '+name)
        if not module(package/'provider.py').experimental_functional_simulator()['available']:raise ValueError('Provider refused frozen review')
        print(json.dumps({'status':'verified','report_sha256':sha(out/'report.json'),'primary_published':False}));return
    provider=module(package/'provider.py');verified=provider.experimental_functional_simulator()
    if verified.get('available')is not True:raise ValueError(verified.get('reason'))
    acceptance=json.loads(accept.read_text());deploy=json.loads(deployment.read_text())
    if acceptance['pass']is not True or acceptance['package_provenance_sha256']!=sha(package/'provenance.json')or acceptance['launcher_sha256']!=sha(package/'launch.py'):raise ValueError('Acceptance does not bind package')
    for name,value in acceptance['input_sha256'].items():
        if sha(Path(name))!=value:raise ValueError('Acceptance source changed: '+name)
    for name,value in deploy['input_sha256'].items():
        if sha(Path(name))!=value:raise ValueError('Deployment input changed: '+name)
    out.mkdir(parents=True,exist_ok=False);inputs={str(package/'provenance.json'):sha(package/'provenance.json')}
    inputs[str(package/'merlin-manifest.json')]=sha(package/'merlin-manifest.json')
    provenance=verified['provenance']
    for name,value in provenance['input_sha256'].items():inputs[str(package/name)]=value
    for directory in [accept.parent,deployment.parent,HERE]:
        for path in directory.rglob('*'):
            if path.is_file()and'__pycache__'not in path.parts:inputs[str(path.resolve())]=sha(path)
    primary={'spike/bin/spike-iris-functional':'5e6cc309b8cd1085e30ee0c31b43c2bc27ef9c325136a94bfdd4d86700787f7e',
        'spike/bin/libsifive_uart.so':'28e8162a04b8492df4f8282ed86f01bd7a25974bbd435892211fc479f9060bb9',
        'build/combined-frozen-35901887/spike':provider.BINARY,'build/combined-candidate-35901887/spike':provider.BINARY}
    for name,value in primary.items():
        if sha(ROOT/name)!=value:raise ValueError('Preserved artifact changed: '+name)
        inputs[str(ROOT/name)]=value
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);tools={}
    for name in ['gcc','g++','make','as','ld','ar','nm','dtc','python3']:
        executable=Path(shutil.which(name,path=env['PATH'])).resolve()
        result=subprocess.run([str(executable),'--version'],capture_output=True,env=env)
        tools[name]={'executable':str(executable),'sha256':sha(executable),'version_exit_status':result.returncode,
            'version_stdout':result.stdout.decode(errors='replace'),'version_stderr':result.stderr.decode(errors='replace')}
        inputs[str(executable)]=sha(executable)
    (out/'host-tools.json').write_text(json.dumps(tools,indent=2)+'\n')
    shutil.copyfile(accept,out/'acceptance.json');shutil.copyfile(deployment,out/'merlin-deployment.json')
    archive=out/'iris-sdk4-experimental.tar.gz';partial=Path(str(archive)+'.partial')
    rows=[]
    for path in package.rglob('*'):
        if '__pycache__'not in path.parts:rows.append((path,'iris-sdk4-experimental/'+str(path.relative_to(package))))
    for path in HERE.rglob('*'):
        if path.is_file()and'__pycache__'not in path.parts:rows.append((path,'iris-sdk4-tools/'+str(path.relative_to(HERE))))
    with partial.open('xb')as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0)as compressed,tarfile.open(fileobj=compressed,mode='w|',format=tarfile.PAX_FORMAT)as tar:
        for path,name in sorted(rows,key=lambda row:row[1]):
            before=path.lstat();info=tarfile.TarInfo(name);info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;info.mode=stat.S_IMODE(before.st_mode)
            if stat.S_ISDIR(before.st_mode):info.type=tarfile.DIRTYPE;tar.addfile(info)
            elif stat.S_ISLNK(before.st_mode):
                if not path.resolve().is_relative_to(package):raise ValueError('Archive symlink escapes package')
                info.type=tarfile.SYMTYPE;info.linkname=os.readlink(path);tar.addfile(info)
            elif stat.S_ISREG(before.st_mode):
                expected=inputs.get(str(path.resolve()))
                if expected is None:raise ValueError('Unbound archive file: '+str(path))
                info.size=before.st_size
                class Reader:
                    def __init__(self,stream):self.stream=stream;self.hash=hashlib.sha256()
                    def read(self,count=-1):
                        data=self.stream.read(count);self.hash.update(data);return data
                with path.open('rb')as stream:
                    reader=Reader(stream);tar.addfile(info,reader)
                    if signature(before)!=signature(os.fstat(stream.fileno()))or signature(before)!=signature(path.lstat())or reader.hash.hexdigest()!=expected:
                        raise ValueError('Archive source changed: '+str(path))
            else:raise ValueError('Unexpected archive file type: '+str(path))
    partial.rename(archive)
    report={'schema':'iris.combined_sdk4.review_closure.v1','status':'ready_for_coordinator_review_not_published',
        'package':str(package),'package_provenance_sha256':sha(package/'provenance.json'),'binary_sha256':provider.BINARY,
        'uart_sha256':provider.UART,'launcher_sha256':sha(package/'launch.py'),'native_device_abi':4,
        'full_source_rebuilds_byte_identical':3,'packaged_source_rebuilds_byte_identical':2,
        'provider_tests':acceptance['tests']['run'],'fresh_merlin_regions':acceptance['actual_generic_merlin_hook']['region_count'],
        'automatic_fatal_resolution_harts':[row['hart']for row in acceptance['automatic_fatal_resolution']],
        'local_native_evidence_groups':19,'root_os_companion_sha256':provider.OS_COMPANION,
        'incident_record':'evidence/inspection-correction.json inside package; exact CAS restore verified',
        'prior_attempts':['build/combined-sdk4-rebuild-v1: native564 remained separate, missing C source-location prefix map',
            'build/combined-sdk4-package-v1: pre-launcher package retained',
            'build/combined-sdk4-package-acceptance-v2: fatal fixtures lacked dtc/explicitDTB; refused during initialization, corrected fixtures use packaged DTB'],
        'input_sha256':inputs,'artifact_sha256':{path.name:sha(path)for path in out.iterdir()if path.is_file()},
        'primary_published':False,'hardware_contacted':False,'rtl_certified':False,'full_knownness_certified':False,
        'timing_calibrated':False,'held_out_2pct':False,'deployed_image_association_verified':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'report.json')
if __name__=='__main__':main()
