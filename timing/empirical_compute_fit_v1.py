#!/usr/bin/env python3
"""Fit constrained NEW compute costs over its own actually executed native baseline.

This linearization is an explicit pilot. Async overlap/port contention require
matched native replay; proxy-fit predictions never certify the live simulator.
"""
import argparse,collections,csv,hashlib,json,pathlib,statistics
import numpy as np
from empirical_fit import nnls,metrics
ROOT=pathlib.Path(__file__).resolve().parents[1]
EXCLUDED={'empty','atomics','atomic','lrsc','sync_barrier','ipi','timer','pipeline','pipeline_vme','refuse_vme','vme_refusal'}
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,x):pathlib.Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def features(r,shared_cache=False):
    out={}
    for f,v in r['features'].items():
        if f.startswith(('rvv.','vme.')):
            # Separate op/setup and amount-of-work costs. The native baseline
            # already includes source/scoped-heuristic backend duration.
            out[f+'.instructions']=float(v['instructions']);out[f+'.work']=float(v['work'])
        elif f in ('memory.vector.load','memory.vector.store'):
            out[f+'.instructions']=float(v['instructions']);out[f+'.work']=float(v['work'])
        elif f.startswith('scalar.fp'):out[f+'.instructions']=float(v['instructions'])
    for path,v in r.get('memory',{}).items():
        if path in ('LOCAL_TCM','REMOTE_TCM','SCRATCHPAD'):
            
            for kind in ('reads','writes'):out['memory.'+path+'.'+kind]=float(v.get(kind,0))
        elif path=='ICACHE.DRAM':
            # Additional L1 refill/front service only. Shared outer service is
            # an explicitly fixed external prior, not identified by this data.
            out['icache.DRAM.l1misses']=float(v.get('l1misses',0))
        # Generic scalar DRAM writes/read hits and shared outer service are
        # not free nuisance columns: warm-store baseline already overpredicts.
    if r.get('branch_history',{}).get('resolved_mispredicts',0):out['branch.mispredicts']=float(r['branch_history']['resolved_mispredicts'])
    # IDs, PCs, case metadata, region labels and trial numbers are NEVER read
    # here. Class selection is only actual hart microarchitecture.
    if shared_cache:
        for metric in ("l1misses","l2misses"):
            key="icache.DRAM."+metric
            if key in out:out["cache.DRAM."+metric]=out.get("cache.DRAM."+metric,0.)+out.pop(key)
    return out

def fit(rows,split,shared_cache=False):
    groups=collections.defaultdict(list)
    for r in rows:
        ent=split['split'][r['parent_case_id']]
        if ent['partition']!=r['partition']:raise ValueError('Split mismatch')
        if r['partition']=='train' and r['family_for_reporting_only'] not in EXCLUDED:
            groups[(ent['semantic_group'],r['hart'])].append(r)
    pools=collections.defaultdict(list)
    for group in groups.values():
        fs=[features(r,shared_cache) for r in group];names=set(k for f in fs for k in f)
        x={k:statistics.median(f.get(k,0) for f in fs) for k in names}
        c='shuttle' if group[0]['hart']<2 else 'rocket'
        pools[c].append((group,statistics.median(r['reference_cycles'] for r in group),statistics.median(r['native_cycles'] for r in group),x))
    models={}
    for c,g in pools.items():
        names=sorted(k for k in set(k for _,_,_,f in g for k in f) if any(f.get(k,0)>0 for _,_,_,f in g))
        if not names:continue
        x=np.array([[f.get(k,0) for k in names] for _,_,_,f in g]);y=np.array([y for _,y,_,_ in g]);base=np.array([b for _,_,b,_ in g]);w=1/np.maximum(y,1.)
        co=nnls(x,y-base,w)
        for _ in range(4):
            e=(base+x@co-y)/np.maximum(y,1.);med=np.median(e);mad=max(.02,1.4826*np.median(np.abs(e-med)));robust=np.minimum(1.,1.5*mad/np.maximum(np.abs(e-med),1e-20));co=nnls(x,y-base,w*np.sqrt(robust))
        rank=int(np.linalg.matrix_rank(x));models[c]={'coefficients':dict(zip(names,map(float,co))),'training_semantic_hart_groups':len(g),'columns':len(names),'rank':rank,'individual_coefficients_identifiable':rank==len(names),'individually_identifiable':{name:bool(rank>int(np.linalg.matrix_rank(np.delete(x,i,axis=1)))) for i,name in enumerate(names)},'training_parent_ids':sorted({r['parent_case_id'] for group,_,_,_ in g for r in group}),'region_intercept_cycles':0.,'baseline_scale':1.,'scope':'Nonnegative added-cost linearization; actual native replay required for nonlinear overlap/contention.'}
    return models

