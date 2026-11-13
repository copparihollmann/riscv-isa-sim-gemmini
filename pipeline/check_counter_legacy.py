#!/usr/bin/env python3
"""Require both previously frozen pipeline modes to preserve893 behavior."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/counter-pipeline-v1-legacy')
    p.add_argument('--build',type=Path,default=ROOT/'build/spike-counter-pipeline-v1')
    p.add_argument('--parent',type=Path,default=ROOT/'build/counter-policy-frozen-8930257d')
    p.add_argument('--counter-mode',action='store_true');a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=True,parents=True);(out/'results.json').write_text('{"status":"in_progress"}\n')
    build=a.build.resolve();parent=a.parent.resolve();identity=json.loads((parent/'manifest.json').read_text())
    if sha(parent/'spike')!=identity['binary_sha256'] or sha(parent/'libsifive_uart.so')!=identity['uart_sha256']:raise RuntimeError('frozen parent changed')
    elf=ROOT/'build/counter-policy-v2-nonlinear/counter.elf';env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);results=[]
    modes=['pure-integer-sequential-frontend','pure-integer-rvc-sequential-frontend']
    if a.counter_mode:modes.append('pure-integer-rvc-counter-sequential-frontend')
    for mode in modes:
        fixture=out/(mode+'.fixture');fixture.write_text((ROOT/'pipeline/rvc.fixture').read_text().replace('pure-integer-rvc-sequential-frontend',mode))
        actual=[]
        for label,model in [('parent',parent),('candidate',build)]:
            graph=out/(mode+'-'+label+'.json');argv=command(model/'spike',elf);argv=['--extlib='+str(model/'libsifive_uart.so') if x.startswith('--extlib=') else x for x in argv]
            argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graph)]
            r=subprocess.run(argv,text=True,capture_output=True,env=env,timeout=90);stem=mode+'-'+label
            (out/(stem+'.stdout')).write_text(r.stdout);(out/(stem+'.stderr')).write_text(r.stderr)
            if r.returncode or 'COUNTER_OBSERVE_DONE 0' not in r.stdout:raise RuntimeError('legacy nonlinear guest failed')
            d=json.loads(graph.read_text());actual.append((r.stdout,r.stderr,d['cycles'],d['retired_instructions'],d['counter_read_observations']))
            results.append(dict(mode=mode,model=label,argv=argv,elf_sha256=sha(elf),fixture_sha256=sha(fixture),graph_sha256=sha(graph),
                                stdout_sha256=sha(out/(stem+'.stdout')),stderr_sha256=sha(out/(stem+'.stderr')),pass_=True))
        if actual[0]!=actual[1]:raise RuntimeError('prior pipeline mode/counter semantics changed')
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/rvc.fixture',elf,parent/'manifest.json',ROOT/'spike/run_functional.py']
    report=dict(schema='iris.shuttle.counter_legacy.v1',status='passed_exact_legacy_counter_modes',binary_sha256=sha(build/'spike'),uart_sha256=sha(build/'libsifive_uart.so'),
                parent_binary_sha256=identity['binary_sha256'],results=results,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},
                exact_observations_and_guest_text=True,calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],modes=len(modes))))


if __name__=='__main__':main()
