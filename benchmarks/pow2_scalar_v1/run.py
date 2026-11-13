#!/usr/bin/env python3
"""Bounded software-only execution and independent scalar corpus validation."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from build import ROOT, sha
from validate import validate


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--build",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--seed",type=int,required=True)
    p.add_argument("--negative",action="store_true")
    p.add_argument("--native-dir",type=Path,default=ROOT/"build/combined-frozen-35901887")
    p.add_argument("--fixture",type=Path)
    p.add_argument("--timeout",type=float,default=180)
    a=p.parse_args()
    if not 0<a.timeout<=3600 or not 0<=a.seed<2**64:
        raise ValueError("Bounded timeout and unsigned seed")
    b=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    build=json.loads((b/"build.json").read_text());corpus=json.loads((b/"corpus.json").read_text())
    if build["negative_skip_kernel"] is not a.negative:
        raise ValueError("Exact positive/omitted-kernel selection")
    inputs=dict(build["input_sha256"])
    for path,h in inputs.items():
        if sha(path)!=h or sha(b/"inputs"/h)!=h:raise ValueError("Bound build input changed")
    binary=a.native_dir.resolve()/"spike";uart=binary.with_name("libsifive_uart.so")
    elf=b/"scalar.elf";rom=ROOT/"board/evidence/bootrom.rv64.img";dtb=ROOT/"board/build/iris.dtb"
    compute="rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm"
    dma="rv64gcv_zfh_zvfh_zvl256b_zvbb"
    argv=[str(binary),"--iris-vme","--isa="+dma,"--hart-isa=0:"+compute,"--hart-isa=1:"+compute,
        "--hart-isa=2:"+dma,"-p3","-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000",
        "--extlib="+str(uart),"--device=sifive_uart,0x10020000","--iris-bootrom="+str(rom),
        "--dtb="+str(dtb),"--iris-schedule-seed="+str(a.seed)]
    if a.fixture:
        fixture=a.fixture.resolve()
        argv+=["--iris-timing-fixture="+str(fixture),"--iris-timing-trace="+str(out/"native-summary.json")]
        inputs[str(fixture)]=sha(fixture)
    argv+=[str(elf)]
    for path in [Path(__file__).resolve(),b/"build.json",elf,binary,uart,rom,dtb]:
        inputs[str(path)]=sha(path)
    if sha(elf)!=build["elf_sha256"]:raise ValueError("Actual frozen ELF identity")
    report=dict(schema="iris.pow2_scalar_software_run.v1",**{"pass":False},status="running",
        started_at_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        argv=argv,input_sha256=inputs,ELF_sha256=sha(elf),native_sha256=sha(binary),
        UART_sha256=sha(uart),fixture_sha256=sha(a.fixture)if a.fixture else None,
        hardware_contacted=False,published_provider_qualification=False,
        seed=a.seed,timeout_seconds=a.timeout,expect_negative=a.negative)
    def save():
        temp=out/".run.json.tmp";temp.write_text(json.dumps(report,indent=2)+"\n");temp.replace(out/"run.json")
    save();proc=None;start=time.monotonic()
    try:
        env=dict(os.environ);env.pop("IRIS_FATAL_PCS",None)
        if a.fixture:env["IRIS_EMPIRICAL_FEATURES"]=str(out/"features.jsonl")
        with(out/"stdout").open("wb")as so,(out/"stderr").open("wb")as se:
            proc=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True)
            report["owned_child_pid"]=proc.pid;save()
            code=proc.wait(timeout=a.timeout)
        if (code==0)==a.negative:raise ValueError("Expected ordinary guest outcome")
        proof=validate((out/"stdout").read_text(),corpus,a.negative)
        if any(sha(path)!=h for path,h in inputs.items()):raise ValueError("Execution input changed")
        report.update(**{"pass":True},status="validated_omission_negative"if a.negative else"passed_guest_exit",
            exit_status=code,timed_out=False,normal_guest_exit_verified=code==0,proof=proof)
    except (Exception,KeyboardInterrupt)as error:
        report.update(status="failed_or_interrupted",error=str(error),**{"pass":False},
            timed_out=isinstance(error,subprocess.TimeoutExpired),normal_guest_exit_verified=False)
    finally:
        if proc is not None and proc.returncode is None:
            # Signal the actual unreaped owned process group only.
            try:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            time.sleep(.2)
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait()
        report.update(host_seconds=time.monotonic()-start,owned_process_cleanup_complete=proc is None or proc.returncode is not None)
        if proc is not None:report.setdefault("exit_status",proc.returncode)
        report["output_sha256"]={str(q):sha(q)for q in out.iterdir()if q.is_file()and q.name!="run.json"and not q.name.startswith(".")}
        save()
    print(json.dumps({k:report.get(k)for k in ["pass","status","host_seconds","proof","error"]}))
    return 0 if report["pass"]else 1


if __name__=="__main__":
    def interrupted(signum,frame):raise KeyboardInterrupt("Interrupted by signal"+str(signum))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
    raise SystemExit(main())
