#!/usr/bin/env python3
"""Rebuild the selected release from its locked SDK4 sources into a fresh directory."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import shutil

HERE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',type=Path)
    parser.add_argument('--jobs',type=int,default=8);parser.add_argument('--dtc',type=Path)
    parser.add_argument('--no-selftest',action='store_true',help='Explicit build-only run; retain its untested build receipt')
    parser.add_argument('--verify-only',action='store_true')
    a=parser.parse_args()
    spec=importlib.util.spec_from_file_location('iris_primary_build_provider',HERE/'provider.py');provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)
    value=provider.experimental_functional_simulator()
    if value.get('available')is not True:raise ValueError(value.get('reason'))
    if a.verify_only:
        print(json.dumps({'status':'verified','native_binary_sha256':value['native_binary_sha256'],'launcher_sha256':value['binary_sha256'],'primary_modified':False}));return
    if a.jobs<1:raise ValueError('Positive jobs required')
    release=Path(value['selected_release']);out=(a.output or HERE.parent/'build'/('sdk4-primary-rebuild-'+uuid.uuid4().hex)).resolve()
    env=dict(os.environ)
    if a.dtc:
        compiler=a.dtc.resolve(strict=True);env['DTC']=str(compiler);env['PATH']=str(compiler.parent)+os.pathsep+env['PATH']
    # The selected359 epoch was built with these host compiler bytes. A dtc
    # search-path override must not silently switch C/C++ to Conda compilers.
    recorded=json.loads((release/'evidence/packaged-rebuild.json').read_text())['tool_sha256']
    compiler_dirs=[]
    for name in ['gcc','g++']:
        choices=[Path(path)for path in recorded if Path(path).name==name]
        if len(choices)!=1 or provider._sha(choices[0])!=recorded[str(choices[0])]:
            raise ValueError('Recorded host compiler unavailable or changed: '+name)
        compiler_dirs.append(str(choices[0].parent))
    env['PATH']=os.pathsep.join(dict.fromkeys([*compiler_dirs,*env['PATH'].split(os.pathsep)]))
    if a.dtc and provider._sha(Path(shutil.which('dtc',path=env['PATH'])).resolve())!=provider._sha(a.dtc.resolve()):
        raise ValueError('Requested dtc conflicts with pinned host-tool search path')
    command=[sys.executable,str(release/'build.py'),'--output',str(out),'--source-snapshot',str(release/'source'),'--jobs',str(a.jobs)]
    subprocess.run(command,env=env,check=True)
    report=json.loads((out/'rebuild.json').read_text())
    if not(report['binary_byte_identical']and report['uart_byte_identical']):raise ValueError('Different byte epoch: preserve new build and qualify it before release; active model unchanged')
    if not a.no_selftest:
        subprocess.run([sys.executable,str(HERE/'selftest.py'),'--kind','all','--native-build',report['build'],'--output',str(out/'selftests')],env=env,check=True)
    print(json.dumps({'status':'rebuilt_exact_selected_release','receipt':str(out/'rebuild.json'),'native_binary_sha256':report['binary_sha256'],
        'uart_sha256':report['uart_sha256'],'primary_modified':False,'selftests_run':not a.no_selftest}))
if __name__=='__main__':main()
