#!/usr/bin/env python3
"""Compare branch operands against both saved Shuttle and Rocket ALU modules."""
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
    perl=Path('/scratch/eygao/iris-cy/.conda-env/bin/perl').resolve();verilator=perl.with_name('verilator');compiler=Path(shutil.which('g++')).resolve()
    sources=[ROOT/'pipeline/frontend_branch_compare.sv',ROOT/'build/rtl-verilator/gen-collateral/RocketALU.sv',ROOT/'build/rtl-verilator/gen-collateral/RocketALU_6.sv']
    test=ROOT/'pipeline/test_frontend_branch_compare.cpp'
    commands=[[str(perl),str(verilator),'--cc','--exe','-Wno-fatal','--top-module','IrisBranchCompare','--Mdir',str(out/'obj'),*[str(p) for p in sources],str(test),'-CFLAGS','-std=c++20 -O2 -Wall -Wextra -Werror'],
              ['make','-C',str(out/'obj'),'-f','VIrisBranchCompare.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,argv in enumerate(commands):
        r=subprocess.run(argv,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('saved ALU oracle build failed: '+r.stderr)
    binary=out/'obj/VIrisBranchCompare';r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source ALU comparison failed: '+r.stderr)
    paths=[Path(__file__).resolve(),test,ROOT/'pipeline/frontend_branch.hpp',*sources,ROOT/'third_party/rocket-chip/src/main/scala/rocket/ALU.scala',ROOT/'third_party/rocket-chip/src/main/scala/rocket/IDecode.scala',ROOT/'build/rtl-verilator/gen-collateral/ShuttleCore.sv',ROOT/'build/rtl-verilator/gen-collateral/Rocket.sv',perl,verilator,compiler]
    report=dict(schema='iris.frontend.branch_compare_component.v1',status='passed_source_ALU_branch_comparison',stdout=r.stdout,input_sha256={str(p):sha(p) for p in paths},commands=commands,binary_sha256=sha(binary),
                source_pins=dict(rocket_chip='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0',shuttle='a536ed1df91a0f65770e36758291d02a8cb929c4'),
                source_evidence=['IDecode.scala74-82:6branches use FN_SEQ/SNE/SLT/SLTU/SGE/SGEU andDW_XPR','ALU.scala17-30,58-64,86-96:comparison computation','ShuttleCore.sv4079-4086 andRocket.sv1600-1606 ALU instantiation:concrete saved module selection'],
                scope='All6 branch comparisons on64 corner pairs+16384 seeded random pairs+16384equal pairs,2DW settings,2actual modules. Excludes instruction issue/retirement/prediction timing.',
                native_integration=False,calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(r.stdout.strip())
if __name__=='__main__':main()
