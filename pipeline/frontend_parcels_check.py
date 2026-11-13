#!/usr/bin/env python3
"""Check timing predecode using the saved source RVCExpander as an oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator').resolve();perl=tool.with_name('perl').resolve()
    source=ROOT/'pipeline/evidence/rvc/RVCExpander.sv';test=ROOT/'pipeline/test_frontend_parcels.cpp'
    compiler=Path(shutil.which('g++')).resolve()
    commands=[[str(perl),str(tool),'--cc','--exe','-Wno-fatal','--top-module','RVCExpander','--Mdir',str(out/'obj'),str(source),str(test),'-CFLAGS','-std=c++20 -O2 -Wall -Wextra -Werror'],
              ['make','-C',str(out/'obj'),'-f','VRVCExpander.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,argv in enumerate(commands):
        b=subprocess.run(argv,text=True,capture_output=True);(out/f'build-{i}.log').write_text(b.stdout+b.stderr)
        if b.returncode:raise RuntimeError('RTL oracle build failed: '+b.stderr)
    binary=out/'obj/VRVCExpander';r=subprocess.run([str(binary)],text=True,capture_output=True)
    (out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source frontend predecode failed: '+r.stderr)
    files=[Path(__file__).resolve(),source,test,ROOT/'pipeline/frontend_parcels.hpp',ROOT/'pipeline/evidence/rvc/saved-rtl-manifest.json',ROOT/'third_party/shuttle/src/main/scala/ifu/Frontend.scala',
           ROOT/'third_party/rocket-chip/src/main/scala/rocket/RVC.scala',ROOT/'third_party/rocket-chip/src/main/scala/rocket/BTB.scala',tool,perl,compiler]
    evidence=[dict(path=str(ROOT/'third_party/shuttle/src/main/scala/ifu/Frontend.scala'),lines=[[259,326]],revision='a536ed1df91a0f65770e36758291d02a8cb929c4'),
              dict(path=str(ROOT/'third_party/rocket-chip/src/main/scala/rocket/RVC.scala'),lines=[[19,43],[77,111],[145,169],[183,186]],revision='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0')]
    report=dict(schema='iris.frontend.parcel_predecode.v1',status='passed_source_CFI_predecode',inputs=65536,upper_halfword_variants=4,rtl_oracle_comparisons=262144,stdout=r.stdout,
                input_sha256={str(p):sha(p) for p in files},source_evidence=evidence,commands=commands,binary_sha256=sha(binary),
                scope='CFI opcode/register-bit classification for all low16 encodings and4 upper halves, including reserved encodings; packet position/carry/cutoff controls. This does not execute instructions or certify architectural legality.',
                native_integration=False,calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(r.stdout.strip())
if __name__=='__main__':main()
