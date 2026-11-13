#!/usr/bin/env python3
"""Build the exact pinned Zephyr tree with the source-backed Iris board."""
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--output",type=Path,default=ROOT/"build/zephyr-scalar3")
    p.add_argument("--conf",type=Path,default=ROOT/"benchmarks/zephyr/all-three.conf")
    p.add_argument("--source",type=Path,default=ROOT/"third_party/zephyr")
    p.add_argument("--patch",type=Path)
    p.add_argument("--uart-profile",choices=['physical','ethan-firesim'],default='physical')
    p.add_argument("--saturn",type=Path,help="Pinned Saturn clone for the optional VME app")
    p.add_argument("--tools",type=Path,default=Path("/scratch/eygao/iris-cy/.conda-env"))
    p.add_argument("--jobs",type=int,default=6)
    p.add_argument("--configure-only",action="store_true")
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    (out/"build.json").unlink(missing_ok=True)
    z=args.source.resolve();tools=args.tools.resolve()
    if subprocess.check_output(["git","-C",str(z),"rev-parse","HEAD"],text=True).strip()!=PIN:
        raise RuntimeError("Zephyr source pin mismatch")
    diff=subprocess.check_output(["git","-C",str(z),"diff","--binary","HEAD"])
    if subprocess.check_output(["git","-C",str(z),"ls-files","--others","--exclude-standard"],text=True):raise RuntimeError("Unrecorded Zephyr source inputs")
    if diff and (not args.patch or args.patch.read_bytes()!=diff):raise RuntimeError("Zephyr overlay differs from the explicit patch")
    if args.patch and args.patch.read_bytes()!=diff:raise RuntimeError("Recorded Zephyr patch is not applied exactly")
    env=dict(os.environ,ZEPHYR_BASE=str(z),ZEPHYR_TOOLCHAIN_VARIANT="cross-compile",
             CROSS_COMPILE=str(tools/"riscv-tools/bin/riscv64-unknown-elf-"),PYTHONDONTWRITEBYTECODE="1")
    env["PATH"]=str(tools/"bin")+os.pathsep+env["PATH"]
    cmake=tools/"bin/cmake";compiler=tools/"riscv-tools/bin/riscv64-unknown-elf-gcc"
    libgcc=Path(subprocess.check_output([str(compiler),"-print-libgcc-file-name"],text=True).strip())
    configure=[str(cmake),"-GNinja","-S",str(ROOT/"benchmarks/zephyr"),"-B",str(out),"-DBOARD=iris",
               "-DBOARD_ROOT="+str(ROOT/"zephyr"),"-DDTS_ROOT="+str(ROOT/"zephyr"),
               "-DEXTRA_CONF_FILE="+str(args.conf.resolve()),"-DPython3_EXECUTABLE="+str(tools/"bin/python3"),
               "-DDTC="+str(tools/"bin/dtc")]
    configure += uart_cmake(args.uart_profile)
    if args.saturn:
        if subprocess.check_output(["git","-C",str(args.saturn),"rev-parse","HEAD"],text=True).strip()!="536774bd4c5e3bcd7813a4a0dc72fc87e5818532":raise RuntimeError("Wrong Saturn base pin")
        configure += ["-DSATURN_ROOT="+str(args.saturn.resolve())]
    build=[str(cmake),"--build",str(out),"-j",str(args.jobs)]
    start=time.perf_counter()
    commands=[]
    for name,cmd in [("configure",configure)]+([] if args.configure_only else [("build",build)]):
        with (out/(name+".log")).open("w") as log:
            result=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
        commands.append({"name":name,"argv":cmd,"exit_status":result.returncode,"log_sha256":sha(out/(name+".log"))})
        if result.returncode: break
    inputs=[path for folder in [ROOT/"zephyr/boards",ROOT/"zephyr/dts",ROOT/"benchmarks/zephyr"]
            for path in folder.rglob("*") if path.is_file() and path.suffix!=".md"]
    inputs+=[Path(__file__),args.conf.resolve(),ROOT/"board/evidence/firesim-dts.dts",ROOT/"hardware/manifest.json",ROOT/"hardware/memory-paths.json"]
    inputs+=uart_inputs(args.uart_profile)
    inputs+=([args.patch.resolve()] if args.patch else [])+([args.saturn.resolve()/"benchmarks/common/vme.h"] if args.saturn else [])
    for path in set(inputs):
        saved=out/"input-snapshot"/path.relative_to(ROOT);saved.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,saved)
    artifacts=[path for path in [out/"zephyr/zephyr.elf",out/"zephyr/zephyr.dts",out/"zephyr/.config",out/"zephyr/zephyr.map"] if path.is_file()]
    record={"schema_version":1,"zephyr_sha":PIN,"source_url":"https://github.com/ucb-bar/zephyr.git",
            "board":"iris","uart_profile":uart_profile(args.uart_profile),"status":"built" if all(row["exit_status"]==0 for row in commands) and not args.configure_only else "configured" if all(row["exit_status"]==0 for row in commands) else "failed",
            "source":str(z),"source_patch_sha256":hashlib.sha256(diff).hexdigest() if diff else None,"source_snapshot":"input-snapshot",
            "commands":commands,"compiler_sha256":sha(compiler),
            "linked_libgcc":{"path":str(libgcc),"sha256":sha(libgcc)},
            "compiler_version":subprocess.check_output([str(compiler),"--version"],text=True).splitlines()[0],
            "input_sha256":{str(path.relative_to(ROOT)):sha(path) for path in sorted(set(inputs))},
            "artifact_sha256":{str(path.relative_to(out)):sha(path) for path in artifacts},
            "host_seconds":time.perf_counter()-start,"booted":False,"zephyr_smp_certified":False,
            "rtl_certified":False,"timing_certified":False,"vme_context_certified":False}
    (out/"build.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({"status":record["status"],"receipt":str(out/"build.json")}))
    if record["status"]=="failed":
        print((out/(commands[-1]["name"]+".log")).read_text()[-10000:])
        return 1
    return 0


if __name__=="__main__":raise SystemExit(main())
