#!/usr/bin/env python3
"""Run the five independent local Zephyr gates concurrently, with exact receipts.

Each child uses the unchanged per-case validator and its own process/files.
There are no FPGA operations or shared simulated machines in this harness.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
CASES=('scalar6','mixed9','rvv6','rvv6-vme-aware','vme4')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('native','uart','fixture','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--timeout',type=int,default=360)
    p.add_argument('--workers',type=int,default=5)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--input',type=Path,action='append',default=[])
    a=p.parse_args()
    if not 1<=a.workers<=5 or a.timeout<=0:p.error('Require1..5workers and positive per-case timeout')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    paths=[a.native.resolve(),a.uart.resolve(),a.fixture.resolve(),Path(__file__).resolve(),
           Path(__file__).with_name('empirical_os_validate.py'),*[f.resolve() for f in a.input]]
    inputs={str(f):sha(f) for f in paths}
    prepared={'schema':'iris.empirical_parallel_Zephyr_preparation.v1','cases':CASES,'workers':a.workers,
        'seed':a.seed,'per_case_timeout_seconds':a.timeout,'input_sha256':inputs,'hardware_contacted':False}
    (out/'prepared.json').write_text(json.dumps(prepared,indent=2)+'\n')
    started=time.monotonic()

    def execute(name):
        group=out/name;group.mkdir()
        argv=[sys.executable,str(ROOT/'zephyr/empirical_os_validate.py'),'--binary',str(a.native.resolve()),
            '--uart',str(a.uart.resolve()),'--output',str(group/'run'),'--case',name,'--seed',str(a.seed),
            '--timeout',str(a.timeout),'--engine-arg=--iris-timing-fixture='+str(a.fixture.resolve()),
            '--engine-arg=--iris-timing-trace={graph}','--input',str(a.fixture.resolve())]
        for path in a.input:argv+=['--input',str(path.resolve())]
        with (group/'driver.stdout').open('w') as stdout,(group/'driver.stderr').open('w') as stderr:
            child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
            (group/'invocation.json').write_text(json.dumps({'argv':argv,'pid':child.pid},indent=2)+'\n')
            timed=False
            try:code=child.wait(timeout=a.timeout+60)
            except subprocess.TimeoutExpired:
                timed=True;os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
                code=child.returncode
        path=group/'run/report.json'
        if not path.is_file():
            return {'name':name,'pass':False,'error':'Per-case harness did not produce a receipt',
                    'harness_exit_status':code,'harness_timed_out':timed},{}
        report=json.loads(path.read_text())
        if len(report['runs'])!=1 or report['runs'][0]['name']!=name:raise ValueError('Wrong actual childcase receipt')
        row=report['runs'][0]
        if row['pass']!=(code==0 and not timed and report['pass']):raise ValueError('Child harness/pass outcome mismatch')
        row=dict(row,child_receipt=str(path),child_receipt_sha256=sha(path),
                 harness_exit_status=code,harness_timed_out=timed)
        return row,report['input_sha256']

    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        results=list(pool.map(execute,CASES))
    rows=[]
    for row,child_inputs in results:
        rows.append(row)
        for path,digest in child_inputs.items():
            if path in inputs and inputs[path]!=digest:raise ValueError('Mixed input epochs in parallel gate receipts')
            inputs[path]=digest
    if any(sha(path)!=digest for path,digest in inputs.items()):raise ValueError('Execution inputs changed during QA')
    report={'schema':'iris.fast_model_actual_Zephyr_SMP_validation.v1','pass':all(r['pass'] for r in rows),
        'runs':rows,'native_sha256':sha(a.native),'UART_sha256':sha(a.uart),'fixture_sha256':sha(a.fixture),
        'seed':a.seed,'input_sha256':inputs,'parallel_workers':a.workers,'host_seconds':time.monotonic()-started,
        'hardware_contacted':False,'timing_kind':'experimental-empirical','timing_certified':False,
        'scope':'Five actual independent three-hart OS executions with original validators; no FPGA timing qualification.'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':report['pass'],'gates':len(rows),'host_seconds':report['host_seconds'],
                      'report_sha256':sha(out/'report.json')}))
    if not report['pass']:raise SystemExit(1)


if __name__=='__main__':main()
