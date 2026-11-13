#!/usr/bin/env python3
"""Freeze semantic parent-group train/internal-validation before any fitting."""
import argparse,csv,hashlib,importlib.util,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('frozen split requires fresh directory')
 csvpath=R/'build/fpga-fit-observations-v1/regions.csv';base=R/'benchmarks/calibration-corpus.json';v2=R/'benchmarks/v2/corpus.json';memory=R/'benchmarks/memory_routes/cases.py';spec=importlib.util.spec_from_file_location('iris_memory_fit_cases',memory);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 cases={x['case_id']:{'suite':'baseline','family':x['kernel'],'metadata':x,'semantic':{'suite':'baseline','kernel':x['kernel'],'argument':x['argument'],'active_mask':x['active_hart_mask_expression']}}for x in json.loads(base.read_text())['cases']}
 for x in json.loads(v2.read_text())['cases']:
  if x.get('status')=='ready':cases[x['case_id']]={'suite':'distribution','family':x['kind'],'metadata':x,'semantic':{'suite':'distribution',**{k:x[k]for k in ['kind','n','mask','sew','lmul','mode','bytes','protocol','edge','tk','tiles']}}}
 for x in m.cases():cases[x['case_id']]={'suite':'memory','family':'route_'+x['kind'],'metadata':x,'semantic':{'suite':'memory',**{k:x[k]for k in ['kind','target_region','base','stride','spread','n','mask','node_count']}}}
 raw=list(csv.DictReader(csvpath.open()));observed=set(x['parent_case_id']for x in raw);assert len(raw)==6750 and observed<=cases.keys();split={};counts={}
 for name in sorted(observed):
  c=cases[name];group=digest(c['semantic']);partition='internal_validation'if int(group[:16],16)%5==0 else'train';split[name]={'semantic_group':group,'partition':partition,'suite':c['suite'],'family':c['family'],'semantic':c['semantic']};counts[partition]=counts.get(partition,0)+1
 rows=[]
 for x in raw:
  c=cases[x['parent_case_id']];s=split[x['parent_case_id']];rows.append({**x,**{k:int(x[k])for k in ['trial_id','hart','active_hart_mask','start_cycle','end_cycle','cycles','instret_delta']},'partition':s['partition'],'semantic_group':s['semantic_group'],'family':c['family'],'metadata':c['metadata']})
 out.mkdir();inputs={str(q):sha(q)for q in [Path(__file__),csvpath,R/'build/fpga-fit-observations-v1/report.json',base,v2,memory]};result={'schema':'iris.empirical_frozen_parent_split.v1','policy':'SHA256(canonical source-control semantics) mod5==0 internalvalidation; all trials/harts and exact semantic aliases share partition; targets not used','split':split,'parent_counts':counts,'observations':len(rows),'semantic_groups':len(set(x['semantic_group']for x in split.values())),'input_sha256':inputs,'global_heldout_metadata_or_timings_opened':False,'training_history':'trial0 retained; never a prediction feature; steady-parameter fitting may explicitly use1..4 with all5 reported','full_2pct_certified':False}
 (out/'split.json').write_text(json.dumps(result,indent=2)+'\n');(out/'observations.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n'for x in rows));print(json.dumps({'split_sha256':sha(out/'split.json'),'observations_sha256':sha(out/'observations.jsonl'),'parents':counts,'semantic_groups':result['semantic_groups']}))
if __name__=='__main__':main()
