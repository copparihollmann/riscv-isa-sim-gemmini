#!/usr/bin/env python3
"""Explore effective cache-tier service with explicitly approximate region counts.
Does not assert actual tags were reconstructed or use protocol as a live input.
"""
import argparse, collections, csv, hashlib, json, pathlib, statistics
import numpy as np
from empirical_fit import ROOT,digest,save,nnls,metrics

def features(r):
    if r['suite']!='distribution' or r['family']!='memory':return None
    m=r['metadata']
    if m['mode'] not in (0,1,2):return None
    c='shuttle' if r['hart']<2 else 'rocket';size=m['bytes'];n=m['n'];peers=bin(r['active_hart_mask']).count('1')-1
    shared=m['mode']==2;total=size if shared else size*(peers+1)
    l1=8192 if c=='shuttle' else 16384;l2=524288
    cold=m['protocol']==2
    if m['mode']==1:
        loads=n;unique=min(n,size//64)
        l1miss=loads if size>l1 else unique if cold else 0
        outer=loads if total>l2 else unique if cold else 0
    else:
        loads=n*size//4;unique=size//64
        l1miss=n*unique if size>l1 else unique if cold else 0
        outer=n*unique if total>l2 else unique if cold else 0
    # This is an explicit region-count approximation. It admits no claim that
    # eviction traversals guarantee coldness, shared fills duplicate, or all
    # L2 ways/indices have capacity-only occupancy.
    return c,{'loads':loads,'l1_miss_lines':l1miss,'outer_miss_lines':outer,
              'outer_miss_peer_lines':outer*peers},(.6 if c=='shuttle' else 1.)*r['instret_delta']

def main(args):
    rows=[json.loads(s) for s in pathlib.Path(args.observations).read_text().splitlines()]
    out=pathlib.Path(args.output);out.mkdir(parents=True,exist_ok=True)
    p=out/'parameters.json'
    if args.command=='train':
        if p.exists():raise SystemExit('Refuse overwrite')
        groups=collections.defaultdict(list)
        for r in rows:
            if r['partition']=='train' and features(r):groups[(r['semantic_group'],r['hart'])].append(r)
        pools=collections.defaultdict(list)
        for g in groups.values():
            r=dict(g[0]);r['cycles']=statistics.median(x['cycles'] for x in g)
            c,fs,base=features(r);pools[c].append((r,fs,base))
        models={};names=['region_intercept_cycles','loads','l1_miss_lines','outer_miss_lines','outer_miss_peer_lines']
        for c,items in pools.items():
            x=np.array([[1.]+[f[k] for k in names[1:]] for _,f,_ in items]);y=np.array([r['cycles'] for r,_,_ in items]);b=np.array([b for _,_,b in items]);w=1/y
            co=nnls(x,y-b,w)
            models[c]={'coefficients':dict(zip(names,map(float,co))),'rank':int(np.linalg.matrix_rank(x)),'columns':len(names),'training_groups':len(items)}
        save(p,{'schema':'iris.empirical_cache_tier_proxy.v1','status':'effective_service_exploration_counts_not_live_tag_verified',
          'units':'core_cycles_at_500MHz','models':models,
          'inputs_sha256':{args.observations:digest(args.observations),'timing/empirical_stream_fit.py':digest(__file__),'hardware/manifest.json':digest(ROOT/'hardware/manifest.json')},
          'scope':['Capacity-only proxy8KiB/16KiBL1D;512KiBL2;64Bline.','Prepare warm/eviction metadata used ONLY to approximate feature counts; live model MUST derive warm state from actual runtime tags.','Counts are NOT a physical source-cache trace, and no tag state is injected.','No source/image association; outer cost combines L2miss/serial/DRAM/dirtyvictim/bandwidth/backpressure.','No FASED30 conversion. Globalheldouttimingunused.'],
          'full_2pct_certified':False,'source_image_association_verified':False,'live_model_verified':False})
        print(json.dumps({'parameters':str(p),'sha256':digest(p),'models':models},indent=2));return
    par=json.loads(p.read_text());pred=[]
    for r in rows:
        f=features(r)
        if not f or f[0] not in par['models']:continue
        c,fs,b=f;co=par['models'][c]['coefficients'];y=b+co['region_intercept_cycles']+sum(co[k]*v for k,v in fs.items())
        pred.append({'case_id':r['case_id'],'parent_case_id':r['parent_case_id'],'hart':r['hart'],'partition':r['partition'],'reference_cycles':r['cycles'],'predicted_cycles':y,'signed_error_pct':100*(y-r['cycles'])/r['cycles']})
    with (out/'predictions.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(pred[0]));w.writeheader();w.writerows(pred)
    save(out/'report.json',{'schema':'iris.empirical_cache_tier_proxy_validation.v1','parameters_sha256':digest(p),'metrics':{part:metrics([r for r in pred if r['partition']==part]) for part in ('train','internal_validation')},'internal_validation_already_used_for_v1_review':True,'global_heldout_timings_consumed':False,'full_2pct_certified':False,'live_model_verified':False,'predictions_sha256':digest(out/'predictions.csv')})
    print((out/'report.json').read_text())
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('command',choices=['train','evaluate']);a.add_argument('--observations',default='calibration/empirical-v1/observations.jsonl');a.add_argument('--output',default='calibration/empirical-stream-v1');main(a.parse_args())
