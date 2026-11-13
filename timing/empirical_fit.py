#!/usr/bin/env python3
"""Train-only nonnegative effective-cost fit; validation is a separate invocation.

Features describe operations and physical address paths, never benchmark IDs/PCs.
The region feature compiler is an audit proxy, not a substitute for live features.
"""
import argparse, collections, csv, hashlib, json, math, pathlib, statistics
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[1]

def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,x): pathlib.Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def core(r): return 'shuttle' if r['hart']<2 else 'rocket'
def pop(x): return bin(int(x)).count('1')
def model_features(r):
    m=r['metadata'];f=r['family'];c=core(r);n=m.get('n',0)
    cpu=.6 if c=='shuttle' else 1.
    base=cpu*r['instret_delta']
    if r['suite']=='distribution' and f in ('dependent','independent'):
        return 'cpu/'+c,0.,{'instructions':r['instret_delta'],'dependent_alu_ops':8*n if f=='dependent' else 0.}
    if r['suite']=='memory':
        target=m['target_region']
        path=('local_tcm' if target=='tcm'+str(r['hart']) else 'remote_tcm') if target.startswith('tcm') else target
        access=n if m['kind']=='chase' else n*m['node_count']
        h=r['hart'];mask=r['active_hart_mask'];others=[j for j in range(3) if j!=h and mask&(1<<j)]
        mybanks=set(m['bank_bit6_sequence_by_hart'][h]);same=0;different=0
        for j in others:
            peer=set(m['bank_bit6_sequence_by_hart'][j])
            if mybanks&peer:same+=1
            else:different+=1
        return 'memory/'+c+'/'+path+'/'+m['kind'],base,{
          'accesses':access,'same_bank_peer_accesses':access*same,
          'other_bank_peer_accesses':access*different,
          'multi_bank_accesses':access if len(mybanks)>1 else 0}
    if r['suite']!='distribution':return None
    if f=='scalar_fp':
        return 'scalar_fp/'+c+'/e'+str(m['sew']),base,{'operations':n}
    if f in ('vector_int','vector_fp'):
        streams=1+int(bool(m['mode'])) if f=='vector_int' else 1
        ops=n*streams;beats=m['lmul']*(2 if c=='shuttle' else 1)
        # Group precision only where its source datapath differs (FP).
        kind='integer' if f=='vector_int' else 'fp'+str(m['sew'])
        return 'vector/'+c+'/'+kind,base,{'operations':ops,'dlen_beats':ops*beats,
          'dependent_operations':n if streams==1 else 0.,'drain_bytes':32*m['lmul']*streams}
    if f in ('vme_int','vme_fp8'):
        ops=n*m['tiles'];kind='fp8' if f=='vme_fp8' else 'int8'
        return 'vme/'+kind,base,{'operations':ops,'k_steps':ops*m['tk'],'drain_tiles':m['tiles']}
    if f in ('row_read','row_write','tile_zero'):
        return 'vme/'+f,base,{'operations':n}
    return None

def nnls(x,y,weight):
    # Deterministic cyclic coordinate descent, column-normalized. Nonnegative
    # coefficients are effective added latency; never cancel CPU cost with a
    # physically negative latency. Relative weighting balances tiny/large ROIs.
    scale=np.maximum(np.linalg.norm(x*weight[:,None],axis=0),1e-30)
    a=x/scale;aw=a*weight[:,None];b=y*weight;coef=np.zeros(x.shape[1]);res=b.copy()
    for _ in range(50000):
        change=0.
        for j in range(x.shape[1]):
            col=aw[:,j];den=float(col@col)
            if not den:continue
            old=coef[j];new=max(0.,old+float(col@res)/den)
            res+=(old-new)*col;coef[j]=new;change=max(change,abs(new-old))
        if change<1e-10*(1+float(np.max(coef))):break
    return coef/scale

