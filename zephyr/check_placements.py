#!/usr/bin/env python3
"""Build and execute all seven scalar Zephyr worker placements."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--binary",type=Path,default=ROOT/"spike/bin/spike-iris-functional")
    p.add_argument("--uart",type=Path,default=ROOT/"spike/bin/libsifive_uart.so")
    p.add_argument("--output",type=Path,default=ROOT/"build/zephyr-placements")
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    result=out/"results.json";result.unlink(missing_ok=True)
    identity=(sha(args.binary),sha(args.uart));proofs=[]
    for mask in range(1,8):
        build=out/("build-mask"+str(mask));run=out/("run-mask"+str(mask))
        subprocess.run([sys.executable,str(ROOT/"zephyr/build.py"),"--output",str(build),"--conf",str(ROOT/("zephyr/configs/mask"+str(mask)+".conf"))],check=True)
        subprocess.run([sys.executable,str(ROOT/"zephyr/run.py"),"--build",str(build),"--output",str(run),"--binary",str(args.binary.resolve()),"--uart",str(args.uart.resolve())],check=True)
        if (sha(args.binary),sha(args.uart))!=identity:raise RuntimeError("Simulator changed during placement sweep")
        row=json.loads((run/"results.json").read_text())
        if row["status"]!="passed_scalar_zephyr_smp":raise RuntimeError("Placement failed")
        proofs.append({"mask":mask,"harts":row["harts"],"regions":len(row["regions"]),
                       "results":str(run/"results.json"),"results_sha256":sha(run/"results.json")})
    record={"schema_version":1,"status":"passed_all_seven_scalar_zephyr_placements",
            "zephyr_sha":"cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0","binary_sha256":identity[0],"uart_sha256":identity[1],
            "placements":proofs,"runner_sha256":sha(Path(__file__)),"timing_certified":False,"rtl_certified":False,"vme_context_certified":False}
    result.write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({"status":record["status"],"placements":len(proofs),"regions":sum(row["regions"] for row in proofs),"receipt":str(result)}))


if __name__=="__main__":main()
