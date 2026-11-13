#!/usr/bin/env python3
"""Compile the actual saved Shuttle frontend as a small standalone C++ peer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    gen=ROOT/'build/rtl-verilator/gen-collateral';tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');perl=tool.with_name('perl');compiler=Path(shutil.which('g++')).resolve();test=ROOT/'pipeline/test_frontend_unit.cpp';obj=out/'obj'
    flags='-std=c++20 -O2 -I'+str(out)
    commands=[[str(perl),str(tool),'--cc','--exe','--top-module','ShuttleFrontend','-Wno-fatal','--Mdir',str(obj),'-y',str(gen),'+libext+.sv',str(gen/'ShuttleFrontend.sv'),str(test),'-CFLAGS',flags],
              ['make','-C',str(obj),'-f','VShuttleFrontend.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,argv in enumerate(commands):
        if i==1:
            header=(obj/'VShuttleFrontend.h').read_text();inputs=re.findall(r'VL_IN(?:8|16|64|W)?\(&([A-Za-z0-9_]+),',header)
            if not inputs or 'io_ptw_status_prv' not in inputs:raise ValueError('source frontend input schema changed')
            (out/'zero_inputs.inc').write_text(''.join('dut.'+name+'=0;\n' for name in inputs))
        r=subprocess.run(argv,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('small source frontend build failed: '+r.stderr)
    binary=obj/'VShuttleFrontend';r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source frontend peer exercise failed: '+r.stderr)
    findings=json.loads(r.stdout)
    actual_inputs=[]
    for line in (obj/'VShuttleFrontend__verFiles.dat').read_text().splitlines():
        if line.startswith('S '):
            path=Path(line.rsplit('"',2)[1]);actual_inputs.append(path)
    actual_inputs += [Path(__file__).resolve(),test,tool,perl,compiler,out/'zero_inputs.inc']
    report=dict(schema='iris.frontend.source_runtime_component.v1',status=findings['status'],findings=findings,input_sha256={str(p):sha(p) for p in actual_inputs},commands=commands,binary_sha256=sha(binary),
                scope='Actual13-module saved Shuttle frontend in compiled C++: cache/BTB/BHT/6entryRAS/ITLB/RVC/queue. External synthetic ROM peer and backpressure; reset-only initialization. No source-state injection or native CPU integration.',
                service_policy='FirstDbeat3edges after acceptedA and8consecutive beats is an explicit synthetic test stimulus, never an Iris latency parameter.',
                native_integration=False,calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
