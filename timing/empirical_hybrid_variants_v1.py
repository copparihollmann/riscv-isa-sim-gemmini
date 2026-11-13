#!/usr/bin/env python3
"""Freeze a small generic mechanism grid before actual TRAIN-only selection."""
import copy,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=ROOT/'calibration/compute-fit-7bd5-hybrid-proposal-v1';original=json.loads((base/'parameters.json').read_text());old=sha(base/'parameters.json')
variants={'half_vector_memory':(.5,.5,None,None),'more_vector_load':(1.5,1,None,None),'data16':(1,1,16,None),'legacy_front_cost':(1,1,None,'legacy')}
for name,(load,store,data,front)in variants.items():
 out=ROOT/('calibration/compute-fit-7bd5-hybrid-grid-'+name+'-v1');out.mkdir(exist_ok=False);p=copy.deepcopy(original);p['calibration_identity']='iris-hybrid7bd5-grid-'+name+'-v1';p['live_train_grid']={'name':name,'load_scale':load,'store_scale':store,'data_read_and_L1miss_candidate':data,'frontend_candidate':front,'selection_uses_CV':False};p['input_sha256'][str(Path(__file__).resolve())]=sha(__file__)
 for r in p['families']:
  if r['family']=='memory.vector.load':r['setup']*=load;r['work']*=load
  if r['family']=='memory.vector.store':r['setup']*=store;r['work']*=store
  if r['work']<1e-9:r['work']=0
 if front:
  p['branch']={'0':2,'1':2,'2':5};p['instruction_l1_extra']={'0':32,'1':32,'2':45}
 if data:p['data_service_candidate']={'read_base':data,'L1miss':data,'write_base':0,'outer_miss':545.732041126,'outer_interval':461,'dirty':0}
 (out/'parameters.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n');digest=sha(out/'parameters.json');rules={(r['hart'],r['family']):r for r in p['families']};lines=[]
 for line in(base/'runtime.fixture').read_text().splitlines():
  f=line.split()
  if not f:lines.append(line);continue
  if f[0]=='empirical_profile':f[2]=p['calibration_identity']
  if f[0]=='empirical_family'and(int(f[1]),f[2])in rules:
   r=rules[int(f[1]),f[2]];f[4]=format(r['setup'],'.12g');f[5]=format(r['work'],'.12g')
  if f[0]=='empirical_instruction_service':f[2]=str(p['instruction_l1_extra'][f[1]])
  if f[0]=='empirical_branch_service':f[2]=str(p['branch'][f[1]])
  if f[0]=='empirical_cache_service'and data:f[2]=str(data);f[4]=str(data);f[-3]='OWN_HYBRID_TRAIN';f[-2]=digest
  f=[digest if x==old else x for x in f];lines.append(' '.join(f))
 (out/'runtime.fixture').write_text('\n'.join(lines)+'\n');(out/'derivation.json').write_text(json.dumps({'schema':'iris.generic_TRAIN_grid_candidate.v1','parent_parameters_sha256':old,'parameters_sha256':digest,'fixture_sha256':sha(out/'runtime.fixture'),'no_runtime_case_ID_or_PC_lookup':True,'fitting_uses_global_heldout':False,'fitting_uses_CV':False,'input_sha256':{str(base/'parameters.json'):old,str(base/'runtime.fixture'):sha(base/'runtime.fixture'),str(Path(__file__).resolve()):sha(__file__)}},indent=2)+'\n');print(name,sha(out/'runtime.fixture'))
