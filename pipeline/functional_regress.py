#!/usr/bin/env python3
"""Replay the frozen32-case ordinary functional contract on an isolated model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.run_functional import symbols
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--binary',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next/spike')
    parser.add_argument('--uart',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next/libsifive_uart.so')
    parser.add_argument('--provenance',type=Path,default=ROOT/'build/snapshot-5e6cc309/provenance.json')
    parser.add_argument('--output',type=Path,default=ROOT/'build/pipeline-rvc-functional32')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
    (out/'results.json').write_text('{"status":"in_progress","calibrated":false}\n')
    binary=args.binary.resolve();uart=args.uart.resolve();initial=(sha(binary),sha(uart));baseline=json.loads(args.provenance.read_text())
    cases=baseline['selftest']['guest_results']
    if len(cases)!=32 or any(c['pass'] is not True for c in cases):raise RuntimeError('frozen32-case expectation missing')
    results=[]
    for row in cases:
        name=row['name'];argv=list(row['argv']);reference=name.endswith('-reference')
        if reference:
            if sha(argv[0])!=baseline['reference_binary_sha256']:raise RuntimeError('reference binary changed')
        else:
            argv[0]=str(binary)
            argv=['--extlib='+str(uart) if a.startswith('--extlib=') else a for a in argv]
        if sha(argv[-1])!=row['elf_sha256']:raise RuntimeError('guest ELF changed: '+name)
        if any(a.startswith('--iris-timing-fixture') for a in argv):raise RuntimeError('functional corpus unexpectedly enabled timing')
        env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
        env.pop('IRIS_FATAL_PCS',None);env.pop('IRIS_UART_RX_FRAMES',None)
        if name=='fatal-entry':env['IRIS_FATAL_PCS']=hex(symbols(argv[-1])['_start'])
        start=time.perf_counter();p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=120);elapsed=time.perf_counter()-start
        stdout,stderr=out/(name+'.stdout'),out/(name+'.stderr');stdout.write_text(p.stdout);stderr.write_text(p.stderr)
        result=dict(name=name,argv=argv,exit_status=p.returncode,expected_exit_status=row['expected_exit_status'],
                    binary_sha256=sha(argv[0]),elf_sha256=sha(argv[-1]),stdout_sha256=sha(stdout),stderr_sha256=sha(stderr),
                    reference_case=reference,host_seconds=elapsed,expected_stdout_sha256=row['stdout_sha256'],
                    expected_stderr_sha256=row['stderr_sha256'])
        result['pass']=p.returncode==row['expected_exit_status'] and sha(stdout)==row['stdout_sha256'] and sha(stderr)==row['stderr_sha256']
        results.append(result)
        if not result['pass']:
            (out/'failed-case.json').write_text(json.dumps(result,indent=2)+'\n')
            raise RuntimeError('ordinary functional output/status changed: '+name)
    if (sha(binary),sha(uart))!=initial:raise RuntimeError('binary/plugin changed while running')
    report=dict(schema='iris.shuttle.functional_regression.v1',status='passed_frozen32_functional_contract',
                binary_sha256=initial[0],uart_sha256=initial[1],baseline_provenance_sha256=sha(args.provenance),
                source_sha256={str(Path(__file__).relative_to(ROOT)):sha(__file__),
                               'spike/run_functional.py':sha(ROOT/'spike/run_functional.py')},
                results=results,calibrated=False,rtl_certified=False,
                scope='Exact stdout/stderr/status regression of frozen32 ordinary functional cases, including unchanged upstream reference executions; no whole-SoC functional or timing certificate.')
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],cases=len(results),receipt=str(out/'results.json'))))


if __name__=='__main__':main()
