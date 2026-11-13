#!/usr/bin/env python3
"""Independent geometry/split/invariance and corruption checks for the CPU fit."""
import copy,hashlib,json,pathlib,tempfile
import empirical_cpu_layout_fit as fit
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 out=ROOT/'build/cpu-layout-fit-verification-v1';out.mkdir(exist_ok=False)
 rows,split=fit.load(ROOT/'build/fpga-cpu-layout-v2-001-analysis/regions.csv',ROOT/'calibration/cpu-layout-v2/split.json')
 p=ROOT/'calibration/cpu-layout-fit-v1';params=json.load((p/'parameters.json').open());report=json.load((p/'report.json').open());pred=json.load((p/'predictions.json').open())
 checks=0;refusals=[]
 def check(v):
  nonlocal checks
  if not v:raise AssertionError('Independent check '+str(checks))
  checks+=1
 for r in rows:
  if r['mode']=='noop':continue
  word=8 if r['hart']<2 else 4;floor=2 if r['hart']<2 else 3
  lens=[2,2,4] if r['mode']=='compact' else [4,4,4]
  # Enumerate every instruction byte instead of using endpoint division.
  words=set();pc=r['loop_pc']
  for n in lens:
   words.update(a//word for a in range(pc,pc+n));pc+=n
  expected=[float(r['n']),float(r['n']*max(0,len(words)-floor)),1.]
  check(fit.features(r)==expected)
  other=dict(r,case_id='opaque-other-name',parent_case_id='opaque-parent',loop_pc=r['loop_pc']+0x400000,repeat=(r['repeat']+1)%3)
  check(fit.features(r)==fit.features(other))
  check(fit.prediction(r,params['models'])==fit.prediction(other,params['models']))
 # Actual source geometry yields no compact-loop steady layout penalty at ANY offset.
 for h in range(3):
  for off in range(0,64,2):
   compact={'hart':h,'mode':'compact','loop_pc':0x80000000+off,'n':256}
   wide=dict(compact,mode='wide')
   check(fit.features(compact)[1]==0)
   check(fit.features(wide)[1]==(256. if (off%8==6 if h<2 else off%4==2) else 0.))
 # Validate grouping, no alias/repeat/hart leakage; no-op is never a fit row.
 parents={}
 for r in rows:
  key=r['loop_offset'] if r['mode']!='noop' else 'control'
  parents.setdefault(key,set()).add(r['partition'])
 check(all(len(p)==1 for p in parents.values()))
 check(sum(r['partition']=='train' for r in rows)==1584)
 check(sum(r['partition']=='internal_validation' for r in rows)==720)
 check(sum(r['partition']=='control' for r in rows)==9)
 for name,hs in [('shuttle',(0,1)),('rocket',(2,))]:
  eligible=[r for r in rows if r['partition']=='train' and r['hart'] in hs and r['n']>=64 and r['repeat']>0 and r['mode']!='noop']
  c,rank=fit.robust_fit(eligible)
  check(rank==3 and c==params['models'][name]['coefficients'])
  # Poison every CV timing by a huge amount: training inputs/results stay identical.
  poison=[dict(r,cycles=10**15) if r['partition']=='internal_validation' else dict(r) for r in rows]
  eligible2=[r for r in poison if r['partition']=='train' and r['hart'] in hs and r['n']>=64 and r['repeat']>0 and r['mode']!='noop']
  check(fit.robust_fit(eligible2)==(c,rank))
  check(abs(c[0]-(2 if name=='shuttle' else 3))<.001 and abs(c[1]-1)<.01)
 for value in (True,False,-1,'1.5','-2'):
  try:fit.checked_int(value,'negative-control')
  except ValueError:refusals.append({'invalid_integer':repr(value),'rejected':True})
  else:raise AssertionError('Malformed integer accepted')
 with tempfile.TemporaryDirectory() as td:
  td=pathlib.Path(td);csv=td/'rows.csv';csv.write_bytes((ROOT/'build/fpga-cpu-layout-v2-001-analysis/regions.csv').read_bytes().replace(b',782,',b',783,',1))
  check(sha(csv)!=fit.CSV_SHA)
  try:fit.load(csv,ROOT/'calibration/cpu-layout-v2/split.json')
  except ValueError:refusals.append({'corrupted_reference_cycle':'rejected'})
  else:raise AssertionError('Changed reference accepted')
 check(pred['parameters_sha256']==sha(p/'parameters.json'))
 check(report['predictions_sha256']==sha(p/'predictions.json'))
 check(report['input_sha256']['timing/empirical_cpu_layout_fit.py']==sha(ROOT/'timing/empirical_cpu_layout_fit.py'))
 check(report['internal_validation']['all']['count']==720)
 check(report['full_2pct_certified'] is False and report['live_native_quality_certified'] is False)
 check(report['internal_validation']['all']['absolute_error_max_pct']>90)
 check(report['internal_validation']['N_ge_64_repeat1_2']['within_2pct_count']<360)
 result={'schema':'iris.empirical_cpu_layout_independent_verification.v1','status':'passed','checks':checks,'negative_controls':refusals,
  'input_sha256':{str(f.relative_to(ROOT)):sha(f) for f in [pathlib.Path(__file__).resolve(),ROOT/'timing/empirical_cpu_layout_fit.py',p/'parameters.json',p/'predictions.json',p/'report.json',ROOT/'calibration/cpu-layout-v2/split.json']},
  'hardware_contacted':False,'global_heldout_timings_consumed':False,'native_timing_binding_verified':False,'full_2pct_certified':False}
 (out/'report.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2));print('SHA',sha(out/'report.json'))
if __name__=='__main__':main()
