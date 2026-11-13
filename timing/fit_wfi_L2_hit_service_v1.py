#!/usr/bin/env python3
"""One fixed TRAIN-only positive effective tag-service correction, no intercept."""
import argparse
import collections
import json
import math
from pathlib import Path
from compare_wfi_footprints_v2 import ROOT,sha,load

def main(output):
    baseline=ROOT/'build/memory-footprints-WFI-groups-hybrid7bd5-selected-v1'
    comparison=ROOT/'build/memory-footprints-WFI-hybrid7bd5-comparison-v2'
    original=ROOT/'calibration/compute-fit-7bd5-hybrid-selected-v1/runtime.fixture'
    rows=[json.loads(l)for l in(comparison/'regions.jsonl').read_text().splitlines()]
    joins=load(baseline/'CSR-endpoint-qualification.json')['joins']
    prefixes=[json.loads(l)for l in(baseline/'features.jsonl').read_text().splitlines()]
    index={(x['hart'],x['sequence']):x for x in prefixes};records=[]
    for row,join in zip(rows,joins):
        hart=row['hart'];start,end=[index[hart,join[key]]for key in('start_sequence','end_sequence')]
        counters={}
        for path in set(start['memory'])|set(end['memory']):
            a,b=start['memory'].get(path,{}),end['memory'].get(path,{})
            delta={k:b.get(k,0)-a.get(k,0)for k in set(a)|set(b)}
            if any(type(v)is not int or v<0 for v in delta.values()):raise ValueError('Counter reset / invalid prefix delta')
            counters[path]=delta
        data=counters.get('DRAM',{});work=data.get('l1misses',0)-data.get('l2misses',0)
        if work<0:raise ValueError('L2-miss cancellation basis negative')
        records.append({**row,'model_memory_prefix_delta':counters,'effective_data_L2_hit_charge_basis':work})
    # Estimator fixed before candidate evaluation: per-hart least squares of
    # relative residual, alpha>=0 and <=old OUTER, using ONLY train parents.
    parameters=[]
    for hart in range(3):
        train=[r for r in records if r['hart']==hart and r['internal_split']=='train']
        den=sum((r['effective_data_L2_hit_charge_basis']/r['hardware_cycles'])**2 for r in train)
        if den<=0:raise ValueError('Unidentified effective service coefficient')
        num=sum(r['effective_data_L2_hit_charge_basis']*(r['hardware_cycles']-r['software_cycles'])/r['hardware_cycles']**2 for r in train)
        alpha=min(545.732041126,max(0,num/den))
        if not math.isfinite(alpha):raise ValueError('Nonfinite coefficient')
        parameters.append({'hart':hart,'read_base':0,'write_base':0,'L1_miss_additional_core_cycles':alpha,
            'outer_miss_additional_core_cycles':545.732041126-alpha,'outer_launch_interval_core_cycles':461,
            'dirty_victim_extra_core_cycles':0,'train_rows':len(train),
            'train_nonzero_basis_rows':sum(r['effective_data_L2_hit_charge_basis']>0 for r in train),
            'design_rank':1,'basis_weighted_squared_norm':den,'status':'EFFECTIVE_TRAIN_TAG_SERVICE_NOT_PHYSICAL_LATENCY'})
    output.mkdir(parents=True,exist_ok=False)
    source=[Path(__file__).resolve(),original,comparison/'report.json',comparison/'regions.jsonl',baseline/'features.jsonl',baseline/'CSR-endpoint-qualification.json']
    params={'schema':'iris.WFI_train_effective_L2_hit_service.v1','parameters':parameters,
        'estimator':'Fixed per-hart bounded nonnegative relative least squares; no intercept; x=D.L1miss-D.L2miss; y=HW_mcycle_delta-baseline_mcycle_delta; weights=1/HW_delta^2',
        'split':'Existing frozen semantic-parent internal_split=train only; all trials/passes stay with parent',
        'READ_coefficient_fixed_zero_reason':'Warm L1 response returns before READ charge; prefix counts lack charged-READ counter',
        'Icache_services_unchanged':True,'other_family_costs_unchanged':True,'outer_total_scalar_miss_additional_latency_preserved':True,
        'physical_L2_latency_identified':False,'source_L2_random_policy_not_implemented':True,
        'linearized_fit_not_actual_runtime_accuracy':True,'candidate_live_replay_required':True,
        'internal_validation_used_for_coefficients':False,'global_heldout_data_consumed':False,
        'input_sha256':{str(p):sha(p)for p in source}}
    (output/'parameters.json').write_text(json.dumps(params,indent=2)+'\n');pid=sha(output/'parameters.json')
    lines=[];changes=[]
    for line in original.read_text().splitlines():
        f=line.split()
        if f and f[0]=='empirical_profile':f[2]='iris-empirical-WFI-TRAIN-L2-hit-v1';line=' '.join(f)
        elif f and f[0]=='empirical_cache_service':
            p=parameters[int(f[1])];old=line
            f[4]=format(p['L1_miss_additional_core_cycles'],'.14g');f[5]=format(p['outer_miss_additional_core_cycles'],'.14g');f[8]='EFFECTIVE_WFI_TRAIN_TAG_SERVICE';f[9]=pid;line=' '.join(f);changes.append({'before':old,'after':line})
        lines.append(line)
    fixture=output/'runtime.fixture';fixture.write_text('\n'.join(lines)+'\n')
    old_instructions=[x for x in original.read_text().splitlines()if x.startswith('empirical_instruction_service ')]
    new_instructions=[x for x in lines if x.startswith('empirical_instruction_service ')]
    if old_instructions!=new_instructions or len(changes)!=3:raise ValueError('Instruction service or cache-row scope changed')
    (output/'diagnostic-region-features.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in records))
    group=[]
    buckets=collections.defaultdict(list)
    for r in records:buckets[(r['hart'],r['footprint_bytes'],r['mask'])].append(r)
    for key,values in sorted(buckets.items()):
        sums={k:sum(r['model_memory_prefix_delta'].get('DRAM',{}).get(k,0)for r in values)for k in('accesses','reads','writes','l1hits','l1misses','l2hits','l2misses')}
        group.append({'hart':key[0],'footprint_bytes':key[1],'mask':key[2],'regions':len(values),'model_DRAM_counter_sums':sums})
    (output/'diagnostic-groups.json').write_text(json.dumps(group,indent=2)+'\n')
    report={'schema':'iris.WFI_effective_service_candidate_frozen.v1','pass':True,'estimator_frozen_before_candidate_evaluation':True,
        'candidate_not_runtime_qualified':True,'fixture_sha256':sha(fixture),'parameters_sha256':pid,'changes':changes,
        'modeled_tag_counter_units':'accesses=count accepted intents; hits/misses=count64B line probes; bytes=requested bytes',
        'model_classifications_are_not_hardware_cache_observations':True,
        'scope':'Model LRU tag history and charge-boundary approximation retained; effective correction only; all360 diagnostics retained; no filtering/ROI-ID prediction/intercept.',
        'input_sha256':{str(p):sha(p)for p in [*source,output/'parameters.json',fixture]},'hardware_contacted':False,'native_changed':False}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'parameters_sha256':pid,'fixture_sha256':sha(fixture),'report_sha256':sha(output/'report.json'),'parameters':parameters}))

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);main(p.parse_args().output.resolve())
