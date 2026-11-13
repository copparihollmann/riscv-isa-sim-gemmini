#!/usr/bin/env python3
"""Retain every repetition and report variance without inventing timing goldens."""
import argparse,collections,json,statistics
from pathlib import Path
from validate import validate
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('Fresh summary path required')
 corpus=json.loads((a.build/'corpus.json').read_text());text=(a.run/'run.stdout').read_text();proof=validate(text,corpus);groups=collections.defaultdict(list)
 for line in text.splitlines():
  if line.startswith('IRIS_REGION '):
   x=json.loads(line.split(' ',1)[1]);groups[(x['suite'],x['parent_case_id'],x['hart'])].append({'trial_id':x['trial_id'],'cycles':x['end_cycle']-x['start_cycle'],'instret_delta':x['instret_delta'],'checksum':x['checksum']})
 rows=[]
 for (suite,parent,hart),samples in groups.items():
  samples.sort(key=lambda x:x['trial_id']);assert [x['trial_id'] for x in samples]==list(range(corpus['trials']));cycles=[x['cycles']for x in samples];mean=statistics.mean(cycles);rows.append({'suite':suite,'parent_case_id':parent,'hart':hart,'raw_samples':samples,'cycle_mean':mean,'cycle_min':min(cycles),'cycle_max':max(cycles),'cycle_population_stddev':statistics.pstdev(cycles),'cycle_coefficient_of_variation':statistics.pstdev(cycles)/mean})
 report={'schema':'iris.campaign_repetition_summary.v1','functional_proof':proof,'mode':'Local functional only; not RTL/FPGA timing','calibration_usable':False,'raw_samples_retained':True,'overhead_subtraction':False,'groups':rows};a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'groups':len(rows),'raw_samples':sum(len(x['raw_samples'])for x in rows),'calibration_usable':False}))
if __name__=='__main__':main()
