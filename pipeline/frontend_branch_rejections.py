#!/usr/bin/env python3
"""Corrupt actual MEM resolution outputs and prove the source oracle rejects."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    base=ROOT/'build/frontend-mem-branch-component-v1';normal=json.loads((base/'results.json').read_text());binary=base/'test_branch';trace=base/'actual-branch.tsv'
    if sha(binary)!=normal['binary_sha256'] or sha(trace)!=normal['trace_sha256']:raise ValueError('normal branch proof changed')
    findings=[]
    for name,column in [('predictor_update',29),('mispredict',31),('next_pc',34)]:
        path=out/(name+'.tsv');changed=False
        with trace.open() as source,path.open('w') as dest:
            for line in source:
                row=list(map(int,line.split()))
                if row[28] and not changed:row[column]^=2 if column==34 else 1;changed=True
                dest.write(' '.join(map(str,row))+'\n')
        if not changed:raise ValueError('no selected branch control')
        r=subprocess.run([str(binary),str(path)],text=True,capture_output=True);(out/(name+'.stderr')).write_text(r.stderr)
        if r.returncode==0:raise ValueError('corruption accepted: '+name)
        findings.append(dict(name=name,rejected=True,return_code=r.returncode))
    paths=[Path(__file__).resolve(),base/'results.json',binary,trace]
    report=dict(schema='iris.frontend.mem_branch_rejections.v1',status='passed_all_actual_output_corruption_refusals',negative_controls=findings,input_sha256={str(p):sha(p) for p in paths},calibrated=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],rejected=len(findings))))
if __name__=='__main__':main()
