#!/usr/bin/env python3
"""Replay the exact qualified combined359 corpus, preserving every guest ELF."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import run_case

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    baseline=ROOT/'build/combined-functional/results.json';frozen=json.loads((ROOT/'build/combined-frozen-35901887/manifest.json').read_text());expected=frozen['local_receipts']['build/combined-functional/results.json']['sha256']
    if sha(baseline)!=expected:raise ValueError('frozen combined359 corpus receipt changed')
    old=json.loads(baseline.read_text());binary=a.binary.resolve();plugin=a.uart.resolve();identity=(sha(binary),sha(plugin));rows=[]
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);env.pop('IRIS_FATAL_PCS',None)
    for row in old['rows']:
        argv=list(row['argv']);argv[0]=str(binary);argv=['--extlib='+str(plugin) if x.startswith('--extlib=') else x for x in argv]
        if sha(argv[-1])!=row['elf_sha256']:raise ValueError('qualified corpus ELF changed: '+row['name'])
        case_env=dict(env);case_env.update(row.get('environment',{}))
        result=run_case(row['name'],argv,case_env,out,row['expected_exit_status'],timeout=180)
        diagnostics=row.get('expected_diagnostics',[])
        if diagnostics:
            text=(out/(row['name']+'.stderr')).read_text();result['pass'] &= all(x in text for x in diagnostics)
        result.update(expected_diagnostics=diagnostics,environment=row.get('environment',{}),qualified_parent_elf_sha256=row['elf_sha256'])
        rows.append(result)
        if not result['pass']:raise ValueError('qualified combined corpus failed: '+row['name'])
    if len(rows)!=32 or (sha(binary),sha(plugin))!=identity:raise ValueError('corpus count/paired native changed')
    inputs=[Path(__file__).resolve(),baseline,ROOT/'build/combined-frozen-35901887/manifest.json',ROOT/'spike/run_functional.py']
    report=dict(schema='iris.frontend.combined_corpus_replay.v1',status='passed_exact_combined359_functional32',binary_sha256=identity[0],uart_sha256=identity[1],rows=rows,input_sha256={str(p):sha(p) for p in inputs},
                old_5e6_negative_controls='build/frontend-values-inherited-negative-controls-v3/results.json',guest_elves_replaced=False,calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],cases=len(rows))))
if __name__=='__main__':main()
