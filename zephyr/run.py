#!/usr/bin/env python3
"""Execute the actual scalar Zephyr SMP image; no timing/RTL claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uart_profiles import check_report

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.run_functional import command,symbols


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--build",type=Path,default=ROOT/"build/zephyr-scalar3")
    p.add_argument("--binary",type=Path,default=ROOT/"spike/bin/spike-iris-functional")
    p.add_argument("--uart",type=Path,default=ROOT/"spike/bin/libsifive_uart.so")
    p.add_argument("--output",type=Path,default=ROOT/"build/zephyr-run-scalar3")
    p.add_argument("--timeout",type=int,default=60)
    p.add_argument("--timing-fixture",type=Path,help="Explicit synthetic live-clock fixture, not Iris calibration")
    p.add_argument("--seed",type=int,help="Recorded deterministic scheduling variation")
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    runner_source=Path(__file__).read_bytes()
    (out/"runner-source.py").write_bytes(runner_source)
    receipt=out/"results.json"
    receipt.unlink(missing_ok=True)
    build=args.build.resolve();elf=build/"zephyr/zephyr.elf"
    proof=json.loads((build/"build.json").read_text())
    if proof["status"]!="built" or sha(elf)!=proof["artifact_sha256"]["zephyr/zephyr.elf"]:
        raise RuntimeError("Zephyr ELF differs from successful build receipt")
    for name,digest in proof["input_sha256"].items():
        if sha(ROOT/name)!=digest:raise RuntimeError("Zephyr build input changed: "+name)
    configs={}
    for line in (build/"zephyr/.config").read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            name,_,value=line.partition("=");configs[name]=value
    mask=int(configs["CONFIG_IRIS_BENCH_HART_MASK"])
    active=[h for h in range(3) if mask&(1<<h)]
    workers=int(configs["CONFIG_IRIS_BENCH_WORKERS"])
    if len(active)!=workers:raise RuntimeError("Invalid compiled worker placement")
    vme=configs.get("CONFIG_IRIS_BENCH_VME")=="y"
    if vme and configs.get("CONFIG_RISCV_IRIS_VME_CONTEXT")!="y":raise RuntimeError("VME app requires the explicit Iris ownership/context extension")
    table=symbols(elf)
    fatal=[table[name] for name in ("z_fatal_error","z_riscv_fatal_error") if name in table]
    if not fatal:raise RuntimeError("ELF has no known fatal handler entry")
    env=dict(os.environ,IRIS_FATAL_PCS=",".join(hex(address) for address in fatal))
    env["PATH"]="/scratch/eygao/iris-cy/.conda-env/bin:"+env["PATH"]
    cmd=command(args.binary.resolve(),elf)
    cmd=["--extlib="+str(args.uart.resolve()) if arg.startswith("--extlib=") else arg for arg in cmd]
    rom,dtb=ROOT/"board/evidence/bootrom.rv64.img",ROOT/"board/build/iris.dtb"
    cmd=cmd[:-1]+["--iris-bootrom="+str(rom),"--dtb="+str(dtb)]+cmd[-1:]
    if args.timing_fixture:
        cmd=cmd[:-1]+["--iris-timing-fixture="+str(args.timing_fixture.resolve()),
                      "--iris-timing-trace="+str(out/"graph.json")]+cmd[-1:]
    if args.seed is not None:cmd=cmd[:-1]+["--iris-schedule-seed="+str(args.seed)]+cmd[-1:]
    start=time.perf_counter();timed_out=False
    try:result=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=args.timeout)
    except subprocess.TimeoutExpired as error:
        timed_out=True
        def decoded(value):return value.decode(errors="replace") if isinstance(value,bytes) else value or ""
        result=subprocess.CompletedProcess(cmd,124,decoded(error.stdout),decoded(error.stderr))
    elapsed=time.perf_counter()-start
    stdout,stderr=out/"stdout",out/"stderr"
    stdout.write_text(result.stdout);stderr.write_text(result.stderr)
    rows=[json.loads(line[len("IRIS_REGION "):]) for line in result.stdout.splitlines() if line.startswith("IRIS_REGION ")]
    done=[json.loads(line[len("IRIS_BATCH_DONE "):]) for line in result.stdout.splitlines() if line.startswith("IRIS_BATCH_DONE ")]
    expected={}
    for worker,hart in enumerate(active):
        expected[("zephyr.gemm16",hart)]=len(range(worker,16,workers))*16*16
        expected[("zephyr.conv2d8",hart)]=len(range(worker,6,workers))*6*9
        if vme:expected[("zephyr.vme.yield",hart)]=1024
    observed={}
    errors=[]
    uart_readback=None
    if proof.get('uart_profile'):
        try:uart_readback=check_report(result.stdout.splitlines(),proof['uart_profile']['name'])
        except RuntimeError as error:errors.append(str(error))
    for row in rows:
        if type(row.get("hart")) is not int or not 0<=row["hart"]<3:
            errors.append("invalid architectural hart identity");continue
        key=(row.get("case_id"),row.get("hart"))
        if key not in expected or key in observed:errors.append("unknown or duplicate region "+repr(key));continue
        observed[key]=row
        role="scalar.compute" if key[0]!="zephyr.vme.yield" else "vme.compute" if row["hart"]<2 else "vector.copy"
        if row.get("checksum")!=expected[key] or row.get("role")!=role or row.get("hart_mask")!=mask:
            errors.append("hart/role/independent checksum mismatch "+repr(key))
        if any(type(row.get(name)) is not int or not 0<=row[name]<(1<<64) for name in ("start_cycle","end_cycle","instret_delta")) or row.get("end_cycle",0)<=row.get("start_cycle",0) or row.get("instret_delta",0)==0:
            errors.append("invalid region counters "+repr(key))
    if set(observed)!=set(expected):errors.append("missing expected per-hart regions")
    if done!=[{"failed":0}]:errors.append("missing successful completion")
    if result.returncode or timed_out:errors.append("simulator failed or timed out")
    if any(line.startswith("IRIS_FATAL") for line in (result.stdout+result.stderr).splitlines()):errors.append("fatal diagnostic in simulator output")
    if Path(__file__).read_bytes()!=runner_source:errors.append("runner source changed during execution")
    record={"schema_version":1,"status":("passed_mixed_zephyr_smp" if vme else "passed_scalar_zephyr_smp") if not errors else "failed",
            "errors":errors,"argv":cmd,"exit_status":result.returncode,"timed_out":timed_out,"host_seconds":elapsed,
            "harts":active,"regions":rows,"checksums_independent":True,"physical_boot":True,"seed":args.seed,
            "binary_sha256":sha(args.binary),"uart_sha256":sha(args.uart),"elf_sha256":sha(elf),
            "build_receipt_sha256":sha(build/"build.json"),"runner_sha256":hashlib.sha256(runner_source).hexdigest(),
            "stdout_sha256":sha(stdout),"stderr_sha256":sha(stderr),"rom_sha256":sha(rom),"dtb_sha256":sha(dtb),
            "fatal_handler_pcs":[hex(address) for address in fatal],"timing_certified":False,"rtl_certified":False,
            "vme_context_certified":False,"scope":"Actual pinned Zephyr scalar app with SMP, CPU affinity, mutexes, yields, sleeps and HTIF completion; not full Zephyr/SoC certification."}
    if proof.get('uart_profile'):record.update(uart_profile=proof['uart_profile'],uart_readback=uart_readback)
    if vme:
        record["vme_ownership_abi"]="iris_vme_enable before measured VME region on compute harts only"
        record["scope"]="Actual Iris derived Zephyr mixed scalar/RVV/VME app, three harts, CPU affinity, yields, synchronization and HTIF; competing same-hart VME contexts validated separately."
    if args.timing_fixture:
        graph=out/"graph.json"
        record["live_fixture"]={"fixture_sha256":sha(args.timing_fixture),"graph_sha256":sha(graph) if graph.is_file() else None,
                                "purpose":"uncalibrated integration; not performance prediction"}
        if not graph.is_file():errors.append("live fixture omitted its event graph")
        else:
            data=json.loads(graph.read_text())
            record["live_fixture"].update(base_clock_hz=data["base_clock_hz"],hart_cycle_dividers=data["hart_cycle_dividers"],retired_instructions=data["retired_instructions"])
        record["status"]=("passed_mixed_zephyr_smp_live_fixture" if vme else "passed_scalar_zephyr_smp_live_fixture") if not errors else "failed"
    receipt.write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({"status":record["status"],"receipt":str(receipt),"regions":len(rows),"errors":errors}))
    return 0 if not errors else 1


if __name__=="__main__":raise SystemExit(main())
