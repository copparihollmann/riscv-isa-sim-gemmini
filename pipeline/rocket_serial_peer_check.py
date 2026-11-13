#!/usr/bin/env python3
"""Build real CPU producer/Serial/LP composition against frozen context SDKs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    capsule=ROOT/'build/serial-memory-system-component-v1/report.json';verify=ROOT/'build/serial-memory-system-component-v1-verify/report.json'
    if sha(capsule)!='4f644f1866fc9579c69e541f8467afcd73abfece97c099886cd5ec56f4c09b07'or sha(verify)!='a3af2b47cc3f7de4e1ba0a652c9b2d76787158edecc5396b566762cb073d21b1':raise ValueError('fixed-context source capsule changed')
    system=ROOT/'build/serial-memory-system-native-v2';build=json.loads((system/'build.json').read_text());lp=ROOT/'build/serial-memory-context-sdk-v2/fased/sdk';front=ROOT/'build/rocket-source-frontend-component-v3/obj';arb=ROOT/'build/rocket-dcache-arbiter-component-v3';runtime=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
    libs=[system/'sdk/libiris_serial_memory_system.a',lp/'libiris_fased_service.a',*[Path(x)for x in build['required_static_libraries_in_link_order']],front/'VIrisRocketFrontendPeer__ALL.a',arb/'obj/VHellaCacheArbiter_1__ALL.a']
    if sha(libs[0])!=build['library_sha256']:raise ValueError('System library changed')
    for path,digest in build['required_child_library_sha256'].items():
        if sha(path)!=digest:raise ValueError('fixed child library changed')
    sources=[ROOT/'pipeline'/n for n in ['test_rocket_serial_peer.cpp','rocket_serial_peer.cpp','rocket_dcache_arbiter.cpp','rocket_frontend_rtl_peer.cpp']]
    includes=[ROOT/'pipeline',system/'sdk',lp,*[Path(x)for x in build['required_include_directories']],front,arb,arb/'obj',ROOT/'build/frontend-owned-contexts-v2'];compiler=Path(shutil.which('g++')).resolve();binary=out/'check'
    command=[str(compiler),'-std=c++20','-O2','-pthread',*['-I'+str(x)for x in includes],'-isystem',str(runtime),'-isystem',str(runtime/'vltstd'),*[str(x)for x in sources],'-Wl,--start-group',*[str(x)for x in libs],'-Wl,--end-group','-o',str(binary)];r=subprocess.run(command,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('serial producer compile: '+r.stderr[-5000:])
    lp_identity='1d1d497a614cda9e0076368589246bceaeb2cb5dcc20c82d951c6f2566257f85';argv=[str(binary),build['source_identity'],lp_identity];r=subprocess.run(argv,text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('serial producer gate: '+r.stderr[-5000:])
    rows=[json.loads(line)for line in r.stdout.splitlines()];files=[Path(__file__).resolve(),*sources,*[ROOT/'pipeline'/n for n in ['rocket_serial_peer.hpp','axi_functional_fixture.hpp','rocket_dcache_arbiter.hpp','rocket_frontend_rtl_peer.hpp']],*libs,capsule,verify,system/'build.json',compiler];hashes={str(x):sha(x)for x in files};archive=out/'inputs';archive.mkdir()
    for path in files:
        dst=archive/hashes[str(path)]
        if not dst.exists():shutil.copy2(path,dst)
    report=dict(schema='iris.rocket.source_serial_producer_composition.v1',status=rows[-1]['status'],findings=rows,input_sha256=hashes,command=command,argv=argv,binary_sha256=sha(binary),source_state_or_ready_injected=False,post_cork_synthetic_actor_removed=True,LP_parameters='explicit fixture30/30/16/16; no calibration default',functional_memory_policy='AR snapshots; AW/W ownership; conflicting outstanding accesses refuse',reset_scope='explicit component resets and both-external-reset-only diagnostic suppression',native_CPU_execution=False,full_FASED_functional_or_host_bridge=False,full_knownness_certified=False,timing_certified=False,loaded_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(rows[-1]))
if __name__=='__main__':main()
