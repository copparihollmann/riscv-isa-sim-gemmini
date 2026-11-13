"""Frozen-plan TRAIN-only linear proposal over an actual own zero-adjustment replay.
No intercepts, hardware policy fit, mode search, reserved labels, or acceptance claim.
"""
import argparse,hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FAMILIES=['rvv.integer','rvv.fadd.fp16','rvv.fadd.fp32','rvv.fadd.fp64','memory.vector.load','memory.vector.store','vme.row_move']
PLAN_SHA='b6e4d6dd50aff833875479f2482462450cc40698fab483bcd6506e767e599e35'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def readrows(p):return [json.loads(l)for l in Path(p).read_text().splitlines()]
def columns(core):return [(f,k)for f in FAMILIES if not(core=='Rocket'and f=='vme.row_move')for k in(['instructions']if f=='vme.row_move'else['instructions','work'])]
def rank(x):
 if not x:return 0
 n=len(x[0]);norm=[math.sqrt(sum(r[j]**2 for r in x))for j in range(n)];a=[[r[j]/(norm[j]or 1)for j in range(n)]for r in x];row=0
 for col in range(n):
  pivot=max(range(row,len(a)),key=lambda i:abs(a[i][col]),default=row)
  if row>=len(a)or abs(a[pivot][col])<1e-10:continue
  a[row],a[pivot]=a[pivot],a[row];v=a[row][col];a[row]=[v0/v for v0 in a[row]]
  for i in range(row+1,len(a)):
   v=a[i][col]
   if v:a[i]=[u-v*w for u,w in zip(a[i],a[row])]
  row+=1
  if row==len(a):break
 return row
def nnls(x,y):
 n=len(x[0]);beta=[0.0]*n;res=list(y);norm=[sum(r[j]*r[j]for r in x)for j in range(n)];need(all(v>0 for v in norm),'Identified nonzero columns')
 for iteration in range(10000):
  change=0
  for j in range(n):
   step=sum(r[j]*v for r,v in zip(x,res))/norm[j];new=max(0.0,beta[j]+step);delta=new-beta[j];beta[j]=new;change=max(change,abs(delta))
   if delta:res=[v-r[j]*delta for r,v in zip(x,res)]
  if change<=1e-12:break
 need(change<=1e-12,'Fixed NNLS did not converge')
 return beta,dict(iterations=iteration+1,converged=True,max_coefficient_delta=change,relative_squared_residual=sum(v*v for v in res))
def basis(zero,build):
 run=json.loads((zero/'run.json').read_text());need(run['pass']is True and run['regions']==1908 and run['actual_CSR_ELF_endpoint_joins']==5724,'Own complete zero replay')
 for p,h in {**run['input_sha256'],**run['output_sha256']}.items():need(sha(p)==h,'Exact zero replay inputs/outputs')
 c=json.loads((build/'corpus.json').read_text());need(len(c['cases'])==1908 and sum(r['internal_split']=='train'for r in c['cases'])==1410,'Exact1908/1410 corpus');rows=readrows(zero/'regions.jsonl');need(len(rows)==1908,'All1908 native records');prefix={}
 for p in readrows(zero/'features.jsonl'):
  key=(p['hart'],p['value']);need(key not in prefix,'Unique actual CSR observation');prefix[key]=p
 need(len(prefix)==5724,'Exactly5724 actual prefixes');out=[]
 for case,r in zip(c['cases'],rows):
  need(r['case_id']==case['case_id']and r['hart']==case['hart']and r['trial_id']==case['trial_id']and r['pass']is True,'Compiled actual role/order/golden')
  points=[prefix[(r['hart'],r[k])]for k in('start_cycle','issue_cycle','end_cycle')];features={}
  for f in FAMILIES:
   v={}
   for k in('instructions','work'):
    a=points[0]['features'].get(f,{}).get(k,0);b=points[2]['features'].get(f,{}).get(k,0);need(type(a)is int and type(b)is int and 0<=a<=b,'Monotone actual family prefixes');v[k]=b-a
   features[f]=v
  out.append(dict(case_id=r['case_id'],hart=r['hart'],trial_id=r['trial_id'],internal_split=case['internal_split'],native_total_cycles=r['end_cycle']-r['start_cycle'],native_issue_cycles=r['issue_cycle']-r['start_cycle'],native_drain_cycles=r['end_cycle']-r['issue_cycle'],features=features))
 return out,run,c

