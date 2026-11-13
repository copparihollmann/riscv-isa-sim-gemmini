#!/usr/bin/env python3
"""Negative host-protocol checks using fixtures, not simulated CPU results."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--positive-run",type=Path,default=ROOT/"build/zephyr-placements/run-mask7")
    p.add_argument("--build",type=Path,default=ROOT/"build/zephyr-placements/build-mask7")
    p.add_argument("--uart",type=Path,default=ROOT/"spike/bin/libsifive_uart.so")
    p.add_argument("--output",type=Path,default=ROOT/"build/zephyr-negative-validation")
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").unlink(missing_ok=True)
    proof=json.loads((args.positive_run/"results.json").read_text())
    if proof["status"]!="passed_scalar_zephyr_smp" or proof["harts"]!=[0,1,2]:
        raise RuntimeError("Successful actual three-hart scalar evidence required")
    results=[]
    for name in ("wrong_golden","missing_hart2","duplicate","bool_hart","counter_overflow","fatal_diagnostic","missing_completion"):
        rows=copy.deepcopy(proof["regions"]);extra="";done=True
        if name=="wrong_golden":rows[0]["checksum"]+=1
        if name=="missing_hart2":rows=[row for row in rows if row["hart"]!=2]
        if name=="duplicate":rows.append(rows[0])
        if name=="bool_hart":next(row for row in rows if row["hart"]==1)["hart"]=True
        if name=="counter_overflow":rows[0]["end_cycle"]=1<<64
        if name=="fatal_diagnostic":extra='IRIS_FATAL {"hart":2}\n'
        if name=="missing_completion":done=False
        text="\n".join("IRIS_REGION "+json.dumps(row) for row in rows)+"\n"+extra+('IRIS_BATCH_DONE {"failed":0}\n' if done else "")
        fixture=out/(name+".py")
        fixture.write_text("#!"+sys.executable+"\nprint("+repr(text)+",end='')\n");fixture.chmod(0o755)
        directory=out/name
        proc=subprocess.run([sys.executable,str(ROOT/"zephyr/run.py"),"--build",str(args.build.resolve()),
                             "--binary",str(fixture),"--uart",str(args.uart.resolve()),"--output",str(directory)],text=True,capture_output=True)
        result=json.loads((directory/"results.json").read_text())
        if proc.returncode==0 or result["status"]!="failed":raise RuntimeError("Invalid protocol accepted: "+name)
        results.append({"name":name,"pass":True,"exit_status":proc.returncode,"errors":result["errors"],"fixture_sha256":sha(fixture)})
    record={"schema_version":1,"scope":"Host console protocol rejection fixtures, not CPU execution or timing data",
            "status":"passed_negative_validation","tests":results,"runner_sha256":sha(ROOT/"zephyr/run.py"),
            "test_script_sha256":sha(Path(__file__)),"positive_run_sha256":sha(args.positive_run/"results.json")}
    (out/"results.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps({"status":record["status"],"tests":len(results)}))


if __name__=="__main__":main()
