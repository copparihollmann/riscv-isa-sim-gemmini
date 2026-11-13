#!/usr/bin/env python3
"""Run exact v2 ELF on functional Spike; host time is never target timing data."""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from validate import validate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
COMPUTE='rv64gcv_zfh_zvfh_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
DMA='rv64gcv_zfh_zvfh_zvl256b_zvbb'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,default=HERE/'build')
    parser.add_argument('--spike',type=Path,default=ROOT/'spike/bin/spike-iris-functional')
    parser.add_argument('--dtc',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/bin/dtc'))
    parser.add_argument('--timeout',type=int,default=120)
    parser.add_argument('--seed',type=int,default=0)
    args=parser.parse_args()
    out=args.build.resolve();elf=out/'batch-v2.elf';corpus=json.loads((out/'corpus.json').read_text())
    build=json.loads((out/'build.json').read_text())
    if sha(elf)!=build['elf_sha256']: raise SystemExit('ELF digest mismatch')
    for path,expected in build['input_sha256'].items():
        if sha(Path(path))!=expected: raise SystemExit('build input changed: '+path)
    for path,expected in corpus['v1_frozen_input_sha256'].items():
        if sha(ROOT/path)!=expected: raise SystemExit('frozen v1 input changed: '+path)
    cmd=[str(args.spike.resolve()),'--iris-vme',f'--isa={DMA}',f'--hart-isa=0:{COMPUTE}',f'--hart-isa=1:{COMPUTE}',f'--hart-isa=2:{DMA}',
         '-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
         '--extlib='+str(ROOT/'spike/bin/libsifive_uart.so'),'--device=sifive_uart,0x10020000']
    if args.seed: cmd.append('--iris-schedule-seed='+str(args.seed))
    cmd.append(str(elf));env=dict(os.environ);env['PATH']=str(args.dtc.resolve().parent)+os.pathsep+env['PATH'];env.pop('IRIS_FATAL_PCS',None)
    spike_hash=sha(args.spike.resolve());uart_hash=sha(ROOT/'spike/bin/libsifive_uart.so');dtc_hash=sha(args.dtc.resolve())
    provenance_path=ROOT/'spike/provenance.json'
    provenance_hash=sha(provenance_path) if provenance_path.is_file() else None
    start=time.perf_counter()
    try: proc=subprocess.run(cmd,cwd=out,env=env,text=True,capture_output=True,timeout=args.timeout)
    except subprocess.TimeoutExpired as error:
        (out/'run.json').write_text(json.dumps({'status':'timeout','timeout_seconds':args.timeout,'command':cmd,'timing_certified':False},indent=2)+'\n')
        for name,text in [('stdout',error.stdout),('stderr',error.stderr)]:
            (out/('run.'+name)).write_bytes(text if isinstance(text,bytes) else (text or '').encode())
        raise SystemExit('functional v2 run timed out')
    elapsed=time.perf_counter()-start
    (out/'run.stdout').write_text(proc.stdout);(out/'run.stderr').write_text(proc.stderr)
    record={'schema_version':1,'command':cmd,'exit_status':proc.returncode,'elf_sha256':sha(elf),
            'spike_sha256':spike_hash,'uart_plugin_sha256':uart_hash,'dtc_sha256':dtc_hash,
            'spike_provenance_sha256':provenance_hash,
            'corpus_sha256':sha(out/'corpus.json'),'host_elapsed_seconds':elapsed,'host_elapsed_is_target_time':False,
            'stdout_sha256':sha(out/'run.stdout'),'stderr_sha256':sha(out/'run.stderr'),'timing_certified':False}
    try: record.update(validate(proc.stdout,corpus))
    except (ValueError,TypeError,KeyError) as error: record.update(functional_checks_passed=False,validation_error=str(error))
    if sha(args.spike.resolve())!=spike_hash or sha(ROOT/'spike/bin/libsifive_uart.so')!=uart_hash:
        record.update(functional_checks_passed=False,validation_error='simulator or UART plugin changed during run')
    (out/'run.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
    if proc.returncode or not record['functional_checks_passed']: raise SystemExit(1)

if __name__=='__main__': main()
