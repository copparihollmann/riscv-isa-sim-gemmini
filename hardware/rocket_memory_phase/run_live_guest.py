#!/usr/bin/env python3
"""Independent saved whole-CPU oracle for the live native scalar-memory guest."""
import argparse
import gzip
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
    p=argparse.ArgumentParser(__doc__);p.add_argument('--elf',type=Path,required=True);p.add_argument('--guest-receipt',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);elf=a.elf.resolve();guest_receipt=a.guest_receipt.resolve();observer=ROOT/'build/rocket-memory-phase-observer-v1';binary=observer/'simulator-rocket-memory-phase';build=json.loads((observer/'build.json').read_text())
    if sha(binary)!=build['binary_sha256']:raise ValueError('frozen whole-CPU observer binary changed')
    for path,digest in build['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('independent whole-CPU input changed: '+path)
    guest=json.loads(guest_receipt.read_text())
    if guest.get('guest_completion_pass')is not True or sha(elf)!=guest['input_sha256'][str(elf)]:raise ValueError('source guest identity or prior numerical success missing')
    shutil.copy2(elf,out/'load.elf');trace=out/'memory-phase.jsonl.gz';argv=[str(binary),'+permissive','+verilator+seed+1','+verilator+rand+reset+2','+loadmem=1','+noc_util_sample_rate=0','+max-cycles=300000','+init_write=0x2000004:0x1','+init_write=0x2000008:0x1','+permissive-off',str(out/'load.elf')];start=time.perf_counter();timed=False
    with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
        try:r=subprocess.run(argv,cwd=ROOT,env=dict(os.environ,IRIS_ROCKET_MEMORY_PHASE=str(trace)),stdout=stdout,stderr=stderr,timeout=240);code=r.returncode
        except subprocess.TimeoutExpired:code=None;timed=True
    rows=[]
    if trace.exists():
        with gzip.open(trace,'rt')as f:rows=[json.loads(line)for line in f]
    # No RTL timing numbers are fed to the native candidate or its fixture.
    # This independent reference establishes completed guest checks and actual
    # load-retirement/late-RF ordering, not whole-path timing agreement.
    nm=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm');symbols={}
    for line in subprocess.check_output([str(nm),str(elf)],text=True).splitlines():
        fields=line.split()
        if len(fields)>=3:
            try:symbols[fields[2]]=int(fields[0],16)
            except ValueError:pass
    pending=None;witnesses=[]
    for row in rows:
        before=row['before'];after=row['after']
        if before['wb_valid']and before['wb_pc']==symbols['source_load_rom']and before['retire']:
            if before['core_dresp_valid']:continue
            pending=dict(retire_edge=row['edge'],instret_before=before['instret'],instret_after=after['instret'])
        if pending and before['ll_wen']and before['ll_waddr']==11:
            witnesses.append(dict(**pending,data_edge=row['edge'],other_retired_before_data=(before['instret']-pending['instret_after'])&((1<<64)-1),returned_value=before['rf_wdata'],written_value=after['rf'][11]));pending=None
    passed=code==0 and not timed and any(w['data_edge']>w['retire_edge']and w['other_retired_before_data']>=1 and w['returned_value']==w['written_value']for w in witnesses)
    report=dict(schema='iris.rocket.live_guest_whole_CPU_oracle.v1',status='passed_independent_whole_CPU_guest_and_early_retire'if passed else'preserved_failed_whole_CPU_live_guest_attempt',argv=argv,exit_status=code,timed_out=timed,host_seconds=time.perf_counter()-start,observer_binary_sha256=sha(binary),elf_sha256=sha(elf),guest_receipt_sha256=sha(guest_receipt),trace_sha256=sha(trace)if trace.exists()else None,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),witnesses=witnesses,input_sha256={str(Path(__file__).resolve()):sha(__file__),str(observer/'build.json'):sha(observer/'build.json'),str(nm):sha(nm)},source_FIR_sha256='f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4',RTL_logic_modified=False,observed_internal_state_injected=False,hardware_contacted=False,timing_certified=False,loaded_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],exit_status=code,host_seconds=report['host_seconds'],witnesses=witnesses)));raise SystemExit(0if passed else 1)
if __name__=='__main__':main()
