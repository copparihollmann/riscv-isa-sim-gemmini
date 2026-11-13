#!/usr/bin/env python3
"""Replay actual RTL cache transitions through the source-backed tag primitive."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/frontend-cache-component-v1');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    run=ROOT/'build/frontend-phase-clock512-v3';proof=ROOT/'build/frontend-phase-proof-512-v3/report.json';receipt=json.loads(proof.read_text())
    if receipt['status']!='passed_readonly_frontend_cache_diagnosis':raise ValueError('independent source proof not closed')
    qualified=set();rows=[]
    for line in (run/'phase.jsonl').open():
        r=json.loads(line);h=r['hart'];b=r['before'];a=r['after'];reset=bool(a['global_reset'])
        if h not in qualified:
            if not(reset and a['mc']==a['ir']==0 and a['cache_replacement_state']==1 and not a['cache_refill_valid'] and a['fb_deq_ptr']==1 and not any(a['fb_valid'+str(i)] for i in range(7))):continue
            qualified.add(h)
        request=a['cache_refill_address'] if not reset and not b['cache_refill_valid'] and a['cache_refill_valid'] else (1<<64)-1
        row=[h,int(reset),request,int(bool(b['cache_refill_beat']) and not reset),int(bool(b['flush_icache']) and not reset),b['cache_refill_address'],b['cache_replacement_state'],
             b['cache_index_valid0'],b['cache_index_tag0'],b['cache_index_valid1'],b['cache_index_tag1'],a['cache_refill_address'],a['cache_replacement_state'],
             a['cache_index_valid0'],a['cache_index_tag0'],a['cache_index_valid1'],a['cache_index_tag1']]
        rows.append(row)
    trace=out/'actual-rtl.tsv';trace.write_text(''.join(' '.join(map(str,row))+'\n' for row in rows))
    compiler=Path(shutil.which('g++')).resolve();binary=out/'test_cache'
    command=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror',str(ROOT/'pipeline/frontend_cache.cpp'),str(ROOT/'pipeline/test_frontend_cache.cpp'),'-o',str(binary)]
    build=subprocess.run(command,text=True,capture_output=True);(out/'build.log').write_text(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError('cache primitive build failed: '+build.stderr)
    def execute(name,path):
        run=subprocess.run([str(binary),str(path)],text=True,capture_output=True);(out/(name+'.stdout')).write_text(run.stdout);(out/(name+'.stderr')).write_text(run.stderr);return run
    normal=execute('actual',trace)
    if normal.returncode or 'PASS actual RTL cache' not in normal.stdout:raise RuntimeError('actual RTL differential failed: '+normal.stderr)
    # A valid wrong tag must fail. Uninitialized invalid tag RAM bits are
    # deliberately immaterial and must not become false functional state.
    changed=[list(row) for row in rows];index=next(i for i,row in enumerate(changed) if row[13]);changed[index][14]^=1
    bad=out/'wrong-valid-tag.tsv';bad.write_text(''.join(' '.join(map(str,row))+'\n' for row in changed));negative=execute('wrong-valid-tag',bad)
    if negative.returncode==0:raise RuntimeError('corrupt valid cache tag accepted')
    ignored=[list(row) for row in rows]
    for row in ignored:
        for valid,tag in ((7,8),(9,10),(13,14),(15,16)):
            if not row[valid]:row[tag]^=0x123456
    unknown=out/'arbitrary-invalid-tags.tsv';unknown.write_text(''.join(' '.join(map(str,row))+'\n' for row in ignored));allowed=execute('arbitrary-invalid-tags',unknown)
    if allowed.returncode:raise RuntimeError('uninitialized invalid tags affected model: '+allowed.stderr)
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/frontend_cache.hpp',ROOT/'pipeline/frontend_cache.cpp',ROOT/'pipeline/test_frontend_cache.cpp',proof,run/'results.json',compiler]
    report=dict(schema='iris.frontend.cache_component.v1',status='passed_source_cache_state_differential',source_sha256={str(p):sha(p) for p in inputs},
                input_trace_sha256=sha(trace),compiled_test_sha256=sha(binary),build_command=command,rows=len(rows),actual_refills=receipt['analysis']['completed_refills'],
                actual_stdout=normal.stdout,negative_valid_tag_rejected=True,arbitrary_invalid_tag_bits_ignored=True,
                source_counter_phase_qualified=False,timing_parameters={},native_integration=False,
                calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],rows=len(rows),refills=report['actual_refills'])))


if __name__=='__main__':main()
