"""Emit one unaccepted linear proposal fixture, preserving every noneligible policy.
Requires the frozen TRAIN-only fit; actual full matched replay remains mandatory.
"""
import argparse,hashlib,json,math
from pathlib import Path
from rvv_identify_compact_fit_v1 import columns,PLAN_SHA
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def emit(fit,zero,out,identity):
 report=json.loads(fit.read_text());need(report['pass']is True and report['proposal_only']is True and report['coefficients_accepted']is False and report['plan_sha256']==PLAN_SHA and report['TRAIN_rows']==1410 and report['all_TRAIN_rows_retained']is True and report['protected_or_reserved_labels_consumed']is False,'Exact frozen TRAIN-only proposal')
 need(identity and not any(c.isspace()for c in identity),'Single-token experimental identity');models={};rules={}
 for core,harts in [('Shuttle',[0,1]),('Rocket',[2])]:
  m=report['models'][core];cols=columns(core);need(m['harts']==harts and m['rank']==len(cols)and m['identified']is True and m['columns']==[dict(family=f,basis=k)for f,k in cols]and len(m['coefficients'])==len(cols),'Exact predeclared identified columns');values=m['coefficients'];need(all(type(v)in(int,float)and math.isfinite(v)and v>=0 for v in values),'Nonnegative finite coefficients')
  families={}
  for(f,k),v in zip(cols,values):families.setdefault(f,dict(setup=0.0,work=0.0))['setup'if k=='instructions'else'work']=float(v)
  models[core]=families
  for h in harts:
   for f,v in families.items():rules[h,f]=v
 for p,h in report['input_sha256'].items():need(sha(p)==h,'Unchanged frozen fit input')
 out.mkdir(parents=True,exist_ok=False);params=dict(schema='iris.rvv_identify_compact_linear_runtime_proposal.v1',status='UNACCEPTED_REQUIRES_ACTUAL_MATCHED_REPLAY',plan_sha256=PLAN_SHA,TRAIN_fit_report_sha256=sha(fit),zero_fixture_sha256=sha(zero),models=models,units='500MHzcorecycles;setup/instruction+nativeWORKslope;noROIintercept',source_limits=report['source_limits'],protected_or_reserved_labels_consumed=False)
 (out/'parameters.json').write_text(json.dumps(params,indent=2)+'\n');ph=sha(out/'parameters.json');original=zero.read_text().splitlines();changed=[];seen=set();original_tokens=[]
 for line in original:
  t=line.split()
  if not t or t[0].startswith('#'):changed.append(line);continue
  original_tokens.append(t)
  if t[0]=='empirical_profile':need(len(t)==4,'Full bounded profile metadata');t[2]=identity;line=' '.join(t)
  elif t[0]=='empirical_family'and(int(t[1]),t[2])in rules:
   key=int(t[1]),t[2];need(key not in seen and len(t)==10 and float(t[4])==float(t[5])==0.0,'Eligible actualzero rule');seen.add(key);v=rules[key];t[4]=format(v['setup'],'.17g');t[5]=format(v['work'],'.17g');t[7]='OWN_COMPACT_TRAIN_LINEAR_PROPOSAL';t[8]=ph;line=' '.join(t)
  changed.append(line)
 missing=set(rules)-seen;need(missing<={(2,'rvv.integer')},'Only source-default Rocket integer rule can be absent')
 if missing:
  # Frozen native constructor configures empirical.vector2 count1; native async
  # default duration/work + interval1 uses this exact resource. No lane/II change.
  v=rules[2,'rvv.integer'];changed.append('empirical_family 2 rvv.integer empirical.vector2 '+format(v['setup'],'.17g')+' '+format(v['work'],'.17g')+' 1 OWN_COMPACT_TRAIN_LINEAR_PROPOSAL '+ph+' core_cycles')
 fixture=out/'runtime.fixture';fixture.write_text('\n'.join(changed)+'\n');proof=dict(schema='iris.rvv_identify_compact_fixture_mapping.v1',**{'pass':True},actual_replay_qualified=False,fixture_sha256=sha(fixture),parameters_sha256=ph,eligible_rules_written=len(rules),source_default_Rocket_integer_rule_added=bool(missing),all_other_costs_modes_resources_II_cache_history_and_ISA_unchanged=True,no_OPU_controller_or_MM_cost_fit=True,no_intercept_or_PC_case_lookup=True,input_sha256={str(p):sha(p)for p in[Path(__file__).resolve(),fit,zero,ROOT/'timing/rvv_identify_compact_fit_v1.py',ROOT/'calibration/rvv-identify-compact-v1/fit-plan.json']})
 (out/'mapping.json').write_text(json.dumps(proof,indent=2)+'\n');return proof
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--fit',type=Path,required=True);p.add_argument('--zero-fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--identity',required=True);a=p.parse_args();print(json.dumps(emit(a.fit.resolve(),a.zero_fixture.resolve(),a.output.resolve(),a.identity)))
