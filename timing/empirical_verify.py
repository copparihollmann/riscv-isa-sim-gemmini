#!/usr/bin/env python3
"""Independent receipt/source/split/prediction verification for empirical fits."""
import argparse, collections, csv, hashlib, importlib.util, json, math, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def verify(folder):
    folder=pathlib.Path(folder);p=load(folder/'parameters.json');report=load(folder/'fit-report.json');split=load(folder/'split.json');checks=[]
    def check(ok,name):
        if not ok:raise ValueError(name)
        checks.append(name)
    check(report['parameters_sha256']==sha(folder/'parameters.json'),'parameter_epoch_bound')
    for f,h in p['input_sha256'].items():check(sha(ROOT/f)==h,'input:'+f)
    for f,h in report['outputs_sha256'].items():check(sha(folder/f)==h,'output:'+f)
    check(not p['full_2pct_certified'] and not report['full_2pct_certified'],'no_full_2pct_claim')
    check(not p['source_image_association_verified'] and not report['source_image_association_verified'],'no_image_association_claim')
    check(not p['global_heldout_timings_consumed'] and not report['global_heldout_timings_consumed'],'no_global_holdout_label_claim')
    rows=[json.loads(s) for s in (folder/'observations.jsonl').read_text().splitlines()];parents={};semantics={}
    for r in rows:
        ent=split['split'][r['parent_case_id']]
        check(r['partition']==ent['partition'] and r['semantic_group']==ent['semantic_group'],'row_partition:'+r['case_id']+':'+str(r['hart']))
        if r['semantic_group'] in semantics:check(semantics[r['semantic_group']]==r['partition'],'alias_partition')
        semantics[r['semantic_group']]=r['partition'];parents[r['parent_case_id']]=r['partition']
        check(r['cycles']>0 and r['instret_delta']>=0,'positive_counters')
    for key,m in p['region_models'].items():
        check(all(math.isfinite(v) and v>=0 for v in m['coefficients'].values()),'nonnegative_finite:'+key)
        check(all(parents[k]=='train' for k in m['training_parent_ids']),'train_only:'+key)
        check(m['individual_coefficients_identifiable']==(m['feature_rank']==m['feature_columns']),'rank_scope:'+key)
    # Independent arithmetic replay: use recorded coefficients and formula only;
    # feature compiler is source-bound and loaded solely for field extraction.
    spec=importlib.util.spec_from_file_location('iris_empirical_feature',ROOT/'timing/empirical_fit.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    csvrows=list(csv.DictReader((folder/'predictions.csv').open()));bykey={(r['case_id'],r['hart']):r for r in rows};errors=collections.defaultdict(list)
    for pred in csvrows:
        r=bykey[(pred['case_id'],int(pred['hart']))];key,base,fs=mod.model_features(r);co=p['region_models'][key]['coefficients']
        y=max(1.,base+co['region_intercept_cycles']+sum(co[k]*v for k,v in fs.items()));e=100*(y-r['cycles'])/r['cycles']
        check(math.isclose(y,float(pred['predicted_cycles']),rel_tol=1e-13),'prediction:'+pred['case_id']+':'+pred['hart'])
        check(math.isclose(e,float(pred['signed_error_pct']),abs_tol=1e-10),'signed_error')
        errors[pred['partition']].append(e)
    for part,e in errors.items():
        check(len(e)==report['overall'][part]['regions'],'metric_count:'+part)
        check(math.isclose(sum(e)/len(e),report['overall'][part]['signed_mean_pct'],abs_tol=1e-10),'signed_mean:'+part)
    return {'schema':'iris.empirical_independent_verification.v1','status':'passed','checks':len(checks),'rows':len(rows),'predictions':len(csvrows),'parent_partitions':dict(collections.Counter(parents.values())),'source_sha256':sha(__file__),'parameters_sha256':sha(folder/'parameters.json'),'fit_report_sha256':sha(folder/'fit-report.json'),'global_heldout_timings_opened':False,'full_2pct_certified':False}
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--calibration',default='calibration/empirical-v1');a.add_argument('--output',default='build/empirical-calibration-verify-v1/results.json');args=a.parse_args();result=verify(ROOT/args.calibration);out=ROOT/args.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
