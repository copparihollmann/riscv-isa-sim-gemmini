#!/usr/bin/env python3
"""Run the isolated saved-FIR RTL reference; never imply FireSim equivalence."""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("elf",type=Path);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--binary",type=Path,default=ROOT/"build/rtl-verilator/simulator-IrisConfig")
    p.add_argument("--build-manifest",type=Path,default=ROOT/"build/rtl-verilator/manifest.json")
    p.add_argument("--max-cycles",type=int,default=5000000)
    p.add_argument("--timeout",type=int,default=600)
    p.add_argument("--seed",type=int,default=1)
    p.add_argument("--release-secondary-harts",action="store_true",
                   help="explicit host MSIP1/2 writes for baremetal all-hart startup")
    args=p.parse_args()
    if args.timeout<=0 or args.max_cycles<=0 or args.seed<0:p.error("positive bounds and nonnegative seed required")
    binary=args.binary.resolve();elf=args.elf.resolve();out=args.output.resolve()
    build=json.loads(args.build_manifest.read_text())
    if build.get("status")!="simulator_built" or sha(binary)!=build.get("binary_sha256"):
        p.error("built RTL binary and matching manifest required")
    out.mkdir(parents=True,exist_ok=False)
    (out/"build-manifest.json").write_bytes(args.build_manifest.read_bytes())
    ldd=subprocess.check_output(["ldd",str(binary)],text=True)
    (out/"ldd.txt").write_text(ldd);libraries=[]
    if "not found" in ldd:raise RuntimeError("unresolved RTL simulator library")
    for line in ldd.splitlines():
        match=re.search(r"(?:=> )?(/[^ ]+) \(",line)
        if match and Path(match[1]).is_file():libraries.append({"path":match[1],"sha256":sha(match[1])})
    # FESVR must see permissive before any Verilator-only arguments; otherwise
    # it interprets a +verilator argument as the program filename.
    cmd=[str(binary),"+permissive","+verilator+seed+"+str(args.seed),"+verilator+rand+reset+2",
         "+max-cycles="+str(args.max_cycles)]
    if args.release_secondary_harts:cmd += ["+init_write=0x2000004:0x1","+init_write=0x2000008:0x1"]
    cmd += ["+permissive-off",str(elf)]
    record={"schema_version":1,"status":"running","started_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "argv":cmd,"binary_sha256":sha(binary),"elf_sha256":sha(elf),"libraries":libraries,
            "build_manifest_sha256":sha(out/"build-manifest.json"),"runner_sha256":sha(Path(__file__)),
            "reference_kind":"saved_IrisConfig_Verilator_native_FIR_memory","matches_ethan_firesim_image":False,
            "source_build_association_verified":False,"calibration_usable_for_firesim":False,
            "secondary_release":"host MSIP1/2 before hart0" if args.release_secondary_harts else "program/OS responsibility",
            "random_reset_seed":args.seed,"host_timeout_seconds":args.timeout,"functional_certified":False}
    receipt=out/"run.json";receipt.write_text(json.dumps(record,indent=2)+"\n");start=time.perf_counter()
    with (out/"stdout").open("w") as stdout,(out/"stderr").open("w") as stderr:
        try:
            proc=subprocess.run(cmd,cwd=out,stdout=stdout,stderr=stderr,timeout=args.timeout)
            record.update(exit_status=proc.returncode,timed_out=False)
        except subprocess.TimeoutExpired:record.update(exit_status=None,timed_out=True)
    record.update(host_seconds=time.perf_counter()-start,stdout_sha256=sha(out/"stdout"),stderr_sha256=sha(out/"stderr"),
                  status="process_exit0_validation_required" if record["exit_status"]==0 else "failed")
    if sha(binary)!=record["binary_sha256"] or sha(elf)!=record["elf_sha256"]:
        record.update(status="failed",input_changed_during_run=True)
    receipt.write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({"status":record["status"],"exit_status":record["exit_status"],"host_seconds":record["host_seconds"],"receipt":str(receipt)}))
    return 0 if record["status"]=="process_exit0_validation_required" else 1

if __name__=="__main__":raise SystemExit(main())
