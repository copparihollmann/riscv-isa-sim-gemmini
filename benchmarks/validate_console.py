#!/usr/bin/env python3
"""Fail on missing, duplicate, or failed rows from an Iris microbenchmark batch."""
import argparse
import json
from pathlib import Path


def validate(text, corpus, harts, smoke):
    if type(harts) is not int or harts not in (1, 2, 3):
        raise ValueError("harts must be an integer in [1,3]")
    cases = [case for case in corpus["cases"] if not smoke or case["included_in_smoke"]]
    masks = {"all": (1 << harts)-1, "compute": ((1 << harts)-1)&3, "1": 1, "4": 4 if harts==3 else 0}
    expected = {(case["case_id"], hart) for case in cases for hart in range(harts)
                if masks[case["active_hart_mask_expression"]] & (1 << hart)}
    goldens = {(case["case_id"], hart):case["expected_checksums_by_hart"][hart]
               for case in cases for hart in range(harts)}
    found, done = {}, []
    for line in text.splitlines():
        if line.startswith("IRIS_FATAL"):
            raise ValueError(line)
        if line.startswith("IRIS_BATCH_DONE "):
            done.append(json.loads(line[len("IRIS_BATCH_DONE "):]))
        if not line.startswith("IRIS_REGION "):
            continue
        row = json.loads(line[len("IRIS_REGION "):])
        if type(row.get("hart")) is not int or not 0 <= row["hart"] < harts or not isinstance(row.get("case_id"),str):
            raise ValueError("invalid region identity")
        key = (row["case_id"], row["hart"])
        if key in found:
            raise ValueError("duplicate region: " + repr(key))
        for field in ("start_cycle", "end_cycle", "instret_delta", "checksum", "expected_checksum"):
            if type(row.get(field)) is not int or not 0 <= row[field] < (1 << 64):
                raise ValueError("invalid counter/checksum field: " + repr(key))
        if row["end_cycle"] <= row["start_cycle"] or row.get("region")!="kernel":
            raise ValueError("invalid region: " + repr(key))
        if row.get("pass") is not True or row["checksum"]!=row["expected_checksum"]:
            raise ValueError("checksum failed: " + repr(key))
        if key not in goldens or row["checksum"] != goldens[key]:
            raise ValueError("independent golden checksum mismatch: " + repr(key))
        found[key]=row
    if set(found)!=expected:
        raise ValueError("region coverage mismatch: missing="+repr(sorted(expected-set(found)))+" extra="+repr(sorted(set(found)-expected)))
    if len(done)!=1 or type(done[0].get("failed")) is not int or done[0]["failed"]!=0:
        raise ValueError("missing or unsuccessful IRIS_BATCH_DONE")
    return {"regions":len(found),"harts":harts,"smoke":smoke,"functional_checks_passed":True,
            "timing_accuracy_certified":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("console",type=Path)
    parser.add_argument("--corpus",type=Path,default=Path(__file__).resolve().parent/"calibration-corpus.json")
    parser.add_argument("--harts",type=int,choices=(1,2,3),default=3)
    parser.add_argument("--smoke",action="store_true")
    args=parser.parse_args()
    try:
        result=validate(args.console.read_text(),json.loads(args.corpus.read_text()),args.harts,args.smoke)
    except (ValueError,KeyError,TypeError) as error:
        raise SystemExit(str(error))
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
