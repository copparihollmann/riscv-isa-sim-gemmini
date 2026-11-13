#!/usr/bin/env python3
"""Check owned cancellation semantics and preserve existing engine output bytes."""
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
    compiler=Path(shutil.which('g++')).resolve();commands=[]
    def build(name,files,include):
        binary=out/name;argv=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror','-I'+str(include),*[str(p)for p in files],'-o',str(binary)];commands.append(argv)
        r=subprocess.run(argv,text=True,capture_output=True);(out/(name+'.build.log')).write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('owned engine build failed: '+r.stderr)
        return binary
    cancel=build('cancel',[ROOT/'pipeline/frontend_engine.cpp',ROOT/'pipeline/test_frontend_engine.cpp'],ROOT/'pipeline')
    r=subprocess.run([str(cancel),str(out/'graph.json')],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source stage cancellation failed: '+r.stderr)
    data=json.loads((out/'graph.json').read_text());events=data['events'];canceled=[n for n in events if n.get('cancelled')]
    if len(canceled)!=3 or data['partial'] or data['pending_operations']:raise ValueError('cancellation graph finality contract differs')
    for node in canceled:
        if node['completed'] or node['end']!=node['cancel_cycle'] or not node['cancel_reason'] or (not node['issued'] and node['start']!=node['end']):raise ValueError('invalid canceled span')
    reference=build('reference',[ROOT/'timing/iris_timing.cpp',ROOT/'timing/test_timing.cpp'],ROOT/'timing')
    local=out/'test_legacy.cpp';local.write_text((ROOT/'timing/test_timing.cpp').read_text().replace('#include "iris_timing.hpp"','#include "frontend_engine.hpp"'))
    candidate=build('candidate',[ROOT/'pipeline/frontend_engine.cpp',local],ROOT/'pipeline')
    before=subprocess.run([str(reference),'json'],text=True,capture_output=True);after=subprocess.run([str(candidate),'json'],text=True,capture_output=True)
    (out/'legacy-reference.json').write_text(before.stdout);(out/'legacy-candidate.json').write_text(after.stdout)
    if before.returncode or after.returncode or before.stdout!=after.stdout or before.stderr!=after.stderr:raise ValueError('no-cancel engine semantics/serialized bytes changed')
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/frontend_engine.hpp',ROOT/'pipeline/frontend_engine.cpp',ROOT/'pipeline/test_frontend_engine.cpp',ROOT/'timing/iris_timing.hpp',ROOT/'timing/iris_timing.cpp',ROOT/'timing/test_timing.cpp',compiler]
    report=dict(schema='iris.frontend.owned_engine_cancel.v1',status='passed_owned_source_stage_cancellation',cancelled_pending_and_inflight=len(canceled),same_edge_cancel_before_callback=True,accepted_memory_actor_uncancellable=True,
                completed_wrongpath_work_preserved=True,no_cancel_legacy_json_byte_identical=True,commands=commands,input_sha256={str(p):sha(p) for p in inputs},
                graph_sha256=sha(out/'graph.json'),legacy_graph_sha256=sha(out/'legacy-reference.json'),stdout=r.stdout,primary_engine_modified=False,native_integration=False,calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],cancelled=len(canceled))))
if __name__=='__main__':main()
