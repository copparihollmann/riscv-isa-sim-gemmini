#!/usr/bin/env python3
"""Bounded local-only exact-ELF numerical qualification on one nice CPU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from validate import validate

TEMPLATE = Path('/users/copparihollmann/iris-work/out/artifacts/probes/utilization-correction-v1/approved-operator-campaign-20261110-v1/corrected-boundary-matched168-20261111-v1/matched168/native-run.json')

def run(packet, limit=3600):
    manifest=json.loads((packet/'manifest.json').read_text())
    for p,h in manifest['input_sha256'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise ValueError('Changed source '+p)
    parent=json.loads(TEMPLATE.read_text()); argv=parent['argv']; argv[-1]=manifest['ELF']
    # argv is taskset -c 18 nice -n 10 /.../spike ...
    spike=next(Path(x) for x in argv if Path(x).name=='spike')
    if hashlib.sha256(spike.read_bytes()).hexdigest()!=parent['simulator_sha256']:raise ValueError('Simulator changed')
    owner=dict(pid=os.getpid(),proc_start=Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()[19],
        hardware_actions=False, CPU=18, nice=10, argv=argv, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (packet/'native-owner.json').write_text(json.dumps(owner,indent=2)+'\n')
    started=time.monotonic();timeout=False
    with (packet/'native.stdout').open('xb') as out,(packet/'native.stderr').open('xb') as err:
        proc=subprocess.Popen(argv,stdout=out,stderr=err)
        try:rc=proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timeout=True;proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
            rc=proc.returncode
    result=dict(argv=argv,returncode=rc,timed_out=timeout,host_seconds=time.monotonic()-started,
        hardware_actions=False, target_timing=False,ELF_sha256=manifest['ELF_sha256'],
        simulator_sha256=parent['simulator_sha256'], stdout_sha256=hashlib.sha256((packet/'native.stdout').read_bytes()).hexdigest(),
        stderr_sha256=hashlib.sha256((packet/'native.stderr').read_bytes()).hexdigest())
    try:
        if rc or timeout:raise ValueError('Native guest failed')
        report=validate((packet/'native.stdout').read_text(),packet)
        (packet/'native-admission.json').write_text(json.dumps(report,indent=2)+'\n');result.update(native_pass=True,regions=report['regions'])
    except Exception as exc:result.update(native_pass=False,error=repr(exc))
    (packet/'native-run.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--packet',type=Path,required=True);p.add_argument('--limit',type=int,default=3600);a=p.parse_args()
    r=run(a.packet.resolve(),a.limit);print(json.dumps(r));raise SystemExit(0 if r['native_pass'] else 1)
