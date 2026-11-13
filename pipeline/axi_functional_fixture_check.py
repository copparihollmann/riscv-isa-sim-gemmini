#!/usr/bin/env python3
"""Build the explicit external AXI snapshot/ownership fixture unit proof."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);compiler=Path(shutil.which('g++')).resolve();source=ROOT/'pipeline/test_axi_functional_fixture.cpp';header=source.with_name('axi_functional_fixture.hpp');binary=out/'check';argv=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)];r=subprocess.run(argv,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError(r.stderr)
    r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError(r.stderr)
    inputs=[Path(__file__).resolve(),source,header,compiler];hashes={str(p):sha(p)for p in inputs};archive=out/'inputs';archive.mkdir()
    for path in inputs:shutil.copy2(path,archive/hashes[str(path)])
    report=dict(schema='iris.axi.functional_snapshot_fixture.v1',status='passed_owned_snapshots_and_ordering_refusals',findings=json.loads(r.stdout),input_sha256=hashes,argv=argv,binary_sha256=sha(binary),functional_policy='AR-acceptance snapshot; AW plus full W burst commits strobed bytes; overlapping outstanding conflicts refuse',timing_parameters_added=False,source_model_or_recorded_ready_injected=False,full_FASED_functional_bridge=False,full_host_token_bridge=False,calibration_usable=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['findings']))
if __name__=='__main__':main()
