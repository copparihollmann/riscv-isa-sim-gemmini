#!/usr/bin/env python3
"""Validate the exact memory-route ELF on all three functional harts, not RTL timing."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from build import sha, ROOT

spec=importlib.util.spec_from_file_location('memory_console_validator',ROOT/'benchmarks/v2/validate.py')
validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
DMA='rv64gcv_zfh_zvfh_zvl256b_zvbb'
COMPUTE='rv64gcv_zfh_zvfh_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True)
    p.add_argument('--binary',type=Path,default=ROOT/'spike/bin/spike-iris-functional')
    p.add_argument('--uart',type=Path,default=ROOT/'spike/bin/libsifive_uart.so')
    p.add_argument('--dtc',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/bin/dtc'))
    p.add_argument('--seed',type=int,default=0);p.add_argument('--timeout',type=int,default=180)
    a=p.parse_args();out=a.build.resolve()
    if (out/'run.json').exists():raise RuntimeError('preserve previous run; use a fresh build directory')
    build=json.loads((out/'build.json').read_text());elf=out/'memory-routes.elf';corpus=json.loads((out/'corpus.json').read_text())
    if sha(elf)!=build['elf_sha256']:raise ValueError('changed ELF')
    for path,digest in build['input_sha256'].items():
        if sha(Path(path))!=digest or sha(out/'inputs'/digest)!=digest:raise ValueError('changed input '+path)
    for path,digest in corpus['v1_frozen_input_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('changed frozen baseline/heldout '+path)
    command=[str(a.binary.resolve()),'--iris-vme','--isa='+DMA,'--hart-isa=0:'+COMPUTE,'--hart-isa=1:'+COMPUTE,'--hart-isa=2:'+DMA,
             '-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
             '--extlib='+str(a.uart.resolve()),'--device=sifive_uart,0x10020000',f'--iris-schedule-seed={a.seed}',str(elf)]
    identities={str(path.resolve()):sha(path.resolve()) for path in [a.binary,a.uart,a.dtc,ROOT/'spike/provenance.json']}
    for path,digest in identities.items():
        target=out/'inputs'/digest
        if not target.exists():target.write_bytes(Path(path).read_bytes())
    env=dict(os.environ,PATH=str(a.dtc.parent)+os.pathsep+os.environ.get('PATH',''));env.pop('IRIS_FATAL_PCS',None)
    start=time.monotonic();error=None
    try:
        process=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=a.timeout)
        stdout,stderr,status=process.stdout,process.stderr,process.returncode
    except subprocess.TimeoutExpired as ex:
        stdout=ex.stdout.decode() if isinstance(ex.stdout,bytes) else ex.stdout or ''
        stderr=ex.stderr.decode() if isinstance(ex.stderr,bytes) else ex.stderr or ''
        status=None;error='timeout'
    (out/'run.stdout').write_text(stdout);(out/'run.stderr').write_text(stderr)
    receipt={'schema_version':1,'argv':command,'exit_status':status,'host_elapsed_seconds':time.monotonic()-start,
             'host_time_is_target_time':False,'timing_certified':False,'calibration_usable':False,'seed':a.seed,
             'input_sha256':identities,'build_sha256':sha(out/'build.json'),'elf_sha256':sha(elf),
             'stdout_sha256':sha(out/'run.stdout'),'stderr_sha256':sha(out/'run.stderr')}
    for path,digest in build['input_sha256'].items():
        if sha(Path(path))!=digest:raise ValueError('build input changed during execution: '+path)
    try:
        if status!=0:raise ValueError(error or f'exit {status}')
        receipt.update(validator.validate(stdout,corpus))
        for path,digest in identities.items():
            if sha(Path(path))!=digest:raise ValueError('changed execution input '+path)
    except (ValueError,TypeError,KeyError) as ex:
        receipt.update(functional_checks_passed=False,validation_error=str(ex))
    (out/'run.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    if not receipt['functional_checks_passed']:raise SystemExit(1)


if __name__=='__main__':main()
