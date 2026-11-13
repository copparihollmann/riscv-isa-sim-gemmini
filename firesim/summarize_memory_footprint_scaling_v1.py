#!/usr/bin/env python3
"""Summarize observed loop costs, without labeling them physical memory latency."""
import argparse,csv,json,statistics,hashlib
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def summarize(analysis,job,out):
 report=json.loads((analysis/'report.json').read_text());assert report['pass']is True and report['regions']==360
 rows=json.loads((analysis/'regions.json').read_text());m=json.loads((job/'run.json').read_text());assert m['capture']['archive_sha256']==report['archive_sha256'];cases={c['id']:c for c in m['cases']};assert len(cases)==210
 table=[]
 for size in [2048,16384,131072,1048576,4194304]:
  for h in range(3):
   for mode in ['solo','all3']:
    mask=(1<<h)if mode=='solo'else 7
    for passed in [0,1]:
     a=[r for r in rows if r['footprint_bytes']==size and r['hart']==h and r['pass_index']==passed and sum(1<<v for v in cases[r['case_id']]['active_harts'])==mask];assert len(a)==3 and {r['trial_id']for r in a}=={0,1,2}
     table.append(dict(footprint_bytes=size,hart=h,active_mask=mask,cohort=mode,pass_index=passed,trials=3,median_raw_region_cycles=statistics.median(r['cycles']for r in a),median_raw_cycles_per_body_LD=statistics.median(r['cycles']/r['body_loads']for r in a),min_raw_cycles_per_body_LD=min(r['cycles']/r['body_loads']for r in a),max_raw_cycles_per_body_LD=max(r['cycles']/r['body_loads']for r in a),median_instret_per_body_LD=statistics.median(r['instret_delta']/r['body_loads']for r in a),median_CLINT_bracket_ticks=statistics.median(r['mtime_delta']for r in a)))
 out.mkdir(parents=True,exist_ok=False)
 with(out/'scaling.csv').open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
 paths=[Path(__file__).resolve(),analysis/'report.json',analysis/'regions.json',job/'run.json'];inputs={str(p):sha(p)for p in paths}
 result=dict(schema='iris.memory_footprint_measured_scaling.v1',hardware_reference=True,cohorts=60,regions=360,table=table,measurement='mcycle region cycles/body LD count; includes loop/call/CSR/fence overhead, no subtraction',physical_cache_miss_or_DRAM_latency_identified=False,physical_bandwidth_measured=False,clock_alignment='CLINT brackets;±1000source-core-cycle quantization plus outside-ROI sampling overhead',source_image_association_verified=False,timing_accuracy_certified=False,input_sha256=inputs,output_sha256={'scaling.csv':sha(out/'scaling.csv')})
 assert all(sha(p)==h for p,h in inputs.items());(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 print('Pass1 median raw cycles/bodyLD (includes loop and counter overhead):')
 for size in [2048,16384,131072,1048576,4194304]:
  print(size,{mode:[round(next(r['median_raw_cycles_per_body_LD']for r in table if r['footprint_bytes']==size and r['hart']==h and r['cohort']==mode and r['pass_index']==1),3)for h in range(3)]for mode in ['solo','all3']})
 print('report_sha256',sha(out/'report.json'))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--job',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();summarize(a.analysis.resolve(),a.job.resolve(),a.output.resolve())
