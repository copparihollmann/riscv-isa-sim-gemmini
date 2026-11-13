#!/usr/bin/env python3
"""Strict numerical/protocol intake. Native execution is not target timing."""
import argparse
import hashlib
import json
from pathlib import Path
import re

def validate(text, packet):
    manifest = json.loads((packet/'manifest.json').read_text())
    host = json.loads((packet/'cases.json').read_text()); want = {c['id']:c for c in host}
    if len(want)!=len(host) or len(host)!=manifest['expected_regions']:raise ValueError('Invalid case inventory')
    if hashlib.sha256(Path(manifest['ELF']).read_bytes()).hexdigest()!=manifest['ELF_sha256']:
        raise ValueError('ELF changed')
    if manifest['negative_omitted_kernel']: raise ValueError('Negative-control packet cannot be admitted')
    for name, expected in manifest['input_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected: raise ValueError('Source changed: '+name)
    samples = {}; stages = {}; progress = []
    for line in text.splitlines():
        if line.startswith('IRIS_REGION '):
            r=json.loads(line.split(' ',1)[1]); key=r['case_id']
            if key not in want or key in samples: raise ValueError('Unknown/duplicate region '+key)
            if r.get('pass') is not True or r['hart']!=0 or r['region']!='memory_kernel' or r['warmup'] is not False:
                raise ValueError('Failed/foreign execution '+key)
            if r['checksum']!=want[key]['expected_checksums_by_hart'][0]: raise ValueError('Independent checksum mismatch '+key)
            if r['end_cycle']<=r['start_cycle'] or r['end_instret']<r['start_instret'] or r['instret_delta']!=r['end_instret']-r['start_instret']:
                raise ValueError('Invalid counters '+key)
            samples[key]=r
        elif line.startswith('IRIS_MEMROOF '):
            v=list(map(int,line.split()[1:]));
            if len(v)!=12:raise ValueError('Malformed typed memory record')
            i,rep,tier,kind,n,reps,pitch,rows,tb,te,checksum,status=v
            if i>=len(manifest['cases']) or rep not in [0,1,2]:raise ValueError('Unknown typed case')
            c=manifest['cases'][i];key=f'memroof_c{i}_r{rep}'
            if key in stages or [tier,kind,n,reps,pitch,rows]!=[c[k] for k in ['tier','kind','bytes','repeats','pitch','rows']] or status or te<tb or checksum!=c['expected_checksum']:
                raise ValueError('Bad typed evidence '+key)
            stages[key]=dict(case_index=i, pass_id=rep, mtime_before=tb, mtime_after=te)
        elif line.startswith('IRIS_PROGRESS v1 DONE '):
            _,_,_,count,key,checksum=line.split()
            if int(count)!=len(progress)+1 or key not in want or int(checksum)!=want[key]['expected_checksums_by_hart'][0] or key in progress:
                raise ValueError('Bad progress evidence')
            progress.append(key)
    if set(samples)!=set(want) or set(stages)!=set(want) or len(progress)!=len(want):raise ValueError('Incomplete corpus')
    if progress!=[c['id'] for c in host]:raise ValueError('Wrong execution order')
    if text.count(f'IRIS_PROGRESS v1 START {len(want)}')!=1:raise ValueError('Missing exact start')
    if text.count(f'IRIS_BATCH_DONE passed={len(want)} failed=0')!=1 or not re.search(r'^DONE$',text,re.M):raise ValueError('No exact completion')
    result=[]
    for row in host:
        key=row['id'];r=samples[key];s=stages[key];c=manifest['cases'][s['case_index']]
        cycles=r['end_cycle']-r['start_cycle']; inst=r['instret_delta']
        result.append(dict(**c, pass_id=s['pass_id'], cycles=cycles, instret=inst, ticks=s['mtime_after']-s['mtime_before'],
            requested_bytes_per_observed_cycle=c['requested_bytes']/cycles,
            cycles_per_dependent_load=cycles/c['dependent_loads'] if c['dependent_loads'] else None,
            physical_busy=None))
    return dict(schema='iris.memory_roofline_intake.v1', **{'pass':True}, regions=len(result),
        ELF_sha256=manifest['ELF_sha256'], samples=result, timing_scope='Only FPGA execution supplies target measurements; native results are functional evidence.')

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--packet',type=Path,required=True);p.add_argument('--console',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=validate(a.console.read_text(),a.packet);a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='samples'}))
