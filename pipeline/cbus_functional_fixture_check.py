#!/usr/bin/env python3
"""Verify the explicit CBUS-only fixture, independently of any outer service."""
import argparse,hashlib,json,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);compiler=Path(shutil.which('g++')).resolve();source=ROOT/'pipeline/test_cbus_functional_fixture.cpp';header=ROOT/'pipeline/cbus_functional_fixture.hpp';fabric=ROOT/'build/memory-fabric-coupled-native-v4/sdk';binary=out/'check';cmd=[str(compiler),'-std=c++20','-O2','-I'+str(fabric),str(source),'-o',str(binary)];r=subprocess.run(cmd,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError('CBUS fixture build failed')
 r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
 if r.returncode:raise RuntimeError('CBUS fixture checks failed')
 findings=json.loads(r.stdout);files=[Path(__file__).resolve(),compiler,source,header,fabric/'memory_fabric.hpp'];report=dict(schema='iris.functional_CBUS_fixture.v1',status=findings['status'],findings=findings,input_sha256={str(p):sha(p)for p in files},command=cmd,binary_sha256=sha(binary),explicit_synthetic_edge_parameters=True,post_cork_service_ports_present=False,timing_certified=False);(out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