def fit(rows):
    # Collapse repeated executions before optimization; all five trials are
    # retained for independent variance/error reporting. Aliases also receive
    # one semantic-hart weight, rather than silently upweighting duplicate code.
    grouped=collections.defaultdict(list)
    for r in rows:
        if r['partition']=='train' and model_features(r): grouped[(r['semantic_group'],r['hart'])].append(r)
    pools=collections.defaultdict(list)
    for group in grouped.values():
        r=dict(group[0]);r['cycles']=statistics.median(v['cycles'] for v in group)
        r['instret_delta']=statistics.median(v['instret_delta'] for v in group)
        key,base,fs=model_features(r);pools[key].append((r,base,fs))
    result={}
    for key,group in sorted(pools.items()):
        names=['region_intercept_cycles']+sorted(set(k for _,_,f in group for k in f))
        x=np.array([[1.]+[f[k] for k in names[1:]] for _,_,f in group],dtype=float)
        target=np.array([r['cycles'] for r,_,_ in group],dtype=float)
        base=np.array([b for _,b,_ in group]);w=1/np.maximum(target,1.)
        # Mild robust IRLS on relative residuals prevents one cold-history
        # region from setting every operation's execution cost.
        coef=nnls(x,target-base,w)
        for _ in range(4):
            err=(base+x@coef-target)/np.maximum(target,1.)
            med=np.median(err);mad=max(.02,1.4826*np.median(np.abs(err-med)))
            robust=np.minimum(1.,1.5*mad/np.maximum(np.abs(err-med),1e-20))
            coef=nnls(x,target-base,w*np.sqrt(robust))
        rank=int(np.linalg.matrix_rank(x));positive=int(np.count_nonzero(coef>1e-9))
        result[key]={'coefficients':dict(zip(names,map(float,coef))),
          'fixed_cpu_cycles_per_retired_instruction':0. if key.startswith('cpu/') else (.6 if '/shuttle/' in '/'+key+'/' else 1. if '/rocket/' in '/'+key+'/' else .6),
          'training_semantic_hart_groups':len(group),'feature_rank':rank,'feature_columns':len(names),
          'individual_coefficients_identifiable':rank==len(names),
          'positive_coefficients':positive,
          'status':'effective_region_fit_not_physical_pipeline_identification',
          'training_parent_ids':sorted(set(r['parent_case_id'] for r,_,_ in group)),
          'support':{k:{'min':float(min(f[k] for _,_,f in group)),'max':float(max(f[k] for _,_,f in group))} for k in names[1:]}}
    return result

def predict(r,models):
    fs=model_features(r)
    if not fs:return None
    key,base,feat=fs
    if key not in models:return None
    m=models[key];co=m['coefficients'];return key,max(1.,base+co['region_intercept_cycles']+sum(co[k]*v for k,v in feat.items()))

def metrics(rows):
    if not rows:return None
    e=np.array([x['signed_error_pct'] for x in rows]);a=np.abs(e)
    return {'regions':len(rows),'signed_mean_pct':float(np.mean(e)),'signed_median_pct':float(np.median(e)),
      'absolute_median_pct':float(np.median(a)),'absolute_p90_pct':float(np.percentile(a,90)),
      'absolute_max_pct':float(np.max(a)),'within_2pct_fraction':float(np.mean(a<=2.))}

