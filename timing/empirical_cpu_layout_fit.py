#!/usr/bin/env python3
"""Training-only generic fetch-word footprint fit, followed by explicit offset CV.

This is a loop-basis diagnostic, not a live timing implementation. Instruction
lengths come from an independently checked executed ELF. Neither case IDs nor
absolute PCs enter predictors. Intercepts are region-boundary diagnostics only.
"""
import argparse, csv, hashlib, json, math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPLIT_SHA = '1c9901b04717341f6934389ac24ebb0a0588a193a4bd3367cb4744ed6bedcf89'
CSV_SHA = 'c5f85eab0f7fad540dbb36aaaa80a082ce1c8636280dc95d54eb831445106c99'
REPORT_SHA = 'b248604626e99ac67e30c3acc24803159c39408bc44df673224d508cfa718a09'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x): Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def checked_int(value, name):
    if isinstance(value,bool): raise ValueError('Boolean '+name)
    if isinstance(value,str) and not value.isdigit(): raise ValueError('Noninteger '+name)
    n=int(value)
    if n!=float(value) or n<0: raise ValueError('Invalid '+name)
    return n

def load(csv_path,split_path):
    if sha(csv_path)!=CSV_SHA or sha(split_path)!=SPLIT_SHA: raise ValueError('Frozen dataset/split identity mismatch')
    split=json.loads(Path(split_path).read_text()); rows=[]; keys=set()
    for raw in csv.DictReader(Path(csv_path).open()):
        r=dict(raw)
        for k in ('hart','loop_offset','n','repeat','loop_pc','begin_pc','end_pc','cycles','instret_delta','checksum','counter_end'):
            r[k]=checked_int(r[k],k)
        k=(r['case_id'],r['hart'])
        if k in keys: raise ValueError('Duplicate observation')
        keys.add(k)
        if r['hart'] not in (0,1,2) or r['repeat'] not in (0,1,2): raise ValueError('Invalid hart/repeat')
        if r['mode'] not in ('compact','wide','noop'): raise ValueError('Invalid mode')
        if r['loop_pc']%64!=r['loop_offset']: raise ValueError('PC/offset mismatch')
        if r['checksum']!=r['hart']+1+3*r['n'] or r['counter_end']!=r['n']: raise ValueError('Golden mismatch')
        if r['instret_delta']!=3*r['n']+(2 if r['hart']<2 else 3): raise ValueError('Instret mismatch')
        r['partition']=split['split'][r['parent_case_id']]['partition']
        if r['mode']=='noop':
            if r['n']!=0 or r['partition']!='control': raise ValueError('Bad no-op control')
        else:
            if r['n'] not in (16,64,256,1024) or r['partition'] not in ('train','internal_validation'): raise ValueError('Bad training row')
        rows.append(r)
    if len(rows)!=2313: raise ValueError('Incomplete corpus')
    return rows,split

def features(r):
    # Pure instruction-footprint geometry. In this checked basis, the first two
    # operations are independent, and the branch depends on the second operation.
    # Thus the dependency/issue lower bound is 2 (Shuttle) or 3 (Rocket).
    lengths=(2,2,4) if r['mode']=='compact' else (4,4,4)
    word=8 if r['hart']<2 else 4
    start=r['loop_pc']; last=start+sum(lengths)-1
    words=last//word-start//word+1
    floor=2 if r['hart']<2 else 3
    return [float(r['n']),float(r['n']*max(0,words-floor)),1.0]

def robust_fit(rows):
    # Conditioning subset only establishes steady service. All other rows remain
    # in the report. Eligibility is NEVER an input to the prediction function.
    x=np.asarray([features(r) for r in rows],float); y=np.asarray([r['cycles'] for r in rows],float)
    scale=np.maximum(np.max(abs(x),axis=0),1); z=x/scale
    weights=np.ones(len(y)); beta=np.linalg.lstsq(z,y,rcond=None)[0]
    for _ in range(200):
        resid=y-z@beta
        weights=np.minimum(1.0,1.0/np.maximum(abs(resid),1e-12))
        new=np.linalg.lstsq(z*np.sqrt(weights[:,None]),y*np.sqrt(weights),rcond=None)[0]
        if np.max(abs(new-beta))<1e-10: beta=new; break
        beta=new
    beta=beta/scale
    if np.any(beta < -1e-7): raise ValueError('Negative service fit')
    return [float(max(v,0)) for v in beta],int(np.linalg.matrix_rank(x))

