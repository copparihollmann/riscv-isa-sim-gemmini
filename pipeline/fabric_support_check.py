#!/usr/bin/env python3
"""Freeze bounded pending-result and source physical-event lifecycle tests."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);compiler=Path(shutil.which('g++')).resolve();rows=[];files=[Path(__file__).resolve(),compiler]
    for name,sources in [('pending-values',['test_frontend_values_fabric.cpp']),('physical-events',['test_fabric_engine.cpp','fabric_engine.cpp'])]:
        paths=[ROOT/'pipeline'/n for n in sources];files.extend(paths);binary=out/name;argv=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror',*[str(x)for x in paths],'-o',str(binary)];r=subprocess.run(argv,text=True,capture_output=True);(out/(name+'.build.log')).write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError(name+' compile failed: '+r.stderr)
        r=subprocess.run([str(binary)],text=True,capture_output=True);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        if r.returncode:raise RuntimeError(name+' functional guard failed: '+r.stderr)
        rows.append(dict(name=name,argv=argv,binary_sha256=sha(binary),findings=json.loads(r.stdout)));print(r.stdout.strip())
    files.extend(ROOT/'pipeline'/name for name in ('fabric_engine.hpp','frontend_values_fabric.hpp'))
    archive=out/'inputs';archive.mkdir();hashes={str(x):sha(x)for x in files}
    for path in files:
        target=archive/hashes[str(path)]
        if not target.exists():shutil.copy2(path,target)
    report=dict(schema='iris.rocket.fabric_support_components.v1',status='passed_bounded_values_and_physical_events',input_sha256=hashes,rows=rows,source_contract=ROOT.as_posix()+'/build/rocket-memory-phase-proof-v2/report.json',source_contract_sha256=sha(ROOT/'build/rocket-memory-phase-proof-v2/report.json'),calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
