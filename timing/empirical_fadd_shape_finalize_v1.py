#!/usr/bin/env python3
"""Freeze an own-epoch positive service selection using TRAIN objectives only."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    sweep=ROOT/'calibration/compute-fit-fadd-shape-7de-sweep-v1'
    selection=json.loads((sweep/'selection.json').read_text())
    if selection.get('pass')is not True or selection.get('selection_uses_internal_validation')is not False:
        raise ValueError('Complete TRAIN-only actual sweep required')
    candidates={r['name']:r for r in selection['candidates']}
    for name,path in [('initial',ROOT/'calibration/compute-fit-fadd-shape-7de-initial-evaluation-v1/report.json'),
                      ('outer',ROOT/'calibration/compute-fit-fadd-shape-7de-outer-prior-evaluation-v2/report.json')]:
        d=json.loads(path.read_text());candidates[name]={'name':name,'pass':True,'report':str(path),'report_sha256':sha(path),'train_objective':d['train_objective']['value']}
    for r in candidates.values():
        if sha(r['report'])!=r['report_sha256']:raise ValueError('Actual sweep report changed')
    chosen=min(candidates,key=lambda name:(candidates[name]['train_objective'],name))
    folder=sweep/chosen if chosen not in ('initial','outer')else ROOT/('calibration/compute-fit-fadd-shape-7de-'+('initial-v1'if chosen=='initial'else'baseline-v1'))
    fixture=folder/('outer-prior.fixture'if chosen=='outer'else'runtime.fixture')
    out=ROOT/'calibration/compute-fit-fadd-shape-7de-selected-v1';out.mkdir(exist_ok=False)
    model=ROOT/'build/fadd-shape-frozen-7de1c02d';raw=ROOT/'calibration/compute-fit-fadd-shape-7de-constrained-v1/parameters.json'
    params={'schema':'iris.empirical_compute_parameters.v1','calibration_identity':'iris-empirical-compute-fadd-shape-7de-v1',
        'actual_parameter_fit_performed':True,'actual_calibrated_native_replay_completed':False,
        'parameter_packet_frozen_before_final_identity_replay':True,
        'native_binary_sha256':sha(model/'spike'),'uart_library_sha256':sha(model/'libsifive_uart.so'),
        'base_hz':500000000,'rtc_divider':1000,'counter_policy':'source-ungated-stall',
        'vme_work':'source-shape-subtiles-v1','scalar_FADD_source_phase':'source-HSD-pipeline-v1;EX-write4Shuttle/3Rocket;no-family-override',
        'raw_parameters_sha256':sha(raw),'cache':{},'instruction':{},'branch':{},'families':[],
        'own_epoch_training_selection':{'objective':'TRAIN parent/hart trial-median relative MSE; no internal-validation selection',
            'chosen':chosen,'candidate_objectives':{n:r['train_objective']for n,r in candidates.items()},'internal_validation_used_for_selection':False},
        'cost_semantics':{'read_base':'Effective conservative scalar DRAM read/coherence-fallback service; private integer L1-hit load front bypasses it. No physical L1/NoC latency claim.',
            'L1_miss':'Additional effective data cache miss response, not instruction service; private hits unchanged.',
            'vector':'Generic contiguous ATL load/store response costs; directL2, no L1D allocation; cache outer reservation retained.',
            'scalar_FADD':'Source-qualified fixed EX/write phases, precise late FPR/flags/FS publication; not an empirical fitted coefficient.',
            'async':'Positive integer extra backend durations over current RVV/VME source/scoped-work baseline, applied only at runtime opcode/config features.'},
        'prior_memory_parameters':{'path':str(ROOT/'calibration/empirical-priority-28a0-runtime-v2/parameters.json'),
            'sha256':sha(ROOT/'calibration/empirical-priority-28a0-runtime-v2/parameters.json'),'qualified_for_new_native':False},
        'unqualified':['Source frontend strict uninitialized-RAS refusal remains on some actual Merlin ELFs; no fallback or seed has been admitted.',
            'Scalar stores/atomics/polling and unsupported scalar-FP operations retain structural errors; optional guardedstore is not included.',
            'Approximate LRU/coherence and effective service queues are not full source cache/NoC/SerialTL timing.',
            'Outer545.732/461 and TCM/scratch values retain separately bound prior28 provenance and are unqualified transfers to this native.',
            'No BF16/FP8 vector-FADD timing fit, arbitrary shapes, wholeZephyr/end-to-end or universal2percent qualification.',
            'Known actualFPGA vector-transport hangs and unsupportedVMEcolumn semantics are not modeled.'],
        'global_heldout_timings_consumed':False,'full_2pct_certified':False,'full_model_certified':False,'source_image_association_verified':False}
    lines=fixture.read_text().splitlines()
    for line in lines:
        f=line.split()
        if not f:continue
        if f[0]=='empirical_cache_service':params['cache'][f[1]]=dict(zip(('read_base','write_base','l1_miss','outer_miss','outer_interval','dirty_extra'),map(float,f[2:8])))
        elif f[0]=='empirical_instruction_service':params['instruction'][f[1]]=dict(zip(('l1_miss','outer_miss','outer_interval'),map(float,f[2:5])))
        elif f[0]=='empirical_branch_service':params['branch'][f[1]]=float(f[2])
        elif f[0]=='empirical_family':params['families'].append({'hart':int(f[1]),'family':f[2],'resource':f[3],'setup':float(f[4]),'work':float(f[5]),'interval':int(f[6]),'scope':'unqualified prior28 path transfer'if'UNIDENTIFIED'in f[-3]else'own7de positive TRAIN effective cost'})
    (out/'parameters.json').write_text(json.dumps(params,indent=2,sort_keys=True)+'\n');digest=sha(out/'parameters.json');rendered=[]
    for line in lines:
        f=line.split()
        if f and f[0]=='empirical_profile':f[2]=params['calibration_identity']
        if f and f[0]in ('empirical_family','empirical_cache_service','empirical_instruction_service','empirical_branch_service'):
            f[-3]='OWN_7DE_TRAIN_OR_EXPLICIT_PRIOR';f[-2]=digest
        rendered.append(' '.join(f)if f else'')
    (out/'runtime.fixture').write_text('\n'.join(rendered)+'\n')
    sensitive=list(rendered);found=set()
    for i,line in enumerate(sensitive):
        f=line.split()
        if f and f[0]=='empirical_family'and f[2]=='rvv.integer':f[4]=str(float(f[4])+20);found.add(int(f[1]));sensitive[i]=' '.join(f)
    for h in set(range(3))-found:
        resource='fit.sensitivity.integer'+str(h);sensitive.extend(['resource '+resource+' 1',f'empirical_family {h} rvv.integer {resource} 20 0 1 SELFTEST_ONLY {digest} core_cycles'])
    (out/'sensitivity.fixture').write_text('\n'.join(sensitive)+'\n')
    inputs=[Path(__file__).resolve(),sweep/'selection.json',fixture,raw,ROOT/'build/compute-fit-v3/split.json',*[Path(r['report'])for r in candidates.values()]]
    record={'schema':'iris.fadd_shape_actual_selection.v1','pass':True,'chosen':chosen,'train_objectives':params['own_epoch_training_selection']['candidate_objectives'],
        'parameters_sha256':digest,'fixture_sha256':sha(out/'runtime.fixture'),'final_identity_replay_completed':False,
        'internal_validation_used_for_selection':False,'global_heldout_timings_consumed':False,'input_sha256':{str(p):sha(p)for p in inputs}}
    (out/'selection.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))


if __name__=='__main__':main()
