#!/usr/bin/env python3
"""Run the NEW probe locally with a bounded subprocess and exact source hashes."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command,symbols
from firstuse_diag_validate_v1 import validate
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(a):
 b=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True);build=json.loads((b/'build.json').read_text());elf=b/'zephyr/zephyr.elf'
 if build['status']!='built'or build['elf_sha256']!=sha(elf):raise ValueError('Exact built ELF')
 inputs={str(ROOT/p):h for p,h in build['input_sha256'].items()}
 for p,h in inputs.items():
  if sha(p)!=h:raise ValueError('Changed input '+p)
 binary=a.binary.resolve();uart=a.uart.resolve();rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb';table=symbols(elf);fatal=[table[n]for n in ['z_fatal_error','z_riscv_fatal_error']if n in table]
 argv=command(binary,elf);argv=['--extlib='+str(uart)if x.startswith('--extlib=')else x for x in argv];argv=argv[:-1]+['--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-schedule-seed='+str(a.seed)]+argv[-1:];env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(x)for x in fatal));start=time.monotonic();timed_out=False
 try:r=subprocess.run(argv,env=env,capture_output=True,timeout=a.timeout)
 except subprocess.TimeoutExpired as e:r=subprocess.CompletedProcess(argv,124,e.stdout or b'',e.stderr or b'');timed_out=True
 (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr);errors=[];proof=None
 try:proof=validate(r.stdout.decode('utf-8','strict'),a.expect_failure)
 except(ValueError,KeyError,TypeError,UnicodeError)as e:errors.append(str(e))
 if timed_out or r.returncode!=(1 if a.expect_failure else 0):errors.append('Expected actual native exit '+str(1 if a.expect_failure else 0))
 for p in [binary,uart,rom,dtb,elf,b/'build.json',Path(__file__).resolve(),ROOT/'zephyr/firstuse_diag_validate_v1.py']:inputs[str(p)]=sha(p)
 if any(sha(p)!=h for p,h in inputs.items()):errors.append('Input changed')
 record=dict(schema='iris.Zephyr_firstuse_diag_execution.v1',**{'pass':not errors},expect_failure=a.expect_failure,seed=a.seed,argv=argv,exit_status=r.returncode,timed_out=timed_out,host_seconds=time.monotonic()-start,ELF_sha256=sha(elf),build_receipt_sha256=sha(b/'build.json'),proof=proof,errors=errors,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),input_sha256=inputs,hardware_contacted=False,timing_certified=False)
 (out/'report.json').write_text(json.dumps(record,indent=2)+'\n');return record
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/combined-frozen-35901887/spike');p.add_argument('--uart',type=Path,default=ROOT/'build/combined-frozen-35901887/libsifive_uart.so');p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--timeout',type=int,default=120);p.add_argument('--expect-failure',action='store_true');a=p.parse_args();r=run(a);print(json.dumps({k:r[k]for k in ['pass','exit_status','timed_out','proof','errors']}));raise SystemExit(0 if r['pass']else 1)
