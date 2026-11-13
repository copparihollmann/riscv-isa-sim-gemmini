#!/usr/bin/env python3
"""Qualify a newly built buffered fitting ELF, without timing or FPGA claims."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from validate import validate

ROOT=Path(__file__).resolve().parents[2]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=0)
    p.add_argument('--timeout',type=float,default=600)
    p.add_argument('--native',type=Path,default=ROOT/'build/combined-frozen-35901887/spike')
    p.add_argument('--uart',type=Path,default=ROOT/'build/combined-frozen-35901887/libsifive_uart.so')
    a=p.parse_args();build=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((build/'build.json').read_text());corpus=json.loads((build/'corpus.json').read_text())
    if sha(build/'campaign.elf')!=receipt['elf_sha256']:raise ValueError('Changed ELF')
    for path,digest in receipt['input_sha256'].items():
        if sha(path)!=digest or sha(build/'inputs'/digest)!=digest:raise ValueError('Changed build input '+path)
    rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb'
    dma='rv64gcv_zfh_zvfh_zvl256b_zvbb'
    compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
    argv=[str(a.native.resolve()),'--iris-vme','--isa='+dma,'--hart-isa=0:'+compute,'--hart-isa=1:'+compute,
        '--hart-isa=2:'+dma,'-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
        '--extlib='+str(a.uart.resolve()),'--device=sifive_uart,0x10020000','--iris-bootrom='+str(rom),
        '--dtb='+str(dtb),'--iris-schedule-seed='+str(a.seed),str(build/'campaign.elf')]
    paths=[a.native.resolve(),a.uart.resolve(),rom,dtb,build/'campaign.elf',build/'corpus.json',build/'build.json',
           Path(__file__).resolve(),Path(__file__).with_name('validate.py')]
    inputs={str(f):sha(f) for f in paths}
    r={'schema':'iris.buffered_campaign_functional_run.v1','status':'running','argv':argv,'seed':a.seed,
       'input_sha256':inputs,'hardware_contacted':False,'timing_certified':False}
    (out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
    started=time.monotonic()
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ.get('PATH',''))
    env.pop('IRIS_EMPIRICAL_FEATURES',None);env.pop('IRIS_FATAL_PCS',None)
    with (out/'run.stdout').open('w') as stdout,(out/'run.stderr').open('w') as stderr:
        child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,start_new_session=True)
        r['pid']=child.pid;(out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
        try:r['exit_status']=child.wait(timeout=a.timeout)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            r.update(exit_status=child.returncode,timed_out=True)
    r.update(host_seconds=time.monotonic()-started,stdout_sha256=sha(out/'run.stdout'),stderr_sha256=sha(out/'run.stderr'))
    try:
        if r['exit_status']!=0:raise ValueError('Guest exit '+str(r['exit_status']))
        r.update(validate((out/'run.stdout').read_text(),corpus))
        for path,digest in {**receipt['input_sha256'],**inputs}.items():
            if sha(path)!=digest:raise ValueError('Execution input changed '+path)
        r['status']='passed'
    except (ValueError,KeyError,TypeError) as error:r.update(status='failed',functional_checks_passed=False,error=str(error))
    (out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ('status','exit_status','host_seconds')}))
    if r['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
