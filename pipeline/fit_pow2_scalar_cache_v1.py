#!/usr/bin/env python3
"""Fixed two-column TRAIN-only NNLS over real baseline cycles and typed probes."""
import argparse,importlib.util,json,math,struct
from pathlib import Path
from scalar_l2_hit_run import ROOT,sha
ELF='f6221a378ae02c1191992bd2db8a546efd7a2ece10c636ddf93d3912e8fb11ed'
TRAIN_ROWS='896f97794b8ef4490ad6d54b5ca8da9e7023aabc7356926072465ff07cb041a5'
RESERVED={4096,65536,524288}
def need(ok,why):
    if not ok:raise ValueError(why)
def load(p):return json.loads(Path(p).read_text())
def nnls(samples):
    # samples=(xhit,xouter,residual,hardwarecycles); fixed relative-square loss.
    a=b=c=d=e=0.
    for x,z,y,t in samples:
        w=1/(t*t);a+=w*x*x;b+=w*x*z;c+=w*z*z;d+=w*x*y;e+=w*z*y
    determinant=a*c-b*b
    need(a>0 and c>0 and determinant>1e-12*a*c,'Two independently identified nonzero service bases required')
    candidates=[(0.,0.),(max(0.,d/a),0.),(0.,max(0.,e/c))]
    h=(d*c-e*b)/determinant;o=(e*a-d*b)/determinant
    if h>=0 and o>=0:candidates.append((h,o))
    def loss(p):return sum(((p[0]*x+p[1]*z-y)/t)**2 for x,z,y,t in samples)
    best=min(candidates,key=loss)
    return best,{'rank':2,'gram':[[a,b],[b,c]],'determinant':determinant,'relative_squared_loss_sum':loss(best),'zero_basis_rows':sum(x==z==0 for x,z,y,t in samples)}
