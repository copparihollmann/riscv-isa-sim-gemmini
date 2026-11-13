#!/usr/bin/env python3
"""Check next-PC source priority at each observed frontend pre-state."""
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
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);run=ROOT/'build/frontend-phase-interface512-v4'
    receipt=json.loads((run/'results.json').read_text())
    if not receipt['full448B_signature_matches_unobserved']:raise ValueError('actual signature differs')
    trace=out/'actual-select.tsv';rows=0
    with (run/'phase.jsonl').open() as source,trace.open('w') as dest:
        for line in source:
            r=json.loads(line);b=r['before'];s=r['after']
            # Before the first actual reset, random queue pointers do not
            # have architectural meaning. All later source edges are used.
            if r['edge']==1:continue
            row=[b['tile_reset'],b['frontend_jump_reset'],b['fetch1_valid'],b['fetch2_valid'],b['fetch1_pc'],b['fetch2_pc'],b['fetch1_replay'],b['fetch2_replay'],
                 b['frontend_s2_ae'],b['frontend_s2_pf'],b['fetch2_tlb_miss'],b['cache_response_valid'],b['frontend_f1_target'],b['frontend_f2_target'],
                 b['redirect_flush'],b['flush_rrd'],b['fetch0_pc'],sum(b['fb_valid'+str(i)]<<i for i in range(7)),b['fb_enq_ptr'],b['fb_deq_ptr'],b['fb_enq_mask'],
                 b['fetch0_valid'],b['fetch0_pc'],b['frontend_s0_replay'],b['frontend_f1_clear'],b['fb_enq_valid'],s['fetch1_valid'],s['fetch2_valid']]
            dest.write(' '.join(map(str,row))+'\n');rows+=1
    compiler=Path(shutil.which('g++')).resolve();binary=out/'test_select';test=ROOT/'pipeline/test_frontend_select.cpp'
    argv=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror',str(test),'-o',str(binary)]
    b=subprocess.run(argv,text=True,capture_output=True);(out/'build.log').write_text(b.stdout+b.stderr)
    if b.returncode:raise RuntimeError('selector component build failed: '+b.stderr)
    r=subprocess.run([str(binary),str(trace)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source selector differential failed: '+r.stderr)
    paths=[Path(__file__).resolve(),compiler,test,ROOT/'pipeline/frontend_select.hpp',ROOT/'pipeline/frontend_queue.hpp',ROOT/'third_party/shuttle/src/main/scala/ifu/Frontend.scala',
           ROOT/'build/rtl-verilator/gen-collateral/ShuttleFrontend.sv',run/'results.json',run/'phase.jsonl']
    report=dict(schema='iris.frontend.selector_component.v1',status='passed_actual_source_frontend_select_differential',rows=rows,stdout=r.stdout,build_command=argv,binary_sha256=sha(binary),trace_sha256=sha(trace),
                input_sha256={str(p):sha(p) for p in paths},
                scope='Source next-PC/replay/clear/enqueue priority at every actual pre-state. Cache response, F1 prediction and F2 predecode target are explicit peer inputs; this is not a continuous full-frontend reconstruction.',
                redirect_pc_observation='Core redirect PC is the observed F0 PC only on the source flush path; this is a peer input, never used on other mux paths.',
                native_integration=False,timing_parameters={},calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(r.stdout.strip())
if __name__=='__main__':main()
