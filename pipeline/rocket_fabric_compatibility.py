#!/usr/bin/env python3
"""Replay exact frozen functional guests on a new isolated fabric epoch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-rocket-fabric-v1/spike');p.add_argument('--receipt',type=Path,default=ROOT/'build/rocket-source-functional32-v3/results.json');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=a.binary.resolve();plugin=binary.with_name('libsifive_uart.so');receipt=a.receipt.resolve();old=json.loads(receipt.read_text());before=sha(binary),sha(plugin);rows=[]
    for original in old['rows']:
        name=original['name'];argv=[str(binary),*['--extlib='+str(plugin)if x.startswith('--extlib=')else x for x in original['argv'][1:]]]
        if sha(argv[-1])!=original['elf_sha256']:raise ValueError('frozen guest changed')
        env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);env.update(original.get('environment',{}));start=time.perf_counter();r=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=180);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        stdout_hash=sha(out/(name+'.stdout'));passed=r.returncode==original['expected_exit_status']and stdout_hash==original['stdout_sha256']and all(line in r.stderr for line in original.get('expected_diagnostics',[]))
        rows.append(dict(name=name,argv=argv,elf_sha256=original['elf_sha256'],exit_status=r.returncode,expected_exit_status=original['expected_exit_status'],stdout_sha256=stdout_hash,qualified_parent_stdout_sha256=original['stdout_sha256'],stderr_sha256=sha(out/(name+'.stderr')),expected_diagnostics=original.get('expected_diagnostics',[]),pass_=passed,host_seconds=time.perf_counter()-start));print(name,passed,flush=True)
    if before!=(sha(binary),sha(plugin)):raise ValueError('paired native changed during compatibility checks')
    report=dict(schema='iris.rocket.fabric_parent_compatibility.v1',status='passed_frozen_functional32_exact_stdout'if all(r['pass_']for r in rows)else'failed_parent_compatibility',binary_sha256=before[0],uart_sha256=before[1],input_sha256={str(receipt):sha(receipt),str(Path(__file__).resolve()):sha(__file__)},rows=rows,native_device_abi=4,calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0if report['status'].startswith('passed')else 1)
if __name__=='__main__':main()
