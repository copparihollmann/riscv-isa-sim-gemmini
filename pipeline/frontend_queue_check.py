#!/usr/bin/env python3
"""Check FIFO state transitions against actual pre/post whole-RTL observations."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/frontend-queue-component-v1');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    run=ROOT/'build/frontend-phase-clock512-v3';rows=[];qualified=set()
    for line in (run/'phase.jsonl').open():
        r=json.loads(line);b=r['before'];s=r['after'];h=r['hart'];reset=bool(s['global_reset'])
        if h not in qualified:
            if not(reset and s['mc']==s['ir']==0 and s['cache_replacement_state']==1 and not s['cache_refill_valid'] and s['fb_deq_ptr']==1 and not any(s['fb_valid'+str(i)] for i in range(7))):continue
            qualified.add(h)
        before=sum(b['fb_valid'+str(i)]<<i for i in range(7));after=sum(s['fb_valid'+str(i)]<<i for i in range(7))
        rows.append([int(reset),b['redirect_flush'],b['fb_enq_valid'],b['fb_enq_mask'],int(not b['rrd0_stall']),int(not b['rrd1_stall']),
                     before,b['fb_enq_ptr'],b['fb_deq_ptr'],after,s['fb_enq_ptr'],s['fb_deq_ptr']])
    trace=out/'actual-queue.tsv';trace.write_text(''.join(' '.join(map(str,r))+'\n' for r in rows))
    compiler=Path(shutil.which('g++')).resolve();binary=out/'test_queue';command=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror',str(ROOT/'pipeline/test_frontend_queue.cpp'),'-o',str(binary)]
    b=subprocess.run(command,text=True,capture_output=True);(out/'build.log').write_text(b.stdout+b.stderr)
    if b.returncode:raise RuntimeError('queue component compile failed: '+b.stderr)
    r=subprocess.run([str(binary),str(trace)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('actual source queue transition mismatch: '+r.stderr)
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/frontend_queue.hpp',ROOT/'pipeline/test_frontend_queue.cpp',ROOT/'third_party/shuttle/src/main/scala/ifu/FetchBuffer.scala',
            ROOT/'build/frontend-phase-proof-512-v3/report.json',run/'results.json',compiler]
    report=dict(schema='iris.frontend.queue_component.v1',status='passed_source_queue_state_differential',rows=len(rows),source_sha256={str(p):sha(p) for p in inputs},
                build_command=command,compiled_test_sha256=sha(binary),input_trace_sha256=sha(trace),stdout=r.stdout,
                verification='Each observed pre-state independently supplied; no claim that unobserved queue activity was reconstructed.',
                native_integration=False,timing_parameters={},calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],rows=len(rows))))


if __name__=='__main__':main()
