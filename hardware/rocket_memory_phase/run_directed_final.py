#!/usr/bin/env python3
"""Replay positive native-memory guests independently on frozen whole RTL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--guest-receipt',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();receipt=a.guest_receipt.resolve();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);guest=json.loads(receipt.read_text());observer=ROOT/'build/rocket-memory-phase-observer-v1';binary=observer/'simulator-rocket-memory-phase';build=json.loads((observer/'build.json').read_text())
    if not guest['status'].startswith('passed')or sha(binary)!=build['binary_sha256']:raise ValueError('native corpus/frozen observer identity missing')
    for path,digest in build['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('frozen whole-CPU input changed')
    rows=[]
    for original in guest['rows']:
        if original['expected_diagnostic']:continue
        elf=Path(original['argv'][-1]);folder=out/original['name'];folder.mkdir()
        if sha(elf)!=original['elf_sha256']:raise ValueError('exact positive guest changed')
        shutil.copy2(elf,folder/'guest.elf');trace=folder/'memory-phase.jsonl.gz';argv=[str(binary),'+permissive','+verilator+seed+1','+verilator+rand+reset+2','+loadmem=1','+noc_util_sample_rate=0','+max-cycles=300000','+init_write=0x2000004:0x1','+init_write=0x2000008:0x1','+permissive-off',str(folder/'guest.elf')];start=time.perf_counter();timed=False
        with(folder/'stdout').open('wb')as stdout,(folder/'stderr').open('wb')as stderr:
            try:r=subprocess.run(argv,cwd=ROOT,env=dict(os.environ,IRIS_ROCKET_MEMORY_PHASE=str(trace)),stdout=stdout,stderr=stderr,timeout=240);code=r.returncode
            except subprocess.TimeoutExpired:code=None;timed=True
        row=dict(name=original['name'],argv=argv,exit_status=code,timed_out=timed,pass_=code==0 and not timed,host_seconds=time.perf_counter()-start,elf_sha256=sha(elf),trace_sha256=sha(trace)if trace.exists()else None,stdout_sha256=sha(folder/'stdout'),stderr_sha256=sha(folder/'stderr'));rows.append(row);print(json.dumps(row),flush=True)
    passed=len(rows)==sum(not r['expected_diagnostic'] for r in guest['rows']) and bool(rows) and all(r['pass_']for r in rows);report=dict(schema='iris.rocket.directed_memory_whole_CPU_oracle.v1',status='passed_independent_whole_CPU_directed_goldens'if passed else'preserved_failed_whole_CPU_directed_attempt',input_sha256={str(Path(__file__).resolve()):sha(__file__),str(receipt):sha(receipt),str(observer/'build.json'):sha(observer/'build.json')},observer_binary_sha256=sha(binary),rows=rows,source_FIR_sha256='f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4',RTL_logic_modified=False,observed_internal_state_injected=False,hardware_contacted=False,timing_certified=False,loaded_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0if passed else 1)
if __name__=='__main__':main()