def value(v,status,source,unknowns=()):return {'value':float(v) if v is not None else None,'status':status,'identified_from':source,'unknowns':list(unknowns)}
def runtime(models):
    out={'cpu':{},'scalar_fp':{},'vector':{},'vme':{},'memory':{}}
    for c in ('shuttle','rocket'):
        k='cpu/'+c;co=models[k]['coefficients'];out['cpu'][c]={
          'integer_issue_interval_cycles':value(co['instructions'],'aggregate_effective_cpi',k,['Actual per-cycle pairing remains source pipeline policy.']),
          'integer_alu_latency_cycles':value(1.,'source_policy_unchanged',k),
          'dependent_alu_extra_cycles':value(co['dependent_alu_ops'],'aggregate_critical_chain_excess',k),
          'branch_mispredict_penalty_cycles':value(None,'not_identifiable',None,['Hardware miss counts unavailable; outcome distributions do not identify miss penalty separately.'])}
    for key,m in models.items():
        parts=key.split('/');co=m['coefficients'];ref={'model':key,'rank':m['feature_rank'],'columns':m['feature_columns']}
        if parts[0]=='scalar_fp':out['scalar_fp'].setdefault(parts[1],{})[parts[2]]={'extra_cycles_per_operation':value(co['operations'],'effective_roi_residual',ref)}
        elif parts[0]=='vector':
            out['vector'].setdefault(parts[1],{})[parts[2]]={
              'setup_cycles':value(0.,'unidentified_not_charged',ref),
              'extra_cycles_per_operation':value(co['operations'],'effective_roi_residual',ref),
              'cycles_per_dlen_beat':value(co['dlen_beats'],'effective_roi_residual',ref),
              'dependent_extra_cycles_per_operation':value(co['dependent_operations'],'effective_roi_residual',ref),
              'drain_cycles_per_byte':value(co['drain_bytes'],'effective_roi_residual',ref),
              'physical_issue_interval_cycles':value(None,'not_separately_identified',ref)}
        elif parts[0]=='vme':
            out['vme'][parts[1]]={k:value(v,'effective_roi_residual',ref) for k,v in co.items() if k!='region_intercept_cycles'}
        elif parts[0]=='memory':
            out['memory'].setdefault(parts[1],{}).setdefault(parts[2],{})[parts[3]]={
              'extra_cycles_per_access':value(co['accesses'],'warm_effective_roi_residual',ref),
              'same_bank_peer_extra_cycles':value(co['same_bank_peer_accesses'],'aggregate_contention_residual',ref),
              'other_bank_peer_extra_cycles':value(co['other_bank_peer_accesses'],'aggregate_contention_residual',ref),
              'multi_bank_extra_cycles':value(co['multi_bank_accesses'],'aggregate_pattern_residual',ref),
              'physical_miss_latency_cycles':value(None,'not_identifiable',ref,['Warm cache, NoC, L2, serial-TL and DRAM contributions not separately observed.'])}
    return out

def train(args):
    out=pathlib.Path(args.output);out.mkdir(parents=True,exist_ok=True)
    dest=out/'parameters.json'
    if dest.exists():raise SystemExit('Refuse overwriting a frozen parameter epoch')
    # Only TRAIN numeric rows reach fitting. Validation data is not inspected.
    rows=[json.loads(s) for s in pathlib.Path(args.observations).read_text().splitlines()]
    models=fit([r for r in rows if r['partition']=='train'])
    ref=json.loads((ROOT/'build/fpga-fit-observations-v1/report.json').read_text())
    obj={'schema':'iris.empirical_calibration.v1','units':'core_cycles_at_500MHz',
      'status':'fit_completed_internal_validation_not_yet_opened',
      'actual_parameter_fit_performed':True,'empirical_quality_accepted':False,
      'full_2pct_certified':False,'source_image_association_verified':False,'rtl_certified':False,
      'global_heldout_timings_consumed':False,'runtime_parameters':runtime(models),'region_models':models,
      'native_fixture_sha256':None,'native_model_implementation_sha256':None,
      'feature_schema_sha256':digest(__file__),'input_sha256':{
        str(pathlib.Path(args.observations)):digest(args.observations),str(pathlib.Path(args.split)):digest(args.split),
        'timing/empirical_fit.py':digest(__file__)},
      'reference':ref,'fit_policy':{'target':'median_all_five_trials_per_semantic_hart_group',
        'objective':'nonnegative relative-error IRLS; no validation labels used',
        'fixed_cpu_baseline_cpi':{'shuttle':.6,'rocket':1.},
        'intercept_policy':'Region intercepts are audit nuisance terms, NEVER charged at every instruction.',
        'case_id_pc_or_trial_number_runtime_feature':False},
      'unknowns':['No independently measured branch-mispredict counts.',
        'Cold instruction/cache history not reproduced by region feature proxy.',
        'Region fit uses physical instret as scalar-work proxy; live engine must emit corresponding functional/source-pipeline counts.',
        'Individual coefficients of rank-deficient groups cannot be interpreted as physical unit latencies.',
        'Streaming DRAM miss/service, atomics, IRQ, synchronization and pipeline interactions not fitted here.',
        'Region model validation does not validate a live simulator timing implementation.']}
    save(dest,obj);print(json.dumps({'parameters':str(dest),'sha256':digest(dest),'models':len(models)}))

