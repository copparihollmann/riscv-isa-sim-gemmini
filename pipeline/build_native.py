#!/usr/bin/env python3
"""Build an isolated pipeline tree and its ABI-matched finite clocked UART."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'pipeline/riscv-isa-sim-next')
    parser.add_argument('--build',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next')
    parser.add_argument('--jobs',type=int,default=24)
    args=parser.parse_args();source=args.source.resolve();build=args.build.resolve();build.mkdir(exist_ok=True,parents=True)
    if args.jobs<1:raise ValueError('positive jobs required')
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!='72958551566a30f19444bd7e354552824e4d0a98':
        raise RuntimeError('wrong pinned Spike base')
    if source==ROOT/'third_party/riscv-isa-sim' or build in (ROOT/'spike/build',ROOT/'spike/bin'):
        raise RuntimeError('isolated builder refuses primary paths')
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    env['CC']=shutil.which('gcc');env['CXX']=shutil.which('g++')
    commands=[];started=time.perf_counter()
    phases=[] if (build/'Makefile').is_file() else [('configure',[str(source/'configure'),'--with-boost=no','--with-boost-asio=no','--with-boost-regex=no','CXXFLAGS=-O2 -g0'])]
    phases += [('native',['make','-j'+str(args.jobs),'spike'])]
    for name,argv in phases:
        with (build/(name+'.log')).open('w') as output:
            p=subprocess.run(argv,cwd=build,env=env,stdout=output,stderr=subprocess.STDOUT)
        commands.append(dict(name=name,argv=argv,exit_status=p.returncode,log_sha256=sha(build/(name+'.log'))))
        if p.returncode:raise RuntimeError(name+' failed; see '+str(build/(name+'.log')))
    includes=build/'sdk';includes.mkdir(exist_ok=True)
    for name in ('riscv','fesvr','fdt'):
        path=includes/name
        if path.is_symlink() and path.resolve()!=source/name:raise RuntimeError('wrong existing SDK symlink')
        if not path.exists():path.symlink_to(source/name,target_is_directory=True)
    compiler=Path(shutil.which('g++')).resolve()
    flags=[str(compiler),'-std=c++20','-O2','-I'+str(includes),'-I'+str(build),'-iquote',str(source/'riscv'),
           '-I'+str(ROOT/'board'),'-I'+str(ROOT/'board/uart-device')]
    dep=build/'uart-plugin.d';plugin=build/'libsifive_uart.so'
    argv=flags+['-fPIC','-shared','-MMD','-MF',str(dep),str(ROOT/'board/uart-device/plugin.cc'),'-o',str(plugin)]
    p=subprocess.run(argv,env=env,capture_output=True,text=True)
    (build/'uart.build.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise RuntimeError('clocked UART build failed: '+p.stderr)
    commands.append(dict(name='clocked-uart',argv=argv,exit_status=p.returncode,log_sha256=sha(build/'uart.build.log')))
    exports=subprocess.check_output(['nm','-D',str(build/'spike')],text=True)
    if not any(line.split()[-1:]==['iris_device_clock_abi_v1'] and ' T ' in line for line in exports.splitlines()):
        raise RuntimeError('native clock ABI export missing')
    dependencies=[Path(n).resolve() for n in shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])]
    if not any(p.name=='iris_clocked_device.h' for p in dependencies):raise RuntimeError('clock SDK missing from plugin dependency receipt')
    tests=[]
    for name,path in [('clock',ROOT/'board/uart-device/clock_test.cpp'),('helper',ROOT/'board/tests/uart_test.cpp')]:
        target=build/('uart-'+name+'-test')
        cmd=flags+['-Wall','-Wextra','-Werror',str(path),'-o',str(target)]
        subprocess.run(cmd,env=env,check=True,capture_output=True,text=True)
        run=subprocess.run([str(target)],check=True,capture_output=True,text=True)
        tests.append(dict(name=name,argv=cmd,executable_sha256=sha(target),source_sha256=sha(path),stdout=run.stdout))
        dependencies.append(path)
    dependencies += [Path(__file__).resolve(),compiler,source/'riscv/simif.h',source/'riscv/sim.h',build/'config.h',
                     ROOT/'board/uart-source-evidence.json',ROOT/'benchmarks/uart_drain.h',ROOT/'benchmarks/uart_drain.S']
    receipt=dict(schema='iris.shuttle.isolated_native_build.v1',status='native_and_matched_clocked_uart_built',
                 binary_sha256=sha(build/'spike'),uart_sha256=sha(plugin),host_seconds=time.perf_counter()-started,
                 source=str(source),build=str(build),base_commit='72958551566a30f19444bd7e354552824e4d0a98',
                 source_overlay_sha256=hashlib.sha256(subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD'])).hexdigest(),
                 commands=commands,tests=tests,input_sha256={str(p):sha(p) for p in sorted(set(dependencies))},
                 native_device_abi=1,physical_uart_hz=500000000,rtc_hz=500000,
                 calibrated=False,rtl_certified=False,held_out_2pct=False)
    (build/'pipeline-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(status=receipt['status'],receipt=str(build/'pipeline-build.json'),binary_sha256=receipt['binary_sha256'])))


if __name__=='__main__':main()
