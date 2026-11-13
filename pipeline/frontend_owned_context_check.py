#!/usr/bin/env python3
"""Check source frontend host contexts without regenerating or editing RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    shuttle=ROOT/'build/frontend-rtl-peer-component-v2';rocket=ROOT/'build/rocket-source-frontend-component-v3'
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/frontend_rtl_peer_context.cpp',ROOT/'pipeline/frontend_rtl_peer.hpp',ROOT/'pipeline/rocket_frontend_rtl_peer.cpp',ROOT/'pipeline/rocket_frontend_rtl_peer.hpp',ROOT/'pipeline/test_frontend_contexts.cpp']
    for component in (shuttle,rocket):
        r=json.loads((component/'results.json').read_text());inputs.append(component/'results.json')
        for path,digest in r['input_sha256'].items():
            if sha(path)!=digest:raise ValueError('component input changed: '+path)
            inputs.append(Path(path))
    shutil.copy2(rocket/'zero_inputs.inc',out/'rocket_zero_inputs.inc');inputs.append(out/'rocket_zero_inputs.inc')
    inc=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');compiler=Path(shutil.which('g++')).resolve();inputs.append(compiler)
    archives=[shuttle/'obj/VShuttleFrontend__ALL.a',rocket/'obj/VIrisRocketFrontendPeer__ALL.a']
    runtime=[shuttle/'obj/verilated.o',shuttle/'obj/verilated_threads.o']
    inputs+=archives+runtime
    for component in (shuttle,rocket):inputs+=list((component/'obj').glob('*.h'))
    inputs+=list(inc.glob('*.h'))+list((inc/'vltstd').glob('*.h'))
    before={str(p):sha(p)for p in inputs}
    binary=out/'test_frontend_contexts'
    argv=[str(compiler),'-std=c++20','-O2','-I'+str(ROOT/'pipeline'),'-I'+str(out),'-I'+str(shuttle),'-I'+str(shuttle/'obj'),'-I'+str(rocket/'obj'),'-I'+str(inc),'-I'+str(inc/'vltstd'),str(ROOT/'pipeline/test_frontend_contexts.cpp'),str(ROOT/'pipeline/frontend_rtl_peer_context.cpp'),str(ROOT/'pipeline/rocket_frontend_rtl_peer.cpp'),'-Wl,--whole-archive']+[str(p)for p in archives]+['-Wl,--no-whole-archive']+[str(p)for p in runtime]+['-pthread','-o',str(binary)]
    r=subprocess.run(argv,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('frontend context host build failed: '+r.stderr[-6000:])
    r=subprocess.run([str(binary)],text=True,capture_output=True,timeout=30);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('frontend context interleave test failed: '+r.stderr)
    findings=json.loads(r.stdout)
    if before!={str(p):sha(p)for p in inputs}:raise ValueError('source/model input changed during context test')
    archive=out/'inputs';archive.mkdir();archived={}
    for path in inputs:
        h=before[str(path)];dst=archive/h
        if not dst.exists():shutil.copy2(path,dst)
        archived[str(path)]={'sha256':h,'archive':str(dst)}
    report=dict(schema='iris.frontend.owned_context_component.v1',status=findings['status'],findings=findings,input_sha256=before,archived_inputs=archived,argv=argv,binary_sha256=sha(binary),rtl_regenerated=False,existing_model_objects_unchanged=True,native_integration=False,calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