def evaluate(args):
    p=pathlib.Path(args.output)/'parameters.json';params=json.loads(p.read_text());sha=digest(p)
    rows=[json.loads(s) for s in pathlib.Path(args.observations).read_text().splitlines()]
    if digest(args.observations)!=params['input_sha256'][str(pathlib.Path(args.observations))]:raise SystemExit('Observations changed')
    preds=[];unsupported=collections.Counter();variance=collections.defaultdict(list)
    for r in rows:
        variance[(r['parent_case_id'],r['hart'])].append(r['cycles']);v=predict(r,params['region_models'])
        if v is None:unsupported[(r['partition'],r['family'])]+=1;continue
        key,y=v;preds.append({'parent_case_id':r['parent_case_id'],'case_id':r['case_id'],'hart':r['hart'],
          'partition':r['partition'],'family':r['family'],'model':key,'trial_id':r['trial_id'],
          'reference_cycles':r['cycles'],'predicted_cycles':y,'signed_error_pct':100*(y-r['cycles'])/r['cycles']})
    by=collections.defaultdict(list)
    for r in preds:by[(r['partition'],r['family'])].append(r)
    summaries={part:{fam:metrics(v) for (p,fam),v in sorted(by.items()) if p==part} for part in ('train','internal_validation')}
    medpred=collections.defaultdict(list)
    for r in preds:medpred[(r['partition'],r['family'],r['parent_case_id'],r['hart'])].append(r)
    parentrows=[]
    for key,v in medpred.items():
        y=statistics.median(x['reference_cycles'] for x in v);yp=statistics.median(x['predicted_cycles'] for x in v)
        parentrows.append({'partition':key[0],'family':key[1],'parent_case_id':key[2],'hart':key[3],
          'reference_cycles':y,'predicted_cycles':yp,'signed_error_pct':100*(yp-y)/y})
    perparent={part:{fam:metrics([r for r in parentrows if r['partition']==part and r['family']==fam]) for fam in sorted(set(r['family'] for r in parentrows))} for part in ('train','internal_validation')}
    var=[]
    for (case,h),v in variance.items():
        med=statistics.median(v);var.append({'parent_case_id':case,'hart':h,'median_cycles':med,'min_cycles':min(v),'max_cycles':max(v),'range_fraction':(max(v)-min(v))/med})
    out=pathlib.Path(args.output)
    with (out/'predictions.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(preds[0]));w.writeheader();w.writerows(preds)
    save(out/'repetition-variance.json',var)
    report={'schema':'iris.empirical_fit_validation.v1','status':'evaluated_frozen_parameter_epoch',
      'parameters_sha256':sha,'feature_model_sha256':digest(__file__),
      'reference_regions':len(rows),'predicted_regions':len(preds),
      'per_family_all_trials':summaries,'per_family_parent_hart_medians':perparent,
      'overall':{part:metrics([r for r in preds if r['partition']==part]) for part in ('train','internal_validation')},
      'unsupported_regions':[{'partition':p,'family':f,'regions':v} for (p,f),v in sorted(unsupported.items())],
      'first_trial':{part:metrics([r for r in preds if r['partition']==part and r['trial_id']==0]) for part in ('train','internal_validation')},
      'remaining_trials':{part:metrics([r for r in preds if r['partition']==part and r['trial_id']!=0]) for part in ('train','internal_validation')},
      'full_2pct_certified':False,'source_image_association_verified':False,
      'global_heldout_timings_consumed':False,'live_native_timing_validated':False,
      'outputs_sha256':{name:digest(out/name) for name in ('predictions.csv','repetition-variance.json')}}
    save(out/'fit-report.json',report)
    print(json.dumps({'report':str(out/'fit-report.json'),'overall':report['overall'],'predicted_regions':len(preds)},indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('command',choices=['train','evaluate']);a.add_argument('--observations',default='calibration/empirical-v1/observations.jsonl');a.add_argument('--split',default='calibration/empirical-v1/split.json');a.add_argument('--output',default='calibration/empirical-v1');args=a.parse_args()
    (train if args.command=='train' else evaluate)(args)
