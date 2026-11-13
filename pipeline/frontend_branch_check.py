#!/usr/bin/env python3
"""Check source MEM resolution from actual per-lane operands and control bits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);run=ROOT/'build/frontend-phase-branch512-v5';receipt=json.loads((run/'results.json').read_text())
    if not receipt['full448B_signature_matches_unobserved']:raise ValueError('whole CPU observer changed signature')
    trace=out/'actual-branch.tsv';count=0
    with (run/'phase.jsonl').open() as source,trace.open('w') as dest:
        for line in source:
            r=json.loads(line);b=r['before']
            if b['tile_reset']:continue
            row=[]
            for lane in (0,1):
                prefix='branch'+str(lane)+'_'
                row.extend([b[prefix+'valid'],b[prefix+'bits_ctrl_branch'],b[prefix+'bits_ctrl_jal'],b[prefix+'bits_ctrl_jalr'],int(b[prefix+'bits_ctrl_mem'] and b[prefix+'bits_ctrl_mem_cmd']==20),
                            b[prefix+'bits_inst'],b[prefix+'bits_pc'],b[prefix+'bits_wdata_bits'],b[prefix+'bits_rvc'],b[prefix+'bits_taken'],b[prefix+'bits_next_pc_valid'],b[prefix+'bits_next_pc_bits'],b[prefix+'bits_ras_head'],b['branch0_sfb'] if lane==0 else 0])
            row.extend([b['branch_selected'],b['branch_actual_predictor_update'],b['branch_actual_taken'],b['branch_actual_mispredict'],b['branch_actual_sfb'],b['branch_actual_call'],b['branch_npc_unaligned'],int(bool(b['branch_lane1'])),r['hart'],r['edge']])
            dest.write(' '.join(map(str,row))+'\n');count+=1
    compiler=Path(shutil.which('g++')).resolve();binary=out/'test_branch';test=ROOT/'pipeline/test_frontend_branch.cpp'
    argv=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror',str(test),'-o',str(binary)]
    c=subprocess.run(argv,text=True,capture_output=True);(out/'build.log').write_text(c.stdout+c.stderr)
    if c.returncode:raise RuntimeError('MEM branch helper build failed: '+c.stderr)
    r=subprocess.run([str(binary),str(trace)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('actual MEM branch differs: '+r.stderr)
    paths=[Path(__file__).resolve(),compiler,test,ROOT/'pipeline/frontend_branch.hpp',ROOT/'hardware/frontend_phase/build_branch.py',ROOT/'third_party/shuttle/src/main/scala/exu/Core.scala',ROOT/'build/rtl-verilator/gen-collateral/ShuttleCore.sv',run/'results.json',run/'phase.jsonl']
    report=dict(schema='iris.frontend.mem_branch_component.v1',status='passed_actual_MEM_branch_resolution',rows=count,stdout=r.stdout,commands=[argv],binary_sha256=sha(binary),trace_sha256=sha(trace),
                input_sha256={str(p):sha(p) for p in paths},source_scope='Core.scala69-75,690-748; saved40bit PC,39bit BTB address and6entry RAS.',
                scope='Source MEM resolution/selection/prediction correction from actual EX-provided taken/wdata and per-lane uops; EX condition comparison and frontend predictor are peers. Not live integration.',
                native_integration=False,calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(r.stdout.strip())
if __name__=='__main__':main()
