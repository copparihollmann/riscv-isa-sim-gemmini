#!/usr/bin/env python3
"""Link actual processor precision guards against this isolated source SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);build=a.build.resolve();source=a.source.resolve()
    proof=json.loads((build/'pipeline-build.json').read_text())
    archives=[Path(name)for name in proof['input_sha256']if Path(name).name=='VShuttleFrontend__ALL.a']
    if len(archives)!=1 or sha(archives[0])!=proof['input_sha256'][str(archives[0])]:raise ValueError('actual native source frontend archive missing/changed')
    obj=archives[0].parent
    rocket=[Path(name)for name in proof['input_sha256']if Path(name).name=='VIrisRocketFrontendPeer__ALL.a']
    if len(rocket)!=1 or sha(rocket[0])!=proof['input_sha256'][str(rocket[0])]:raise ValueError('Rocket model archive missing/changed')
    if sha(build/'spike')!=proof['binary_sha256'] or sha(build/'libsifive_uart.so')!=proof['uart_sha256']:raise ValueError('native SDK binary identity changed')
    compiler=Path(shutil.which('g++')).resolve();test=ROOT/'pipeline/test_rocket_context.cpp';target=out/'test_context'
    argv=[str(compiler),'-std=c++20','-O2','-DIRIS_TEST_RVC','-DIRIS_TEST_SPLIT_FETCH','-iquote',str(build)]
    for directory in ('','riscv','fesvr','fdt'):argv+=['-iquote',str(source/directory)]
    argv += [str(test),'-L'+str(build),'-lriscv','-ldisasm','-lsoftfloat','-lfesvr','-lfdt','-Wl,--whole-archive',str(obj/'VShuttleFrontend__ALL.a'),str(rocket[0]),'-Wl,--no-whole-archive',str(obj/'verilated.o'),str(obj/'verilated_threads.o'),'-lpthread','-o',str(target)]
    r=subprocess.run(argv,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('actual source processor guard link failed: '+r.stderr[-1000:])
    r=subprocess.run([str(target)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode or 'PASS actual processor' not in r.stdout:raise ValueError('actual source processor precision guard failed')
    files=[Path(__file__).resolve(),test,ROOT/'pipeline/test_context.cpp',ROOT/'pipeline/test_frontend_context.cpp',rocket[0],source/'riscv/csrs.cc',compiler,source/'riscv/processor.cc',source/'riscv/processor.h',source/'riscv/iris_timing_adapter.h',build/'pipeline-build.json',obj/'VShuttleFrontend__ALL.a',obj/'verilated.o',obj/'verilated_threads.o',*[build/f'lib{x}.a'for x in ('riscv','disasm','softfloat','fesvr','fdt')]]
    report=dict(schema='iris.rocket.actual_context_PMP_guards.v1',status='passed_actual_processor_context_and_source_PMP_guards',binary_sha256=proof['binary_sha256'],uart_sha256=proof['uart_sha256'],input_sha256={str(p):sha(p)for p in files},argv=argv,executable_sha256=sha(target),stdout_sha256=sha(out/'stdout'),calibrated=False,rtl_certified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'])))
if __name__=='__main__':main()
