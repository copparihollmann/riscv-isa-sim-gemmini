#!/usr/bin/env python3
"""Fit positive generic costs on ALL TRAIN parents of this own native epoch.

No case IDs, PCs, shapes, labels or reference cycles enter a runtime rule.
Parent identifiers only keep repetitions together for the training objective.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import statistics
import numpy as np
from empirical_fit import nnls

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def feature(row):
 values={}
 for family,x in row['features'].items():
  if family.startswith(('rvv.','vme.','memory.vector.','scalar.fp')):
   values[family+'.instructions']=float(x['instructions'])
   if not family.startswith('scalar.fp'):values[family+'.work']=float(x['work'])
 for path,x in row.get('memory',{}).items():
  if path=='ICACHE.DRAM':values['icache.l1misses']=float(x.get('l1misses',0))
 # Costs act only on actual runtime history, never static branch/case labels.
 values['branch.mispredicts']=float(row.get('branch_history',{}).get('resolved_mispredicts',0))
 return values


def main():
 p=argparse.ArgumentParser(__doc__)
 for n in('features','baseline-fixture','native-receipt','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--identity',required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 joined=json.loads(a.features.with_name('report.json').read_text());receipt=json.loads(a.native_receipt.read_text())
 if joined.get('pass')is not True or receipt.get('pass')is not True or receipt.get('regions')!=1008:raise ValueError('Own all1008 execution and features required')
 rows=[json.loads(x)for x in a.features.read_text().splitlines()]
 train=[x for x in rows if x['partition']=='train']
 if len(train)!=816:raise ValueError('Exact816TRAIN rows required')
 groups=collections.defaultdict(list)
 for row in train:groups[row['parent_case_id'],row['hart']].append(row)
 if len(groups)!=272:raise ValueError('All272TRAIN parent/hart groups required')
 models={};rules=[];instruction={};branch={}
 for cls in('shuttle','rocket'):
  points=[]
  for values in groups.values():
   if('shuttle'if values[0]['hart']<2 else'rocket')!=cls:continue
   fs=[feature(r)for r in values];names={k for f in fs for k in f};x={k:statistics.median(f.get(k,0)for f in fs)for k in names}
   points.append((values,x,statistics.median(r['reference_cycles']for r in values),statistics.median(r['native_cycles']for r in values)))
  names=sorted({k for _,f,_,_ in points for k,v in f.items()if v>0})
  matrix=np.array([[f.get(k,0)for k in names]for _,f,_,_ in points]);reference=np.array([r for _,_,r,_ in points]);baseline=np.array([b for _,_,_,b in points])
  coef=nnls(matrix,reference-baseline,1/np.maximum(reference,1))
  coefficients=dict(zip(names,map(float,coef)));rank=int(np.linalg.matrix_rank(matrix))
  models[cls]={'coefficients':coefficients,'training_parent_ids':sorted({r['parent_case_id']for v,_,_,_ in points for r in v}),
   'groups':len(points),'rank':rank,'columns':len(names),'coefficients_separately_identifiable':rank==len(names),
   'all_training_families_included':True,'objective':'mean squared normalized residual across all TRAIN parent/hart trial medians',
   'scalar_baseline_scale':1,'ROI_intercept':0}
  families=sorted({f for r in train if('shuttle'if r['hart']<2 else'rocket')==cls for f,v in r['features'].items()if v['instructions']and f.startswith(('rvv.','vme.','memory.vector.','scalar.fp'))})
  for hart in ((0,1)if cls=='shuttle'else(2,)):
   instruction[str(hart)]=max(0,int(round(coefficients.get('icache.l1misses',0))))
   branch[str(hart)]=max(0,int(round(coefficients.get('branch.mispredicts',0))))
   for f in families:
    setup=coefficients.get(f+'.instructions',0);work=coefficients.get(f+'.work',0)
    # Async extras are charged per accepted instruction with integer ceil.
    # Select a nonnegative integer setup/work pair on TRAIN observations only.
    if f.startswith(('rvv.','vme.')):
     relevant=[(x,r)for _,x,r,_ in points if x.get(f+'.instructions',0)]
     candidates=[]
     for s in range(13):
      for w in range(5):
       loss=sum(((s*x.get(f+'.instructions',0)+w*x.get(f+'.work',0)-setup*x.get(f+'.instructions',0)-work*x.get(f+'.work',0))/r)**2 for x,r in relevant)
       candidates.append((loss,s+w,s,w))
     _,_,setup,work=min(candidates)
    if setup+work<=1e-10:continue
    domain='memory'if f.startswith('memory.vector.')else'scalarFP'if f.startswith('scalar.fp')else'vme'if f.startswith('vme.')else'vectorFP'if f.startswith('rvv.fadd.')else'vector'
    rules.append({'hart':hart,'family':f,'setup':setup,'work':work,'interval':1,'resource':'fit.hybrid.'+domain+str(hart)})
 source_inputs={str(p.resolve()):sha(p)for p in(Path(__file__),a.features,a.features.with_name('report.json'),a.native_receipt,a.baseline_fixture,ROOT/'build/compute-fit-v3/split.json')}
 parameters={'schema':'iris.empirical_compute_selected_parameters.v1','actual_parameter_fit_performed':True,'actual_calibrated_native_replay_completed':False,
  'calibration_identity':a.identity,'native_binary_sha256':joined['native_binary_sha256'],'uart_library_sha256':sha(Path(receipt['argv'][0]).with_name('libsifive_uart.so')),
  'base_hz':500000000,'rtc_divider':1000,'counter_policy':'source-ungated-stall','models':models,'families':rules,'branch':branch,'instruction_l1_extra':instruction,
  'fit_parent_ids':sorted({x['parent_case_id']for x in train}),'training_rows':816,'training_parent_hart_groups':272,'excluded_training_families':[],
  'own_native_epoch_fit_and_runtime_validation':False,'source_model_scope':'Explicit legacy28 approximate CPU/frontend modes plus response-owned V8 cache read overlap; source frontend/scalarFADD/shape/storefront flags absent.',
  'cost_semantics':{'async':'Positive integer setup+runtime-work extra over own native zero-compute-cost baseline.','scalar_FP':'Effective extra conservative instruction duration; not source pipeline latency.','memory_vector':'Additional setup/work with fractional accumulation; source transport outer reservation retained.','branch':'Extra recovery on actual runtime BHT misses.','instruction':'Extra per actual Icache L1 miss; fixed shared-outer prior preserved.'},
  'prior_memory_parameters':'Exact prior28outer/TCM/scratch values, not identified or fitted by this new compute corpus.',
  'selection_uses_internal_validation':False,'global_heldout_timings_consumed':False,'full_model_certified':False,'full_2pct_certified':False,'source_image_association_verified':False,
  'unqualified':['Linear overlap approximation requires actual native replay.','Physical per-level memory latency/bandwidth and issue interval are not individually identified.','All atomic/polling families are included in the training objective, even where no adjustable feature changes their floor.','Internal CV was viewed earlier in development; it is not blind validation.'],'input_sha256':source_inputs,'native_inputs_sha256':receipt['input_sha256']}
 (out/'parameters.json').write_text(json.dumps(parameters,indent=2,sort_keys=True)+'\n');digest=sha(out/'parameters.json')
 lines=[]
 for line in a.baseline_fixture.read_text().splitlines():
  f=line.split()
  if f and f[0]in('empirical_instruction_service','empirical_branch_service'):continue
  if f and f[0]=='empirical_profile':f[2]=a.identity;line=' '.join(f)
  lines.append(line)
 lines+=['resource '+r+' 1'for r in sorted({r['resource']for r in rules})]
 for h in range(3):
  lines += [f'empirical_instruction_service {h} {instruction[str(h)]} 545.732041126 461 OWN_HYBRID_TRAIN {digest} core_cycles',f'empirical_branch_service {h} {branch[str(h)]} OWN_HYBRID_TRAIN {digest} core_cycles']
 for r in rules:lines.append('empirical_family '+str(r['hart'])+' '+r['family']+' '+r['resource']+' '+' '.join(format(r[k],'.12g')for k in('setup','work','interval'))+' OWN_HYBRID_TRAIN '+digest+' core_cycles')
 (out/'runtime.fixture').write_text('\n'.join(lines)+'\n')
 report={'schema':'iris.own_hybrid_training_fit.v1','actual_parameter_fit_performed':True,'actual_candidate_runtime_validation_performed':False,'training_regions':816,'training_parent_hart_groups':272,'all_training_families_included':True,'atomic_and_polling_included':True,'fitting_uses_CV':False,'fitting_uses_global_heldout':False,'parameters_sha256':digest,'fixture_sha256':sha(out/'runtime.fixture'),'models':models,'input_sha256':source_inputs}
 (out/'fit-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'rules':len(rules),'fixture_sha256':sha(out/'runtime.fixture'),'output':str(out)}))


if __name__=='__main__':main()
