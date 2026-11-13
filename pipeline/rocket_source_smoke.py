#!/usr/bin/env python3
"""Preserve actual source-frontend integration attempts, including failures."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-rocket-source-v1/spike');p.add_argument('--elf',type=Path,default=ROOT/'build/frontend-live-source-control-v4/control.elf');p.add_argument('--fixture',type=Path,default=ROOT/'pipeline/rocket-source-synthetic.fixture');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    binary=a.binary.resolve();uart=binary.with_name('libsifive_uart.so');elf=a.elf.resolve();fixture=a.fixture.resolve()
    inputs=[Path(__file__).resolve(),ROOT/'spike/run_functional.py',binary,uart,elf,fixture,ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',binary.with_name('pipeline-build.json')]
    retained=out/'native-inputs';retained.mkdir()
    for name in ('spike','libsifive_uart.so','pipeline-build.json'):shutil.copy2(binary.with_name(name),retained/name)
    receipt=json.loads(binary.with_name('pipeline-build.json').read_text())
    overlay=subprocess.check_output(['git','-C',receipt['source'],'diff','--binary','HEAD'])
    if hashlib.sha256(overlay).hexdigest()!=receipt['source_overlay_sha256']:raise ValueError('native source overlay changed')
    (retained/'source-overlay.patch').write_bytes(overlay)
    shutil.copy2(Path(__file__).resolve(),retained/'runner.py')
    hashes={str(p):sha(p)for p in inputs};argv=command(binary,elf);argv=['--extlib='+str(uart)if x.startswith('--extlib=')else x for x in argv]
    argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(out/'graph.json')]
    start=time.perf_counter();timed_out=False
    try:r=subprocess.run(argv,text=True,capture_output=True,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']),timeout=90)
    except subprocess.TimeoutExpired as e:r=subprocess.CompletedProcess(argv,None,(e.stdout or b'').decode()if isinstance(e.stdout,bytes)else e.stdout or '',(e.stderr or b'').decode()if isinstance(e.stderr,bytes)else e.stderr or '');timed_out=True
    (out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if hashes!={str(p):sha(p)for p in inputs}:raise ValueError('native/source inputs changed during run')
    report=dict(schema='iris.rocket.source_frontend_smoke.v1',status='guest_exit_zero'if r.returncode==0 else 'preserved_failed_integration_attempt',exit_status=r.returncode,timed_out=timed_out,host_seconds=time.perf_counter()-start,input_sha256=hashes,argv=argv,binary_sha256=hashes[str(binary)],uart_sha256=hashes[str(uart)],stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));print(r.stdout[-1500:]);print(r.stderr[-2500:])
if __name__=='__main__':main()
