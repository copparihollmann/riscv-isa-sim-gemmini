#!/usr/bin/env python3
"""Build a new same-edge real Rocket frontend/arbiter/fabric consumer."""
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
    receipts={ROOT/'build/memory-fabric-component-v1/report.json':'8b2c64b19e69135e3c53a88ed34766cdd4ef7a8d03c5848ba85ae17961780f67',ROOT/'build/memory-fabric-component-v1-verify/report.json':'a5a12f40736836f73d0eca8ae75a8ba114e649bac8e52ea93ce49cdb74e6455a'}
    for path,digest in receipts.items():
        if sha(path)!=digest:raise ValueError('frozen component receipt changed: '+str(path))
    fabric=ROOT/'build/memory-fabric-coupled-native-v4/sdk';scoped=ROOT/'build/memory-fabric-context-sdk-v2';arb=ROOT/'build/rocket-dcache-arbiter-component-v3';front=ROOT/'build/rocket-source-frontend-component-v3/obj';runtime=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
    libs=[fabric/'libiris_memory_fabric.a',scoped/'cache/sdk/libiris_cache_hierarchy.a',scoped/'noc/sdk/libiris_noc.a',scoped/'adapters/sdk/libiris_memory_adapters.a',front/'VIrisRocketFrontendPeer__ALL.a',arb/'obj/VHellaCacheArbiter_1__ALL.a']
    if sha(libs[0])!='0f57cce8efb66472c736814ee2695242bb77e24c2f1ed7f5d643f0d4a1658e7b':raise ValueError('fabric native identity changed')
    sources=[ROOT/'pipeline'/name for name in ['test_rocket_fabric_peer.cpp','rocket_fabric_peer.cpp','rocket_dcache_arbiter.cpp','rocket_frontend_rtl_peer.cpp']]
    includes=[ROOT/'pipeline',fabric,arb,arb/'obj',front,ROOT/'build/frontend-owned-contexts-v2',runtime,runtime/'vltstd']
    compiler=Path(shutil.which('g++')).resolve();binary=out/'check'
    # Scoped SDK archives own one shared, exact-version Verilator runtime;
    # ordinary archive extraction avoids duplicate thread-local runtimes.
    command=[str(compiler),'-std=c++20','-O2','-pthread',*[ '-I'+str(x)for x in includes],*[str(x)for x in sources],'-Wl,--start-group',*[str(x)for x in libs],'-Wl,--end-group','-o',str(binary)]
    r=subprocess.run(command,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('composition compile failed: '+r.stderr[-5500:])
    r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('composition gate failed: '+r.stderr[-5500:])
    rows=[json.loads(line)for line in r.stdout.splitlines()];findings=rows[-1]
    inputs=[Path(__file__).resolve(),*sources,*[ROOT/'pipeline'/name for name in ['rocket_fabric_peer.hpp','rocket_dcache_arbiter.hpp','rocket_frontend_rtl_peer.hpp']],*libs,*receipts,arb/'rocket_dcache_arbiter_pins.inc',ROOT/'build/frontend-owned-contexts-v2/rocket_zero_inputs.inc',fabric/'memory_fabric.hpp',fabric/'memory_fabric_adapters.hpp',compiler]
    archive=out/'inputs';archive.mkdir();hashes={str(x):sha(x)for x in inputs}
    for path in inputs:
        dst=archive/hashes[str(path)]
        if not dst.exists():shutil.copy2(path,dst)
    report=dict(schema='iris.rocket.source_frontend_fabric_composition.v1',status=findings['status'],findings=rows,input_sha256=hashes,command=command,binary_sha256=sha(binary),external_service='explicit synthetic edge-3 post-cork Get test actor; not source Iris latency',source_state_injected=False,full_internal_knownness_certified=False,native_integration=False,timing_certified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