def module():
    p=ROOT/'benchmarks/pow2_memory_v1/validate.py';s=importlib.util.spec_from_file_location('pow2_memory_source_validator',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def observations(run,corpus):
    receipt=load(run/'run.json');need(receipt['pass']is True and receipt['exit_status']==0 and receipt['timed_out']is False and receipt['ELF_sha256']==ELF,'Complete normal exact-ELF software run required')
    text=(run/'stdout').read_text();module().validate(text,corpus)
    for name,wanted in receipt['output_sha256'].items():need(sha(name)==wanted,'Changed software output '+name)
    rows=[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith('IRIS_REGION ')]
    prefix=[json.loads(l)for l in(run/'features.jsonl').read_text().splitlines()];index={}
    for p in prefix:
        if p['csr']==0xb00:index.setdefault((p['hart'],p['value']),[]).append(p)
    result={}
    for row in rows:
        ends=[]
        for key in('start_cycle','end_cycle'):
            candidates=index.get((row['hart'],row[key]),[]);need(len(candidates)==1,'Unique actual CSR endpoints required');ends.append(candidates[0])
        lo,hi=ends;need(lo['sequence']<hi['sequence'],'Actual CSR order')
        def counter(path,key):
            delta=hi['memory'].get(path,{}).get(key,0)-lo['memory'].get(path,{}).get(key,0);need(type(delta)is int and delta>=0,'Nonnegative accepted-intent prefix');return delta
        result[row['case_id'],row['hart']]={'row':row,'cycles':row['end_cycle']-row['start_cycle'],
            'D_L2hit_algebra':counter('DRAM','l1misses')-counter('DRAM','l2misses'),'D_outer':counter('DRAM','l2misses'),
            'admitted_hits':counter('SCALAR_L2_SERVICE','L2_hit_lines'),'admitted_outer':counter('SCALAR_OUTER_SERVICE','L2_miss_lines'),
            'charged_alpha':counter('SCALAR_L2_SERVICE','charged_core_cycles'),'charged_beta':counter('SCALAR_OUTER_SERVICE','charged_core_cycles'),
            'CSR_sequences':[lo['sequence'],hi['sequence']]}
    return result
def main(a):
    train=a.train.resolve();baseline=a.baseline.resolve();admitted=a.admitted.resolve();out=a.output.resolve()
    report=load(train/'report.json');need(report['schema']=='iris.pow2_single_memory_TRAIN_only_export.v1'and report['status']=='passed'and report['reserved_timing_labels_excluded']is True and report['regions']==180,'Exact TRAIN-only reference role')
    need(sha(train/'regions.jsonl')==TRAIN_ROWS==report['regions_sha256']and report['ELF_sha256']==ELF,'Frozen TRAIN reference changed')
    reference=[json.loads(l)for l in(train/'regions.jsonl').read_text().splitlines()];need(len(reference)==180,'All180 TRAIN labels required')
    corpus_path=ROOT/'build/pow2-memory-single-v1/corpus.json';corpus=load(corpus_path);module().validate_corpus(corpus)
    canonical={(r['case_id'],r['hart']):r for r in module().canonical()if r['footprint_bytes']not in RESERVED}
    need(len(canonical)==180,'Expected canonical TRAIN subset')
    base=observations(baseline,corpus);new=observations(admitted,corpus);seen=set();joined=[]
    for r in reference:
        key=r['case_id'],r['hart'];need(key in canonical and key not in seen and r['internal_split']=='train'and r['footprint_bytes']not in RESERVED,'No reserved/duplicate labels');seen.add(key)
        need(all(type(r.get(k))is type(v)and r[k]==v for k,v in canonical[key].items()),'Reference geometry/golden')
        b,n=base[key],new[key];need(b['D_L2hit_algebra']==n['admitted_hits']and b['D_outer']==n['admitted_outer'],'Baseline/new admitted class mismatch: preserve all rows and refuse fit')
        need(type(r['cycles'])is int and r['cycles']>0,'Positive raw hardware delta')
        joined.append({'case_id':r['case_id'],'hart':r['hart'],'semantic_parent_case_id':r['semantic_parent_case_id'],'footprint_bytes':r['footprint_bytes'],'pass_index':r['pass_index'],'trial_id':r['trial_id'],'baseline_native_cycles':b['cycles'],'hardware_cycles':r['cycles'],'actual_admitted_L2_hit_lines':n['admitted_hits'],'actual_admitted_outer_lines':n['admitted_outer'],'baseline_instret':b['row']['instret_delta'],'hardware_instret':r['instret_delta']})
    need(seen==set(canonical),'All TRAIN groups/repeats retained')
    coefficients=[]
    for h in range(3):
        samples=[(r['actual_admitted_L2_hit_lines'],r['actual_admitted_outer_lines'],r['hardware_cycles']-r['baseline_native_cycles'],r['hardware_cycles'])for r in joined if r['hart']==h]
        (alpha,beta),design=nnls(samples);need(all(math.isfinite(x)and 0<=x<1e11 for x in(alpha,beta)),'Coefficient horizon')
        coefficients.append({'hart':h,'alpha_core_cycles_per_modeled_L2_hit_line':alpha,'beta_core_cycles_per_modeled_outer_miss_line':beta,'train_rows':len(samples),'design':design})
    out.mkdir(parents=True,exist_ok=False)
    paths=[Path(__file__).resolve(),train/'report.json',train/'regions.jsonl',baseline/'run.json',baseline/'stdout',baseline/'features.jsonl',admitted/'run.json',admitted/'stdout',admitted/'features.jsonl',corpus_path,ROOT/'benchmarks/pow2_memory_v1/validate.py']
    params={'schema':'iris.pow2_scalar_cache_TRAIN_NNLS.v1','pass':True,'coefficients':coefficients,'estimator':'Per-hart2-column nonnegative relative least squares on all60 TRAIN rows/hart; no intercept; y=HWcycles-actual oldselected native baseline; X=actual new admitted ordinary-scalar DRAM L2-hit/outer-miss line probes; exact paired class equality required','reserved_labels_consumed':False,'row_filtering':False,'physical_cache_latency_identified':False,'native_actual_replay_required':True,'input_sha256':{str(p):sha(p)for p in paths}}
    (out/'parameters.json').write_text(json.dumps(params,indent=2)+'\n');pid=sha(out/'parameters.json');parent=ROOT/'calibration/compute-fit-7bd5-hybrid-selected-v1/runtime.fixture';text=parent.read_text().replace('iris-empirical-hybrid7bd5-compute-v1 bounded','iris-pow2-TRAIN-scalar-cache-v1 bounded')+'\n'
    for p in coefficients:
        h=p['hart'];text+=f'empirical_scalar_l2_hit {h} {p["alpha_core_cycles_per_modeled_L2_hit_line"]:.17g} EFFECTIVE_POW2_TRAIN {pid} core_cycles\n';text+=f'empirical_scalar_outer_response {h} {p["beta_core_cycles_per_modeled_outer_miss_line"]:.17g} EFFECTIVE_POW2_TRAIN {pid} core_cycles\n'
    (out/'runtime.fixture').write_text(text);(out/'TRAIN-observations.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in joined))
    result={'pass':True,'fixture_sha256':sha(out/'runtime.fixture'),'parameters_sha256':pid,'rows':180,'reserved_labels_consumed':False,'outer_II_vector_Icache_store_atomic_formulas_unchanged':True,'actual_runtime_accuracy_qualified':False};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**result,'coefficients':coefficients}))
if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    for k in('train','baseline','admitted','output'):p.add_argument('--'+k,type=Path,required=True)
    main(p.parse_args())