def prediction(r, models):
    m=models['shuttle' if r['hart']<2 else 'rocket']
    return float(np.dot(features(r),m['coefficients']))

def metrics(rows):
    if not rows:return {'count':0}
    es=np.array([(r['predicted_cycles']-r['cycles'])/r['cycles']*100 for r in rows if r['cycles']>0]); ae=abs(es)
    return {'count':len(rows),'positive_reference_count':len(es),'signed_error_mean_pct':float(np.mean(es)),
            'signed_error_median_pct':float(np.median(es)),'absolute_error_median_pct':float(np.median(ae)),
            'absolute_error_p90_pct':float(np.quantile(ae,.9)),'absolute_error_max_pct':float(np.max(ae)),
            'within_2pct_count':int(np.sum(ae<=2)),'within_2pct_fraction':float(np.mean(ae<=2))}

def fit(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    rows,split=load(args.csv,args.split)
    models={}
    for name,harts in [('shuttle',(0,1)),('rocket',(2,))]:
        eligible=[r for r in rows if r['partition']=='train' and r['hart'] in harts and r['n']>=64 and r['repeat']>0 and r['mode']!='noop']
        coef,rank=robust_fit(eligible)
        models[name]={'coefficients':coef,'coefficient_names':['cycles_per_dependency_iteration','cycles_per_excess_fetch_word','region_boundary_cycles_audit_only'],
                      'rank':rank,'fitting_rows':len(eligible),'dependency_issue_floor':2 if name=='shuttle' else 3,
                      'fetch_word_bytes':8 if name=='shuttle' else 4}
    params={'schema':'iris.empirical_cpu_layout_parameters.v1','models':models,
            'feature_definition':'[N, N*max(0,distinct_aligned_fetch_words_intersecting_loop - dependency_issue_floor),1]',
            'absolute_PC_or_case_lookup':False,'region_intercept_may_be_used_per_instruction':False,
            'source_qualification':'Effective event hypothesis from checked original-order loop motif; not a general native pipeline implementation or proved source controller rule.',
            'fit_rows':'train offsets only; N>=64 and immediate repeats1/2 establish conditioned service; prediction is identical for all repetitions.',
            'input_sha256':{str(args.csv.relative_to(ROOT)):sha(args.csv),str(args.split.relative_to(ROOT)):sha(args.split),str(Path(__file__).resolve().relative_to(ROOT)):sha(__file__)},
            'training_offset_groups':split['train_offsets'],'global_heldout_timings_consumed':False,'internal_validation_timings_used_for_fit':False,
            'live_model_binding_available':False,'full_2pct_certified':False,'source_image_association_verified':False}
    write(out/'parameters.json',params)
    # Predictions are frozen before a distinct evaluate command reads CV labels.
    preds=[]
    for r in rows:
        if r['mode']=='noop':continue
        preds.append({k:r[k] for k in ['case_id','parent_case_id','hart','mode','loop_offset','n','repeat','loop_pc','partition']}|{'predicted_cycles':prediction(r,models)})
    write(out/'predictions.json',{'schema':'iris.cpu_layout_predictions.v1','parameters_sha256':sha(out/'parameters.json'),'rows':preds,'no_labels':True})
    train=[dict(r,predicted_cycles=prediction(r,models)) for r in rows if r['partition']=='train' and r['mode']!='noop']
    write(out/'training-report.json',{'schema':'iris.cpu_layout_training_report.v1','models':models,'all_training_rows':metrics(train),
          'conditioned_fit_rows':metrics([r for r in train if r['n']>=64 and r['repeat']>0]),
          'global_heldout_timings_consumed':False,'internal_validation_evaluated':False})
    print(json.dumps({'parameters_sha256':sha(out/'parameters.json'),'predictions_sha256':sha(out/'predictions.json'),'models':models},indent=2))

def evaluate(args):
    rows,split=load(args.csv,args.split);out=args.output
    if (out/'report.json').exists():raise ValueError('Refusing report overwrite')
    params=json.loads((out/'parameters.json').read_text());preds=json.loads((out/'predictions.json').read_text())
    if preds['parameters_sha256']!=sha(out/'parameters.json'):raise ValueError('Prediction parameter identity changed')
    lookup={(r['case_id'],r['hart']):r for r in rows};comp=[]
    for p in preds['rows']:
        r=lookup[(p['case_id'],p['hart'])]
        if p['partition']!=r['partition'] or abs(p['predicted_cycles']-prediction(r,params['models']))>1e-9: raise ValueError('Prediction changed')
        comp.append(dict(r,predicted_cycles=p['predicted_cycles'],signed_error_pct=100*(p['predicted_cycles']-r['cycles'])/r['cycles']))
    valid=[r for r in comp if r['partition']=='internal_validation']
    by={}
    for name,subset in [('all',valid),('N_ge_64_repeat1_2',[r for r in valid if r['n']>=64 and r['repeat']>0]),
                         ('repeat0_all_N',[r for r in valid if r['repeat']==0]),('N16_all_repeats',[r for r in valid if r['n']==16])]:
        by[name]=metrics(subset)
    by_hart={str(h):metrics([r for r in valid if r['hart']==h]) for h in range(3)}
    by_mode={m:metrics([r for r in valid if r['mode']==m]) for m in ('compact','wide')}
    # Report all raw repeat spreads, including first-use state; do not quietly
    # average/subtract it. These are observations, not a repeat-index model.
    groups={}
    for r in rows:
        groups.setdefault((r['parent_case_id'],r['hart']),[]).append(r)
    reps=[{'parent_case_id':k[0],'hart':k[1],'cycles_by_repeat':[r['cycles'] for r in sorted(v,key=lambda r:r['repeat'])],
           'raw_range_cycles':max(r['cycles'] for r in v)-min(r['cycles'] for r in v)} for k,v in sorted(groups.items())]
    report={'schema':'iris.empirical_cpu_layout_report.v1','status':'fit_and_internal_validation_complete_unbound_diagnostic',
       'input_sha256':{str(args.csv.relative_to(ROOT)):sha(args.csv),str(args.split.relative_to(ROOT)):sha(args.split),str(Path(__file__).resolve().relative_to(ROOT)):sha(__file__)},
       'reference_archive_sha256':'40ee7353db6cb0f2fa75fe63e28079328256773e2ce5d15f8d2dc77b8086fa26',
       'reference_report_sha256':REPORT_SHA,'parameters_sha256':sha(out/'parameters.json'),'predictions_sha256':sha(out/'predictions.json'),
       'models':params['models'],'internal_validation':by,'internal_validation_by_hart':by_hart,'internal_validation_by_mode':by_mode,
       'training':metrics([r for r in comp if r['partition']=='train']),'rows':len(comp),'noop_controls':9,
       'split_parent_counts':split['parent_counts'],'overhead_subtraction':False,
       'limitations':['Conditioned compact loop is ~2 cycles/iteration on both Shuttles across offsets; simple loop alignment alone does not reproduce the old smoke 4-cycle cadence.',
          'Training motif has two independent integer ops followed by a branch depending on the second; other dataflow/BTB/history and general kernels remain unvalidated.',
          'First-use/reset/instruction-cache/branch-history effects are not predicted by this steady-footprint diagnostic; every row and error is retained.',
          'Boundary constant is region-only diagnostic; never charge it per instruction or use repetition number as a live feature.',
          'No native runtime timing knob is bound by this report. Existing source-image association and full heldout +/-2% remain false.'],
       'internal_validation_is_development_evidence':True,'global_heldout_timings_consumed':False,'live_native_quality_certified':False,
       'full_2pct_certified':False,'source_image_association_verified':False}
    write(out/'comparisons.json',comp);write(out/'repetitions.json',reps);write(out/'report.json',report)
    print(json.dumps(report,indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['fit','evaluate']);p.add_argument('--csv',type=Path,default=ROOT/'build/fpga-cpu-layout-v2-001-analysis/regions.csv');p.add_argument('--split',type=Path,default=ROOT/'calibration/cpu-layout-v2/split.json');p.add_argument('--output',type=Path,default=ROOT/'calibration/cpu-layout-fit-v1');args=p.parse_args()
    {'fit':fit,'evaluate':evaluate}[args.command](args)
if __name__=='__main__':main()
