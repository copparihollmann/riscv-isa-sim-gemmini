#!/usr/bin/env python3
"""Rebuild the frozen SDK4 model in a fresh isolated workspace, offline."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
PIN='72958551566a30f19444bd7e354552824e4d0a98'
FROZEN_SHA='ef1214f25a2db5a01b6dd9aa1180b002c0f4da74ec987ac0a5b90bff10ed7088'
OVERLAY_SHA='e33269e90102a8a9137473eb4d6a0c7c276a2553972ab4e668ab62f041a82060'
BINARY_SHA='35901887c93ab80aa92e68aac2f26cefa6cc785ae8251d5dc283471aa97faf5d'
UART_SHA='cc9e38b8df42c0f482f94213a0f58747e1e1c66bd17d54eef154e3ea9748a34b'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def frozen_bytes(frozen,entry):
    stored=frozen/entry['object'];raw=stored.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['object_sha256']:raise ValueError('Frozen object corrupt: '+str(stored))
    data=gzip.decompress(raw)if entry['compression']=='gzip'else raw
    if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Frozen input corrupt')
    return data

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=8)
    p.add_argument('--base-repository',type=Path,default=ROOT/'third_party/riscv-isa-sim-combined')
    p.add_argument('--frozen',type=Path,default=ROOT/'build/combined-frozen-35901887')
    bundled=Path(__file__).resolve().parent/'source'
    p.add_argument('--source-snapshot',type=Path,default=bundled if bundled.is_dir()else None)
    a=p.parse_args()
    if a.jobs<1:raise ValueError('Positive jobs required')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);workspace=out/'workspace';workspace.mkdir()
    source=workspace/'third_party/riscv-isa-sim-combined';source.parent.mkdir()
    commands=[];start=time.monotonic()
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    env['CC']=shutil.which('gcc');env['CXX']=shutil.which('g++')
    def run(name,argv,cwd=None):
        log=out/(name+'.log');before=time.monotonic()
        with log.open('wb')as stream:
            result=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
        record={'phase':name,'argv':list(map(str,argv)),'cwd':str(cwd)if cwd else None,'exit_status':result.returncode,
            'host_seconds':time.monotonic()-before,'log_sha256':sha(log)};commands.append(record)
        if result.returncode:raise RuntimeError(name+' failed; preserve '+str(log))
    restored={}
    location_prefix=ROOT
    if a.source_snapshot:
        snapshot=a.source_snapshot.resolve();lock=json.loads((snapshot.parent/'source-lock.json').read_text())
        if lock['base_commit']!=PIN or lock['source_overlay_sha256']!=OVERLAY_SHA or lock['frozen_manifest_sha256']!=FROZEN_SHA:
            raise ValueError('Wrong packaged source epoch')
        location_prefix=Path(lock['historical_repository_root'])
        for name,value in lock['input_sha256'].items():
            relative=Path(name)
            if relative.is_absolute()or'..'in relative.parts:raise ValueError('Unsafe source snapshot path')
            original=snapshot/relative
            if original.is_symlink()or sha(original)!=value:raise ValueError('Packaged source changed: '+name)
            path=workspace/relative;path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,path)
            if not name.startswith('third_party/'):restored[name]=value
    else:
        frozen=a.frozen.resolve();manifest_path=frozen/'manifest.json'
        if sha(manifest_path)!=FROZEN_SHA:raise ValueError('Wrong frozen SDK4 source/evidence closure')
        manifest=json.loads(manifest_path.read_text())
        run('clone',['git','clone','--shared','--no-checkout',a.base_repository.resolve(),source])
        run('checkout',['git','-C',source,'checkout','--detach',PIN])
        patch=frozen/'source-overlay.patch'
        if sha(patch)!=OVERLAY_SHA:raise ValueError('Wrong frozen overlay')
        run('apply',['git','-C',source,'apply','--intent-to-add',patch])
        actual=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD'])
        if hashlib.sha256(actual).hexdigest()!=OVERLAY_SHA:raise ValueError('Applied overlay differs')
        for name,entry in manifest['files'].items():
            if name.startswith(('board/','timing/','pipeline/','hardware/','benchmarks/uart_drain.')):
                relative=Path(name)
                if relative.is_absolute()or'..'in relative.parts:raise ValueError('Unsafe frozen path')
                path=workspace/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(frozen_bytes(frozen,entry));path.chmod(entry['mode'])
                restored[name]=entry['sha256']
        plugin_entry=manifest['files']['build/combined-dev/uart-plugin.cc']
        plugin=workspace/'build/combined-dev/uart-plugin.cc';plugin.parent.mkdir(parents=True,exist_ok=True)
        plugin.write_bytes(frozen_bytes(frozen,plugin_entry));restored['build/combined-dev/uart-plugin.cc']=sha(plugin)
    plugin=workspace/'build/combined-dev/uart-plugin.cc'
    build=workspace/'build/spike-combined';build.mkdir(parents=True)
    # Reproduce source location strings while compiling only this frozen tree.
    flags='-O2 -g0 -ffile-prefix-map='+str(workspace)+'='+str(location_prefix)
    cflags='-g -O2 -ffile-prefix-map='+str(workspace)+'='+str(location_prefix)
    run('configure',[source/'configure','--with-boost=no','--with-boost-asio=no','--with-boost-regex=no',
        'CXXFLAGS='+flags,'CFLAGS='+cflags],build)
    run('native',['make','-j'+str(a.jobs),'spike'],build)
    sdk=build/'sdk';sdk.mkdir()
    for name in ['riscv','fesvr','fdt']:(sdk/name).symlink_to(source/name,target_is_directory=True)
    compiler=Path(env['CXX']).resolve()
    argv=[compiler,'-std=c++20','-O2','-ffile-prefix-map='+str(workspace)+'='+str(location_prefix),'-I'+str(sdk),'-I'+str(build),
        '-iquote',source/'riscv','-I'+str(workspace/'board'),'-I'+str(workspace/'board/uart-device'),
        '-fPIC','-shared','-MMD','-MF',build/'uart-plugin.d',plugin,'-o',build/'libsifive_uart.so']
    run('uart',argv,build)
    exported=subprocess.check_output(['nm','-D',str(build/'spike')],text=True)
    if not any(line.split()[-1:]==['iris_device_clock_abi_v4']and' T 'in line for line in exported.splitlines()):raise ValueError('SDK4 native clock export missing')
    source_inputs={str(path.relative_to(workspace)):sha(path)for path in workspace.rglob('*')
        if path.is_file()and'.git'not in path.parts and path.is_relative_to(source)}
    report={'schema':'iris.combined_sdk4.rebuild.v1','status':'built_not_published','base_commit':PIN,'frozen_manifest_sha256':FROZEN_SHA,
        'source_overlay_sha256':OVERLAY_SHA,'source':str(source),'build':str(build),'native_device_abi':4,
        'binary_sha256':sha(build/'spike'),'uart_sha256':sha(build/'libsifive_uart.so'),
        'reference_binary_sha256':BINARY_SHA,'reference_uart_sha256':UART_SHA,
        'binary_byte_identical':sha(build/'spike')==BINARY_SHA,'uart_byte_identical':sha(build/'libsifive_uart.so')==UART_SHA,
        'commands':commands,'restored_frozen_input_sha256':restored,'source_input_sha256':source_inputs,
        'tool_sha256':{str(Path(env[name]).resolve()):sha(Path(env[name]).resolve())for name in ['CC','CXX']},
        'builder_sha256':sha(__file__),'host_seconds':time.monotonic()-start,'primary_modified':False,
        'source_mode':'packaged_source_snapshot'if a.source_snapshot else'offline_git_base_plus_frozen_overlay',
        'rtl_certified':False,'calibrated':False,'held_out_2pct':False,'deployed_image_association_verified':False}
    (out/'rebuild.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'rebuild.json')
if __name__=='__main__':main()
