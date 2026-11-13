#!/usr/bin/env python3
"""Build context stress using a clean base or explicitly matched Zephyr patch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import time
from uart_profiles import profile as uart_profile,inputs as uart_inputs,cmake as uart_cmake

ROOT=Path(__file__).resolve().parents[1]
PIN="cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0"


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--source",type=Path,default=ROOT/"third_party/zephyr")
    p.add_argument("--app",type=Path,default=ROOT/"zephyr/context-stress")
    p.add_argument("--patch",type=Path)
    p.add_argument("--uart-profile",choices=['physical','ethan-firesim'],default='physical')
    p.add_argument("--extra-conf",type=Path,action="append",default=[])
    p.add_argument("--cmake",action="append",default=[],help="Explicit additional CMake cache argument")
    p.add_argument("--input",type=Path,action="append",default=[],help="Additional generated/source build input to archive")
    p.add_argument("--output",type=Path,default=ROOT/"build/zephyr-context-base")
    p.add_argument("--tools",type=Path,default=Path("/scratch/eygao/iris-cy/.conda-env"))
    p.add_argument("--jobs",type=int,default=6)
    args=p.parse_args();z=args.source.resolve();app=args.app.resolve();out=args.output.resolve();tools=args.tools.resolve()
    out.mkdir(parents=True,exist_ok=True);(out/"build.json").unlink(missing_ok=True)
    pin=subprocess.check_output(["git","-C",str(z),"rev-parse","HEAD"],text=True).strip()
    if pin!=PIN:raise RuntimeError("Wrong Zephyr base pin")
    diff=subprocess.check_output(["git","-C",str(z),"diff","--binary","HEAD"])
    untracked=subprocess.check_output(["git","-C",str(z),"ls-files","--others","--exclude-standard"],text=True)
    if untracked:raise RuntimeError("Unrecorded Zephyr overlay inputs")
    if diff and (not args.patch or args.patch.read_bytes()!=diff):raise RuntimeError("Applied Zephyr overlay differs from recorded patch")
    if args.patch and args.patch.read_bytes()!=diff:raise RuntimeError("Recorded overlay is not applied exactly")
    sources=[path for folder in [app,ROOT/"zephyr/boards",ROOT/"zephyr/dts"] for path in folder.rglob("*") if path.is_file() and path.suffix!=".md"]
    sources+=[Path(__file__),ROOT/"zephyr/context-stress/src/registers.S"]+([args.patch.resolve()] if args.patch else [])+[path.resolve() for path in args.extra_conf+args.input]
    sources+=uart_inputs(args.uart_profile)
    inputs={str(path.relative_to(ROOT)):sha(path) for path in sorted(set(sources))}
    for name in inputs:
        saved=out/"input-snapshot"/name;saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,saved)
    env=dict(os.environ,ZEPHYR_BASE=str(z),ZEPHYR_TOOLCHAIN_VARIANT="cross-compile",CROSS_COMPILE=str(tools/"riscv-tools/bin/riscv64-unknown-elf-"),PYTHONDONTWRITEBYTECODE="1")
    env["PATH"]=str(tools/"bin")+os.pathsep+env["PATH"]
    commands=[[str(tools/"bin/cmake"),"-GNinja","-S",str(app),"-B",str(out),"-DBOARD=iris","-DBOARD_ROOT="+str(ROOT/"zephyr"),"-DDTS_ROOT="+str(ROOT/"zephyr"),"-DPython3_EXECUTABLE="+str(tools/"bin/python3"),"-DDTC="+str(tools/"bin/dtc")],
              [str(tools/"bin/cmake"),"--build",str(out),"-j",str(args.jobs)]]
    if args.extra_conf:commands[0]+=["-DEXTRA_CONF_FILE="+";".join(str(path.resolve()) for path in args.extra_conf)]
    commands[0]+=args.cmake
    commands[0]+=uart_cmake(args.uart_profile)
    results=[];start=time.perf_counter()
    for index,cmd in enumerate(commands):
        log=out/(("configure" if index==0 else "build")+".log")
        with log.open("w") as stream:p=subprocess.run(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT)
        results.append({"argv":cmd,"exit_status":p.returncode,"log_sha256":sha(log)})
        if p.returncode:break
    if subprocess.check_output(["git","-C",str(z),"diff","--binary","HEAD"])!=diff:raise RuntimeError("Zephyr source changed during build")
    if any(sha(ROOT/name)!=digest for name,digest in inputs.items()):raise RuntimeError("Build inputs changed during build")
    elf=out/"zephyr/zephyr.elf"
    record={"schema_version":1,"status":"built" if len(results)==2 and not any(row["exit_status"] for row in results) else "failed",
            "zephyr_sha":PIN,"source":str(z),"uart_profile":uart_profile(args.uart_profile),"source_patch_sha256":hashlib.sha256(diff).hexdigest() if diff else None,
            "commands":results,"input_sha256":inputs,
            "source_snapshot":"input-snapshot",
            "compiler_sha256":sha(tools/"riscv-tools/bin/riscv64-unknown-elf-gcc"),"elf_sha256":sha(elf) if elf.is_file() else None,
            "host_seconds":time.perf_counter()-start,"rtl_certified":False,"timing_certified":False}
    (out/"build.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({"status":record["status"],"receipt":str(out/"build.json")}))
    if record["status"]=="failed":print(log.read_text()[-12000:]);return 1
    return 0


if __name__=="__main__":raise SystemExit(main())