def main(a):
    rows=[json.loads(s) for s in pathlib.Path(a.regions).read_text().splitlines()];split=json.load(open(a.split));out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True)
    p=out/'parameters.json'
    if a.command=='train':
        if p.exists():raise SystemExit('Refuse overwrite frozen live-fit epoch')
        native=json.load(open(a.native_receipt));models=fit(rows,split,a.shared_cache_service)
        obj={'schema':'iris.empirical_live_residual_fit.v1','status':'pilot_fit_completed_runtime_replay_pending','actual_parameter_fit_performed':True,'shared_instruction_data_cache_service':a.shared_cache_service,'models':models,'global_heldout_timings_consumed':False,'full_2pct_certified':False,'source_image_association_verified':False,'live_model_quality_accepted':False,'source_sha256':sha(__file__),'input_sha256':{a.regions:sha(a.regions),a.split:sha(a.split),a.native_receipt:sha(a.native_receipt)},'native_inputs_sha256':native['input_sha256'],'native_run_status_at_snapshot':native['status'],'eligible_fit_families_excluded':sorted(EXCLUDED),'intercept_policy':'No ROI intercept or negative cost; fixed actual native baseline scale1.','charged_feature_contract':'Shared outer/TCM/scratch priors fixed externally. No generic scalar DRAM cost columns. Additional instruction-L1/branch/vector-store and compute costs only; actual runtime quantization and nonlinear replay required.','linearization_unknowns':['Async compute overlap is not a sum; this pilot only proposes additional costs.','Shared outer launch interval cannot be fitted by simple per-hart instruction-count regression.','Cold Icache needs actual runtime Icache features; not assigned to an instruction family.','Snapshot may be an intentionally bounded training pilot, not the complete6750 run.']}
        save(p,obj);(out/'fit-source.py').write_bytes(pathlib.Path(__file__).read_bytes());(out/'native-receipt-snapshot.json').write_bytes(pathlib.Path(a.native_receipt).read_bytes());print(json.dumps({'parameters':str(p),'sha256':sha(p),'models':len(models)},indent=2));return
    par=json.load(p.open());pred=[]
    for r in rows:
        c='shuttle' if r['hart']<2 else 'rocket';fs=features(r,par.get('shared_instruction_data_cache_service',False));co=par['models'].get(c,{}).get('coefficients',{});yp=r['native_cycles']+sum(v*fs.get(k,0) for k,v in co.items());pred.append({'case_id':r['case_id'],'parent_case_id':r['parent_case_id'],'hart':r['hart'],'partition':r['partition'],'family':r['family_for_reporting_only'],'reference_cycles':r['reference_cycles'],'baseline_native_cycles':r['native_cycles'],'linearized_predicted_cycles':yp,'signed_error_pct':100*(yp-r['reference_cycles'])/r['reference_cycles'],'baseline_signed_error_pct':100*(r['native_cycles']-r['reference_cycles'])/r['reference_cycles'],'calibration_family_supported':r['family_for_reporting_only'] not in EXCLUDED})
    # Case/bank metadata is copied ONLY into diagnostic tables. features() never
    # reads it; all fitted costs use runtime counters/address-derived events.
    for result,observed in zip(pred,rows):
        m=observed.get('case_metadata_for_reporting_only',{})
        result.update(report_target=m.get('target_region',''),report_kind=m.get('kind',''),report_n=m.get('n',''),report_mask=m.get('mask',''),report_stride=m.get('stride',''),report_spread=m.get('spread',''),report_addresses=json.dumps(m.get('addresses_by_hart',[])),report_bit6_sequences=json.dumps(m.get('bank_bit6_sequence_by_hart',[])))
    fields=list(pred[0]);f=(out/'predictions.csv').open('w');w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(pred);f.close()
    by=collections.defaultdict(list)
    for r in pred:by[(r['partition'],r['family'])].append(r)
    report={'schema':'iris.empirical_live_residual_diagnostics.v1','parameters_sha256':sha(p),'regions':len(pred),'per_family':{part:{f:metrics(v) for (p,f),v in sorted(by.items()) if p==part} for part in ('train','internal_validation')},'overall':{part:metrics([r for r in pred if r['partition']==part and r['calibration_family_supported']]) for part in ('train','internal_validation')},'baseline_positive_addition_floor':{part:{'regions':len([r for r in pred if r['partition']==part]),'baseline_already_over_2pct':len([r for r in pred if r['partition']==part and r['baseline_signed_error_pct']>2])} for part in ('train','internal_validation')},'global_heldout_timings_consumed':False,'actual_candidate_native_replay_performed':False,'full_2pct_certified':False,'source_image_association_verified':False,'predictions_sha256':sha(out/'predictions.csv')};bank_groups=collections.defaultdict(list)
    for r in pred:
        if r['report_target']:bank_groups[(r['partition'],r['hart'],r['report_target'],r['report_kind'],str(r['report_n']),str(r['report_mask']),str(r['report_stride']),str(r['report_spread']))].append(r)
    report['per_hart_target_mask_stride_spread']=[{'partition':k[0],'hart':k[1],'target':k[2],'kind':k[3],'n':k[4],'mask':k[5],'stride':k[6],'spread':k[7],**metrics(v)} for k,v in sorted(bank_groups.items())]
    report['bank_fields_are_reporting_only_not_regression_features']=True
    save(out/'report.json',report);print(json.dumps({'report':str(out/'report.json'),'overall':report['overall']},indent=2))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('command',choices=['train','evaluate']);a.add_argument('--regions',required=True);a.add_argument('--split',default='calibration/empirical-v1/split.json');a.add_argument('--native-receipt',required=True);a.add_argument('--output',required=True);a.add_argument('--shared-cache-service',action='store_true');main(a.parse_args())
