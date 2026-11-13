#!/usr/bin/env python3
"""Rebuild the clean Zvt oracle from Git objects, excluding all Iris patches."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

HERE=Path(__file__).resolve().parent
PIN='72958551566a30f19444bd7e354552824e4d0a98'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dtc',default=os.environ.get('DTC') or shutil.which('dtc'))
    parser.add_argument('--jobs',type=int,default=8)
    args=parser.parse_args()
    if not args.dtc:parser.error('--dtc required')
    archive=subprocess.check_output(['git','-C',str(HERE.parent/'third_party/riscv-isa-sim'),'archive',PIN])
    source=HERE/'reference-source'
    if source.exists():raise SystemExit('reference-source already exists; use a fresh output directory to avoid reusing modified reference inputs')
    source.mkdir()
    # All archive members come from the pinned, locally owned Git object tree.
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.name.startswith('/') or '..' in Path(member.name).parts:raise ValueError('Unsafe archive member')
        tar.extractall(source)
    build=HERE/'reference-build';build.mkdir(exist_ok=True)
    env=dict(os.environ,DTC=str(Path(args.dtc).resolve()),CC=os.environ.get('CC') or shutil.which('gcc'),CXX=os.environ.get('CXX') or shutil.which('g++'));env['PATH']=str(Path(args.dtc).resolve().parent)+os.pathsep+env['PATH']
    config=[str(source/'configure'),f'--prefix={HERE}/reference-install','--with-boost=no','--with-boost-asio=no','--with-boost-regex=no']
    with (build/'configure.log').open('w') as log:subprocess.run(config,cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    with (build/'build.log').open('w') as log:subprocess.run(['make',f'-j{args.jobs}','spike'],cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    binary=HERE/'bin/spike-zvt-reference';binary.parent.mkdir(exist_ok=True);shutil.copy2(build/'spike',binary);subprocess.run(['strip',str(binary)],check=True)
    (HERE/'reference-build.json').write_text(json.dumps({'upstream_spike_sha':PIN,'source_archive_sha256':hashlib.sha256(archive).hexdigest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'configure_argv':config,'unmodified_upstream':True},indent=2)+'\n')

if __name__=='__main__':main()
