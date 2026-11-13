#!/usr/bin/env python3
"""Independent per-word oracle and canonical-grid validation."""
import argparse
import json
from pathlib import Path
import struct

KINDS=("integer_dependent","integer_independent4","fp16_dependent","fp16_independent4",
       "fp32_dependent","fp32_independent4","fp64_dependent","fp64_independent4")


def expected(kind,n):
    if kind.startswith("integer"):
        return [n,2*n,3*n,4*n] if kind.endswith("independent4") else [n,0,0,0]
    width=int(kind[2:4])
    # Independent exact encoding for positive power-of-two integers. Every
    # accumulation from 0 to N<=2048 is exactly representable, including FP16.
    fraction,bias={16:(10,15),32:(23,127),64:(52,1023)}[width]
    exponent=n.bit_length()-1
    bits=(exponent+bias)<<fraction
    return [bits]*4 if kind.endswith("independent4") else [bits,0,0,0]


def validate(text,corpus,negative=False):
    cs=corpus["cases"]
    canonical=[]
    for trial in range(3):
        for n in [1<<k for k in range(4,12)]:
            for ki,kind in enumerate(KINDS):
                for hart in range(3):
                    canonical.append((f"scalar.pow2.{kind}.n{n}.h{hart}.trial{trial}",kind,ki,n,hart,trial))
    if len(cs)!=576 or corpus["reserved_validation_lengths"]!=[32,256,1024]:
        raise ValueError("Frozen576 grid and reservedN split required")
    rows=[];groups=[];done=[];prior={}
    for line in text.splitlines():
        if line.startswith("IRIS_REGION "):
            rows.append(json.loads(line.split(" ",1)[1]))
        elif line.startswith("IRIS_SCALAR_GROUP "):
            g=json.loads(line.split(" ",1)[1])
            if g!={"group":len(groups),"records":len(rows)} or len(rows)!=24*(len(groups)+1):
                raise ValueError("Canonical console group frontier")
            groups.append(g)
        elif line.startswith("IRIS_BATCH_DONE "):
            done.append(json.loads(line.split(" ",1)[1]))
        elif line.startswith("IRIS_FATAL "):
            raise ValueError("Actual fatal trap")
    if len(rows)!=576 or len(groups)!=24:
        raise ValueError("Every region and complete frontier required")
    for row,c,canonical_row in zip(rows,cs,canonical):
        cid,kind,ki,n,hart,trial=canonical_row
        want=expected(kind,n)
        if c["id"]!=cid or c["expected_values"]!=want or c["active_harts"]!=[hart]:
            raise ValueError("Corpus differs from independent canonical golden")
        if c["internal_split"]!=("reserved_validation" if n in (32,256,1024) else "train"):
            raise ValueError("Reserved length grouping changed")
        for k,v in {"case_id":cid,"suite":"pow2_scalar","region":"kernel","hart":hart,
                    "kind_index":ki,"n":n,"trial_id":trial,"expected_checksum":want[0]}.items():
            if type(row.get(k))is not type(v) or row[k]!=v:
                raise ValueError("Typed row identity: "+k)
        if any(type(row.get(k))is not int or not 0<=row[k]<2**64 for k in
               ("start_cycle","end_cycle","instret_delta","mtime_before","mtime_after","checksum")):
            raise ValueError("Typed architectural counters/checksum")
        if row["start_cycle"]>=row["end_cycle"] or row["start_cycle"]<prior.get(hart,0) or row["mtime_before"]>row["mtime_after"]:
            raise ValueError("Forward per-hart counters and CLINT")
        prior[hart]=row["end_cycle"]
        if type(row.get("pass"))is not bool:
            raise ValueError("Typed pass flag")
        if negative:
            if row["values"]!=[0]*4 or row["checksum"]!=0 or row["pass"]is not False:
                raise ValueError("Omitted-kernel negative must fail every actual word group")
        elif row["values"]!=want or row["checksum"]!=want[0] or row["pass"]is not True or row["instret_delta"]<3*n:
            raise ValueError("Independent complete word/instruction golden")
    if done!=[dict(failed=576 if negative else 0,cases=576,regions=576,trials=3)]:
        raise ValueError("Exact independent completion")
    return dict(pass_=True,regions=576,words=2304,groups=24,trials=3,
        all_three_harts_individually=True,normal_completion=not negative,
        omitted_kernel_detected=negative,timing_certified=False)


if __name__=="__main__":
    p=argparse.ArgumentParser(__doc__);p.add_argument("console",type=Path)
    p.add_argument("--corpus",type=Path,required=True);p.add_argument("--negative",action="store_true")
    a=p.parse_args();print(json.dumps(validate(a.console.read_text(),json.loads(a.corpus.read_text()),a.negative)))
