#!/usr/bin/env python3
"""Match actual admitted-load line probes to the frozen old TRAIN fit basis."""
import copy,importlib.util,json
from pathlib import Path
from scalar_l2_hit_run import ROOT,sha
def main():
    old=ROOT/'build/memory-footprints-WFI-groups-hybrid7bd5-selected-v1';new=ROOT/'build/scalar-L2hit-zero-basis-WFI360-v1';r=json.loads((new/'run.json').read_text())
    if r['pass']is not True or r['normal_guest_exit_verified']is not True:raise ValueError('Normal complete zero-cost witness required')
    spec=importlib.util.spec_from_file_location('WFI_validator',ROOT/'benchmarks/memory_footprints_mtime_wfi_groups_v8/validate.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    corpus=json.loads((ROOT/'build/memory-footprints-mtime-wfi-groups-fit-v8/corpus.json').read_text());v.validate((new/'stdout').read_text(),corpus)
    for name in('stdout','stderr'):
        if (old/name).read_bytes()!=(new/name).read_bytes():raise ValueError('Zero service changed raw program outputs '+name)
    a=[json.loads(l)for l in(old/'features.jsonl').read_text().splitlines()];b=[json.loads(l)for l in(new/'features.jsonl').read_text().splitlines()]
    if len(a)!=len(b)or len(b)!=720:raise ValueError('All720 genuine CSR endpoints required')
    for x,y in zip(a,b):
        z=copy.deepcopy(y);z['memory'].pop('SCALAR_L2_SERVICE',None)
        if x!=z:raise ValueError('Zero service changed old prefix fields/timeline')
    index={(x['hart'],x['sequence']):x for x in b};joins=json.loads((old/'CSR-endpoint-qualification.json').read_text())['joins'];cases={c['id']:c for c in corpus['cases']};rows=[json.loads(l[len('IRIS_REGION '):])for l in(new/'stdout').read_text().splitlines()if l.startswith('IRIS_REGION ')];witness=[]
    for row,join in zip(rows,joins):
        h=row['hart'];lo,hi=[index[h,join[k]]for k in('start_sequence','end_sequence')]
        def delta(path,key):return hi['memory'].get(path,{}).get(key,0)-lo['memory'].get(path,{}).get(key,0)
        old_basis=delta('DRAM','l1misses')-delta('DRAM','l2misses');admitted=delta('SCALAR_L2_SERVICE','L2_hit_lines')
        if old_basis!=admitted or delta('SCALAR_L2_SERVICE','charged_core_cycles')!=0:raise ValueError('Old residual basis is not exact admitted scalar-load L2-hit basis')
        excluded=[]
        for family in set(lo['features'])|set(hi['features']):
            if family.startswith('memory.')and family not in('memory.DRAM.load','memory.DRAM.store'):
                count=hi['features'].get(family,{}).get('instructions',0)-lo['features'].get(family,{}).get('instructions',0)
                if count:excluded.append([family,count])
        if excluded:raise ValueError('Unexpected LR/atomic/vector/MMIO work in fitted window '+repr(excluded))
        witness.append({'case_id':row['case_id'],'hart':h,'internal_split':cases[row['parent_case_id']]['internal_split'],'old_D_L1miss_minus_L2miss':old_basis,'actual_ordinary_load_L2hit_lines':admitted,'zero_charged_cycles':True,'excluded_memory_families_retired':excluded})
    out=ROOT/'build/scalar-L2hit-WFI-basis-proof-v1';out.mkdir(exist_ok=False)
    inputs=[Path(__file__).resolve(),old/'run.json',old/'stdout',old/'features.jsonl',old/'CSR-endpoint-qualification.json',new/'run.json',new/'stdout',new/'features.jsonl',ROOT/'calibration/WFI-L2-hit-effective-TRAIN-candidate-v1/parameters.json',ROOT/'build/scalar-L2hit-frozen-e8edb584/manifest.json']
    report={'schema':'iris.scalar_L2hit_frozen_TRAIN_basis_correspondence.v1','pass':True,'regions':360,'CSR_prefixes':720,'all_original_prefix_fields_bytevalue_identical':True,'raw_stdout_stderr_byteidentical':True,'TRAIN_rows':sum(x['internal_split']=='train'for x in witness),'basis_equal_for_all_regions':True,'coefficient_provenance_may_be_reused':True,'paused_candidate_runtime_qualification_reused':False,'actual_normal_zero_run_host_seconds':r['host_seconds'],'scope':'Actual service gate admits ordinary scalar DRAM loads only; new counter equals old D.L1miss-D.L2miss in every WFI ROI. Retired LR/SC/atomic/vector/MMIO deltas are0. Stores in this corpus contribute no fitted L2-hit probes. Model tag counts are not hardware cache observations.','witness':witness,'input_sha256':{str(p):sha(p)for p in inputs},'hardware_contacted':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(out/'report.json'),'train_rows':report['TRAIN_rows']}))
if __name__=='__main__':main()
