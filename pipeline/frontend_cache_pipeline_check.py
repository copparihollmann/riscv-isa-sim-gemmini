#!/usr/bin/env python3
"""Drive source cache FSM continuously using only actual interface inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    run=ROOT/'build/frontend-phase-interface512-v4';receipt=json.loads((run/'results.json').read_text())
    if not(receipt['status']=='passed_readonly_frontend_signature_requires_analysis' and receipt['full448B_signature_matches_unobserved']):raise ValueError('observer functional signature refused')
    fields=['cache_s0_fire','cache_response_valid','cache_s2_miss','cache_refill_request','cache_refill_address']
    after=['cache_s1_valid','cache_s2_valid','cache_s2_hit','frontend_can_request_reg','cache_refill_valid','cache_replacement_state','cache_refill_address','cache_refill_done']
    qualified=set();count=0
    trace=out/'actual-interface.tsv'
    with trace.open('w') as dest,(run/'phase.jsonl').open() as source:
        for line in source:
            r=json.loads(line);b=r['before'];s=r['after'];h=r['hart']
            if h not in qualified:
                if not b['tile_reset']:continue
                qualified.add(h)
            row=[h,r['edge'],b['tile_reset'],b['fetch0_valid'],b['fetch0_pc'],b['cache_s1_paddr'],int(bool(b['frontend_tlb_miss'] or b['frontend_f1_clear'])),
                 int(bool(b['fetch2_valid'] and (b['frontend_s2_ae'] or b['frontend_s2_pf']) and not b['fetch2_replay'])),b['flush_icache'],b['cache_a_ready'],b['cache_refill_beat']]
            row += [b[k] for k in fields]+[s[k] for k in after]
            dest.write(' '.join(map(str,row))+'\n');count+=1
    compiler=Path(shutil.which('g++')).resolve();binary=out/'test_cache_pipeline'
    names=['frontend_cache.cpp','frontend_cache_pipeline.cpp','test_frontend_cache_pipeline.cpp']
    argv=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror',*[str(ROOT/'pipeline'/n) for n in names],'-o',str(binary)]
    b=subprocess.run(argv,text=True,capture_output=True);(out/'build.log').write_text(b.stdout+b.stderr)
    if b.returncode:raise RuntimeError('component build failed: '+b.stderr)
    r=subprocess.run([str(binary),str(trace)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('continuous cache pipeline differs: '+r.stderr)
    inputs=[Path(__file__).resolve(),compiler,run/'results.json',run/'phase.jsonl',ROOT/'hardware/frontend_phase/build_interface.py',ROOT/'third_party/shuttle/src/main/scala/ifu/ICache.scala',
            ROOT/'build/rtl-verilator/gen-collateral/ShuttleICache.sv',*[ROOT/'pipeline'/n for n in names],ROOT/'pipeline/frontend_cache.hpp',ROOT/'pipeline/frontend_cache_pipeline.hpp']
    for negative,field in [('request',14),('hit',18),('edge',1)]:
        path=out/(negative+'-corruption.tsv');changed=False
        with trace.open() as source,path.open('w') as dest:
            for line in source:
                row=list(map(int,line.split()))
                if not changed and not row[2] and ((negative=='request' and row[14]) or (negative=='hit' and row[17]) or (negative=='edge' and row[1]>1000)):
                    row[field]^=1;changed=True
                dest.write(' '.join(map(str,row))+'\n')
        if not changed:raise ValueError('negative corpus had no witness')
        n=subprocess.run([str(binary),str(path)],text=True,capture_output=True);(out/(negative+'-corruption.stderr')).write_text(n.stderr)
        if n.returncode==0:raise ValueError('corruption silently accepted: '+negative)
    report=dict(schema='iris.frontend.cache_pipeline_component.v1',status='passed_continuous_source_cache_pipeline_differential',rows=count,
                inputs_sha256={str(p):sha(p) for p in inputs},build_command=argv,compiled_test_sha256=sha(binary),input_trace_sha256=sha(trace),stdout=r.stdout,
                actual_interface_inputs=['S0 valid/vaddr','S1 translated physical address','S1 translation/clear kill','S2 instruction exception kill','invalidate','TileLink A ready','TileLink D data-beat fire','actual tile reset'],
                computed_outputs=['S0 request fire','s1/s2 valid','s2 hit when valid','response valid','miss','refill request valid/address','can-request history','refill-active state','replacement RNG'],
                internal_state_injected=False,reset_only_initialization=True,negative_corruptions_rejected=3,source_read_phase='pre-edge computation; source edge updates; post-edge state check',
                native_integration=False,timing_parameters={},calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],rows=count)))
if __name__=='__main__':main()
