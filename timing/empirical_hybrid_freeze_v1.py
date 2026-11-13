#!/usr/bin/env python3
"""Select actual candidate on ALL TRAIN parents, then freeze final identity."""
import collections,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
source=ROOT/'calibration/compute-fit-7bd5-hybrid-proposal-v1';split=load(ROOT/'build/compute-fit-v3/split.json')['split'];reference=ROOT/'build/fpga-compute-fit-v1-001-analysis/regions.json';hw={(x['case_id'],x['hart']):x for x in load(reference)}
names=['proposal','grid-half_vector_memory','grid-more_vector_load','grid-data16','grid-legacy_front_cost'];scored=[];inputs={str(Path(__file__).resolve()):sha(__file__),str(reference):sha(reference)}
for name in names:
 run=ROOT/('build/compute-fit-7bd5-hybrid-'+name+'-v1');r=load(run/'run.json')
 if r.get('pass')is not True or r.get('regions')!=1008 or r.get('actual_CSR_ELF_boundary_joins')!=2016:raise ValueError('Actual complete candidate replay required')
 for p,h in {**r['input_sha256'],**r['output_sha256']}.items():
  if sha(p)!=h:raise ValueError('Candidate evidence changed')
 groups=collections.defaultdict(list)
 for x in map(json.loads,(run/'regions.jsonl').read_text().splitlines()):
  if split[x['parent_case_id']]['partition']!='train':continue
  y=hw[x['case_id'],x['hart']];groups[x['parent_case_id'],x['hart']].append((x['end_cycle']-x['start_cycle'])/(y['end_cycle']-y['start_cycle'])-1)
 if len(groups)!=272 or any(len(v)!=3for v in groups.values()):raise ValueError('All272TRAIN groups, including polling/atomic, required')
 score=statistics.mean(statistics.median(v)**2for v in groups.values());scored.append({'candidate':name,'TRAIN_all_parent_hart_MSE':score,'run':str(run/'run.json'),'run_sha256':sha(run/'run.json')})
 for path in(run/'run.json',run/'regions.jsonl'):inputs[str(path)]=sha(path)
best=min(scored,key=lambda x:x['TRAIN_all_parent_hart_MSE']);selected=ROOT/('calibration/compute-fit-7bd5-hybrid-'+best['candidate']+'-v1');out=ROOT/'calibration/compute-fit-7bd5-hybrid-selected-v1';out.mkdir(exist_ok=False)
p=load(selected/'parameters.json');old=sha(selected/'parameters.json');p['calibration_identity']='iris-empirical-hybrid7bd5-compute-v1';p['own_epoch_training_selection']={'objective':'mean squared median per-trial relative error over ALL272TRAIN parent/hart groups','training_regions':816,'excluded_families':[],'internal_validation_used':False,'global_heldout_used':False,'selected_candidate':best,'candidates':scored};p['actual_calibrated_native_replay_completed']=False
for r in p['families']:
 if r['work']<1e-9:r['work']=0
 if r['hart']==2and r['family'].startswith('rvv.fadd.'):r['resource']='fit.hybrid.sharedFPU2'
p['source_fit_scope']='Own7bd5zero-compute-cost baseline, nonnegative normalizedNNLS onALLTRAIN, then actual generic live cost-grid selection. No coefficient qualification transferred.'
p['unqualified']+=['Finalidentity replay still pending at parameter freeze; binding records actual success separately.','Sourcefrontend/scalarFADD/shape/storefront modes are OFF in this explicit legacy28-mode packet.','A logical sharedFPUresource label does not establish a physically qualified shared-port timing model.']
p['input_sha256'].update(inputs);p['input_sha256'][str(selected/'parameters.json')]=old
(out/'parameters.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n');digest=sha(out/'parameters.json');rules={(r['hart'],r['family']):r for r in p['families']};lines=[]
for l in(selected/'runtime.fixture').read_text().splitlines():
 f=l.split()
 if not f:lines.append(l);continue
 if f[0]=='empirical_profile':f[2]=p['calibration_identity']
 if f[0]=='empirical_family'and(int(f[1]),f[2])in rules:
  r=rules[int(f[1]),f[2]];f[3]=r['resource'];f[4]=format(r['setup'],'.12g');f[5]=format(r['work'],'.12g')
 f=[digest if x==old else x for x in f];lines.append(' '.join(f))
lines.append('resource fit.hybrid.sharedFPU2 1');(out/'runtime.fixture').write_text('\n'.join(lines)+'\n')
report={'schema':'iris.own_hybrid_final_training_selection.v1','actual_parameter_fit_performed':True,'selected_candidate':best,'all_candidates':scored,'selection_uses_internal_validation':False,'selection_uses_global_heldout':False,'all_TRAIN_families_included':True,'training_regions':816,'training_parent_hart_groups':272,'parameters_sha256':digest,'fixture_sha256':sha(out/'runtime.fixture'),'final_identity_actual_native_validation_pending':True,'input_sha256':{**inputs,str(selected/'parameters.json'):old,str(selected/'runtime.fixture'):sha(selected/'runtime.fixture'),str(ROOT/'build/compute-fit-v3/split.json'):sha(ROOT/'build/compute-fit-v3/split.json')}}
(out/'selection.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'selected':best,'fixture_sha256':sha(out/'runtime.fixture'),'parameters_sha256':digest,'output':str(out)}))
