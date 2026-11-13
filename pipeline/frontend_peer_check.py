#!/usr/bin/env python3
"""Build/test the typed saved-RTL frontend peer with explicit synthetic memory."""
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
    gen=ROOT/'build/rtl-verilator/gen-collateral';tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');perl=tool.with_name('perl');compiler=Path(shutil.which('g++')).resolve();test=ROOT/'pipeline/test_frontend_peer.cpp';peer=ROOT/'pipeline/frontend_rtl_peer.cpp';obj=out/'obj'
    flags='-std=c++20 -O2 -I'+str(out)+' -I'+str(ROOT/'pipeline')
    commands=[[str(perl),str(tool),'--cc','--exe','--top-module','ShuttleFrontend','-Wno-fatal','--Mdir',str(obj),'-y',str(gen),'+libext+.sv',str(gen/'ShuttleFrontend.sv'),str(test),str(peer),'-CFLAGS',flags],
              ['make','-C',str(obj),'-f','VShuttleFrontend.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,argv in enumerate(commands):
        if i==1:
            header=(obj/'VShuttleFrontend.h').read_text();inputs=re.findall(r'VL_IN(?:8|16|64|W)?\(&([A-Za-z0-9_]+),',header)
            if not inputs or 'io_ptw_status_prv' not in inputs:raise ValueError('source frontend input schema changed')
            (out/'zero_inputs.inc').write_text(''.join('dut.'+name+'=0;\n' for name in inputs))
        r=subprocess.run(argv,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('source frontend peer build failed; see '+str(out/f'build-{i}.log'))
    binary=obj/'VShuttleFrontend';r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source frontend peer failed: '+r.stderr)
    findings=json.loads(r.stdout);actual=[]
    for line in (obj/'VShuttleFrontend__verFiles.dat').read_text().splitlines():
        if line.startswith('S '):actual.append(Path(line.rsplit('"',2)[1]))
    actual += [Path(__file__).resolve(),test,peer,ROOT/'pipeline/frontend_rtl_peer.hpp',tool,perl,compiler,out/'zero_inputs.inc']
    archive=out/'inputs';archive.mkdir();archived={}
    for path in actual:
        digest=sha(path);target=archive/digest
        if not target.exists():shutil.copy2(path,target)
        archived[str(path)]={'sha256':digest,'archive':str(target)}
    report=dict(archived_inputs=archived,schema='iris.frontend.typed_source_peer.v1',status=findings['status'],findings=findings,input_sha256={str(p):sha(p) for p in actual},commands=commands,binary_sha256=sha(binary),
                scope='Exact saved Shuttle frontend typed evaluate/commit peer, reset only. Mixed parcels, source backpressure, redirect during an accepted refill, invalidate/refill and interface/protocol refusals. Synthetic ROM service is not a hardware latency parameter.',
                native_integration=False,source_state_injected=False,calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