def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);plan=ROOT/'calibration/rvv-identify-1908-v1/fit-plan.json';need(sha(plan)==PLAN_SHA,'Frozen plan identity');zero=a.zero.resolve();build=a.build.resolve();rows,run,c=basis(zero,build);inputs={str(p):sha(p)for p in[Path(__file__).resolve(),plan,build/'ready.json',build/'corpus.json',zero/'run.json',zero/'regions.jsonl',zero/'features.jsonl']};models={};native={r['case_id']:r for r in rows};train=None
 if a.train is not None:
  directory=a.train.resolve();receipt=json.loads((directory/'report.json').read_text());need(receipt.get('status')=='passed'and receipt['regions']==1410 and receipt['reserved_timing_labels_excluded']is True and receipt['ELF_sha256']==sha(build/'guest.elf')and receipt['regions_sha256']==sha(directory/'regions.jsonl'),'Strict new1410 TRAIN export receipt');train=readrows(directory/'regions.jsonl');want=[r['case_id']for r in rows if r['internal_split']=='train'];need([r['case_id']for r in train]==want,'Every TRAIN row/repetition in canonical order, no filtering');inputs.update({str(p):sha(p)for p in(directory/'report.json',directory/'regions.jsonl')})
  for r in train:
   n=native[r['case_id']];need(r['internal_split']=='train'and r['hart']==n['hart']and r['trial_id']==n['trial_id']and type(r['cycles'])is int and r['cycles']>0 and r['pass']is True,'Typed actual matching TRAIN row');need(type(r['issue_cycles'])is int and type(r['drain_cycles'])is int and r['issue_cycles']+r['drain_cycles']==r['cycles'],'Actual hardware phase deltas')
 for core,harts in [('Shuttle',[0,1]),('Rocket',[2])]:
  cols=columns(core);selected=[r for r in rows if r['hart']in harts and r['internal_split']=='train'];x=[[r['features'][f][k]for f,k in cols]for r in selected];rnk=rank(x);need(rnk==len(cols),'Predeclared source feature rank deficient')
  model=dict(harts=harts,TRAIN_rows=len(selected),columns=[dict(family=f,basis=k)for f,k in cols],rank=rnk,identified=True)
  if train is not None:
   hardware={r['case_id']:r for r in train};target=[hardware[r['case_id']]['cycles']for r in selected];weighted=[[v/y for v in row]for row,y in zip(x,target)];residual=[(y-r['native_total_cycles'])/y for r,y in zip(selected,target)];beta,fit=nnls(weighted,residual);model.update(coefficients=beta,fit=fit,negative_residual_rows=sum(y<r['native_total_cycles']for r,y in zip(selected,target)),zero_feature_rows=sum(not any(r)for r in x))
  models[core]=model
 (out/'basis.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));report=dict(schema='iris.rvv_identify_1908_TRAIN_linear_proposal.v1',**{'pass':True},proposal_only=True,actual_fitted_replay_required=True,coefficients_accepted=False,protected_or_reserved_labels_consumed=False,plan_sha256=PLAN_SHA,all_TRAIN_rows_retained=True,TRAIN_rows=1410,models=models,input_sha256=inputs,zero_adjustment_identity=run['calibration_identity'],output_basis_sha256=sha(out/'basis.jsonl'),estimator='Nonnegative relativeLS;coordinate-descent tolerance1e-12/max10000;no intercepts/no grid;rowmoveWORK0',source_limits='WholeVRFowner/blockedvector memory/partialgroupchaining/OPUbridge not repaired by coefficients;negative residuals remain')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,TRAIN_rows=1410,models=models,report_sha256=sha(out/'report.json'))))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--zero',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--train',type=Path);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
