#!/usr/bin/env python3
"""Compare fixed same-ELF memory predictions with a complete managed reference.

This tool does not fit parameters. Target/pattern/case labels are used for
reporting only, never for a simulator prediction.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'firesim'))
from analyze_campaign import read_archive, select_guest_uart
from memory_routes_current_audit_v2 import audit, rows_check

ARCHIVE = 'e85e9394166139fc34a94bc684ded090ed82c8fef686448276af8cb25ad31eb7'


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): value.update(block)
    return value.hexdigest()


def verify_map(mapping):
    for path, expected in mapping.items():
        if not isinstance(path, str) or not isinstance(expected, str) or sha(path) != expected:
            raise ValueError('Changed bound file: '+str(path))


def quantile(values, fraction):
    values = sorted(values)
    if not values: return None
    rank = fraction*(len(values)-1); lower = int(rank); upper = min(lower+1, len(values)-1)
    return values[lower]+(values[upper]-values[lower])*(rank-lower)


def metrics(rows):
    signed = [r['signed_error_percent'] for r in rows]; absolute = list(map(abs, signed))
    return {'regions': len(rows), 'median_signed_error_percent': statistics.median(signed),
        'median_absolute_error_percent': statistics.median(absolute), 'p90_absolute_error_percent': quantile(absolute, .9),
        'max_absolute_error_percent': max(absolute), 'within_2_percent': sum(x <= 2 for x in absolute),
        'min_signed_error_percent': min(signed), 'max_signed_error_percent': max(signed),
        'instret_mismatches': sum(r['instret_matches'] is not True for r in rows)}


def group_metrics(rows, keys):
    groups = collections.defaultdict(list)
    for row in rows: groups[tuple(row[k] for k in keys)].append(row)
    return [{**dict(zip(keys, key)), **metrics(values)} for key, values in sorted(groups.items())]


def verify_reference(analysis, build):
    report = json.loads((analysis/'report.json').read_text()); job = Path(report['job'])
    for key in ('pass', 'archive_verified', 'functional_checks_passed', 'managed_run_passed', 'fitting_only', 'fitting_observations_available'):
        if report.get(key) is not True: raise ValueError('Unqualified memory reference: '+key)
    if (report.get('schema') != 'iris.memory_routes_current_archive_analysis.v1'
            or report.get('global_heldout') is not False or report.get('archive_sha256') != ARCHIVE
            or report.get('cleanup_status') != 'passed' or report.get('capture_status') != 'captured'):
        raise ValueError('Wrong fitting-only memory reference identity')
    if sha(job/'run.json') != report['current_run_manifest_sha256']: raise ValueError('Run manifest changed')
    verify_map({str(analysis/name): value for name, value in report['artifact_sha256'].items()})
    current = json.loads((job/'run.json').read_text()); archive = Path(report['archive'])
    if sha(archive) != ARCHIVE or current['capture']['archive_sha256'] != ARCHIVE:
        raise ValueError('Actual archive bytes changed')
    data, identities = read_archive(archive, current['capture']['captured_run_manifest_sha256'])
    manifest = json.loads(data['job/run.json'])
    if (manifest.get('fitting_only') is not True or manifest.get('global_heldout') is not False
            or manifest.get('expected_regions') != 2592 or manifest.get('status') != 'completed_uncertified'
            or manifest.get('cleanup_status') != 'passed' or manifest.get('error') is not None):
        raise ValueError('Archived lifecycle/reference role mismatch')
    phases = [(r['task'], r['status'], r['cleanup_phase'], r['returncode'], r['timed_out']) for r in manifest['commands']]
    if phases != [('kill','passed',False,0,False), ('infrasetup','passed',False,0,False),
                  ('runworkload','passed',False,0,False), ('kill','passed',True,0,False)]:
        raise ValueError('Full four-phase successful managed run required')
    if identities['job/manager/workloads/iris-batch/batch.elf'] != sha(build/'memory-routes.elf'):
        raise ValueError('Hardware/native measured ELF differs')
    if identities['job/corpus.json'] != sha(build/'corpus.json') or data['job/corpus.json'] != (build/'corpus.json').read_bytes():
        raise ValueError('Hardware/native corpus differs')
    member, proof = select_guest_uart(data, identities)
    rows = [json.loads(x.split(' ',1)[1]) for x in data[member].decode().splitlines() if x.startswith('IRIS_REGION ')]
    if rows != json.loads((analysis/'regions.json').read_text()): raise ValueError('Derived hardware rows differ from archived UART')
    return report, current, rows


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ('build','run','qualification','reference','output'): parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args(); build=args.build.resolve(); run=args.run.resolve(); out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    corpus, layout, corpus_proof = audit(build)
    ref, manifest, hardware = verify_reference(args.reference.resolve(), build); rows_check(hardware, corpus)
    native = json.loads((run/'run.json').read_text()); qualification=json.loads((args.qualification/'report.json').read_text())
    if (native.get('pass') is not True or native.get('debugger_exit_status') != 0 or native.get('timed_out') is not False
            or native.get('normal_guest_exit_verified') is not False or native.get('regions') != 2592
            or qualification.get('pass') is not True or qualification.get('counter_word_controls') != 14
            or qualification.get('prefix_controls') != 8 or qualification.get('parameter_fit_performed') is not False):
        raise ValueError('Complete fixed native replay/typed controls required')
    verify_map(native['input_sha256']); verify_map(native['output_sha256']); verify_map(qualification['input_sha256'])
    predicted=[json.loads(x) for x in (run/'region-features.jsonl').read_text().splitlines()]; rows_check(predicted, corpus)
    cases={c['case_id']:c for c in corpus['cases']}; split=json.loads((build/'split.json').read_text())['split']; joined=[]
    for model, actual in zip(predicted, hardware):
        case=cases[model['case_id']]
        if (model['case_id'],model['hart']) != (actual['case_id'],actual['hart']): raise ValueError('Prediction/reference row mismatch')
        hc=actual['end_cycle']-actual['start_cycle']; nc=model['end_cycle']-model['start_cycle']; hart=model['hart']
        path=('LOCAL_TCM' if case['target_region']=='tcm'+str(hart) else 'REMOTE_TCM') if case['target_region'].startswith('tcm') else 'SCRATCHPAD' if case['target_region']=='scratchpad' else 'DRAM'
        memory=model['memory']; data=memory.get(path,{})
        row={'case_id':model['case_id'],'parent_case_id':case['parent_case_id'],'semantic_parent_case_id':case['semantic_parent_case_id'],
            'partition':split[case['semantic_parent_case_id']], 'hart':hart,'trial_id':case['trial_id'],'target':case['target_region'],
            'path':path,'kind':case['kind'],'mask':case['mask'],'active_harts':bin(case['mask']).count('1'),
            'pattern':'hart-banks' if case['spread'] else 'bank0' if case['stride']==128 else 'alternating',
            'n':case['n'],'stride':case['stride'],'spread':case['spread'],'kernel_requested_bytes':case['kernel_read_bytes_per_hart']+case['kernel_write_bytes_per_hart'],
            'hardware_cycles':hc,'native_cycles':nc,'signed_error_cycles':nc-hc,'signed_error_percent':100*(nc-hc)/hc,
            'hardware_instret':actual['instret_delta'],'native_instret':model['instret_delta'],'instret_matches':actual['instret_delta']==model['instret_delta'],
            'actual_model_data_path_features':data,'actual_model_instruction_cache_features':{k:v for k,v in memory.items() if k.startswith('ICACHE')},
            'actual_model_all_memory_features':memory,'actual_model_features':model['features'],
            'actual_model_global_resource_occupancy':model['resource_occupancy'], 'resource_occupancy_scope':'global interval, not exclusive attribution to measured hart'}
        joined.append(row)
    if any(not x['instret_matches'] for x in joined):
        # Keep these rows in the report; never discard them to improve accuracy.
        pass
    groups=collections.defaultdict(list)
    for row in joined: groups[row['parent_case_id'],row['hart']].append(row)
    repetitions=[]
    for (parent,hart), values in sorted(groups.items()):
        values.sort(key=lambda r:r['trial_id'])
        if [x['trial_id'] for x in values] != [0,1,2]: raise ValueError('Complete three-trial repetition group required')
        hw=[x['hardware_cycles'] for x in values]; nv=[x['native_cycles'] for x in values]
        hm=statistics.median(hw); nm=statistics.median(nv)
        repetitions.append({**{k:values[0][k] for k in ('parent_case_id','semantic_parent_case_id','partition','hart','target','path','kind','mask','pattern','n')},
            'hardware_cycles':hw,'native_cycles':nv,'hardware_median':hm,'native_median':nm,
            'hardware_population_CV':statistics.pstdev(hw)/statistics.mean(hw),'native_population_CV':statistics.pstdev(nv)/statistics.mean(nv),
            'median_signed_error_percent':100*(nm-hm)/hm,'all_trials_identical_hardware':len(set(hw))==1})
    (out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in joined))
    (out/'repetitions.json').write_text(json.dumps(repetitions,indent=2)+'\n')
    scalar_keys=[k for k,v in joined[0].items() if not isinstance(v,dict)]
    with (out/'regions.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=scalar_keys);writer.writeheader();writer.writerows({k:r[k] for k in scalar_keys} for r in joined)
    fixture=next(Path(s.split('=',1)[1]) for s in native['argv'] if s.startswith('--iris-timing-fixture='))
    tcmscratch=[line for line in fixture.read_text().splitlines() if line.startswith('empirical_family ') and any(p in line for p in ('memory.LOCAL_TCM.','memory.REMOTE_TCM.','memory.SCRATCHPAD.'))]
    if len(tcmscratch)!=16: raise ValueError('Unexpected frozen TCM/scratch rule set')
    summaries={','.join(keys):group_metrics(joined,keys) for keys in [('target',),('target','kind'),('path','kind','hart'),('target','pattern'),
        ('target','kind','pattern','mask'),('partition',),('trial_id',),('hart',),('target','n')]}
    (out/'group-errors.json').write_text(json.dumps(summaries,indent=2)+'\n')
    report={'schema':'iris.memory_routes_current_fixed_prediction_comparison.v1','pass':True,'regions':2592,'repetition_groups':864,
        'fixed_parameters_unchanged':True,'parameter_fit_performed':False,'coefficient_selection_performed':False,
        'global_heldout_timings_consumed':False,'new_memory_fitting_reference_consumed':True,'hardware_contacted':False,
        'full_2pct_certified':False,'source_image_association_verified':False,'timing_accuracy_certified':False,
        'normal_guest_exit_verified_by_timed_replay':False,'timed_scope':'all measured regions; intentional quiescent post-ROI debugger stop',
        'separate_functional_normal_exit_schedules':[0,17], 'all_numeric_goldens':True,'actual_CSR_ELF_boundary_joins':5184,
        'metrics_all':metrics(joined),'metrics_by_target':summaries['target'],'metrics_by_target_kind':summaries['target,kind'],
        'repetition_statistics':{'hardware_groups_with_identical_three_trials':sum(x['all_trials_identical_hardware'] for x in repetitions),
            'hardware_median_population_CV':statistics.median(x['hardware_population_CV'] for x in repetitions),
            'hardware_max_population_CV':max(x['hardware_population_CV'] for x in repetitions)},
        'existing_TCM_scratch_rules':tcmscratch,'prior_rule_scope':'16 imported effective TCM/scratch rules; not fitted or selected on this new memory reference',
        'identifiability':corpus_proof['identifiability_scope']+[
            'All masks preserve disjoint per-hart value windows: shared bank/target contention, not same-data-line ownership transfer.',
            'Chase/read/write and two N values can constrain effective service plus fixed overhead; physical latency versus issue interval remains confounded.',
            'Native Icache and data-cache counters describe this approximate model, not hardware hit/miss observations.',
            'Instruction-cache cold/history cost, active unmeasured barrier harts, and load/store frontend cost contribute inside these whole-region measurements.',
            'Named TCM/scratch service queues currently aggregate banks; source address bit6 patterns remain in every row for structural residual diagnosis.',
            'Source-facing startup FASED 30/30 observations are not physical CPU/L2/serial latency and are not inferred from these regions.'],
        'reference':{'analysis':str(args.reference.resolve()/'report.json'),'run_manifest':str(Path(ref['job'])/'run.json'),
            'capture_archive_sha256':ARCHIVE,'elf_sha256':sha(build/'memory-routes.elf'),'runtime_identity':ref['runtime_identity']},
        'native':{'run':str(run/'run.json'),'fixture':str(fixture),'fixture_sha256':sha(fixture),'host_seconds':native['host_seconds']},
        'input_sha256':{str(p):sha(p) for p in [Path(__file__).resolve(),ROOT/'timing/memory_routes_current_audit_v2.py',ROOT/'firesim/analyze_campaign.py',
            args.reference.resolve()/'report.json',args.reference.resolve()/'regions.json',Path(ref['job'])/'run.json',Path(ref['archive']),
            run/'run.json',run/'region-features.jsonl',args.qualification.resolve()/'report.json',fixture,
            *[build/name for name in ('memory-routes.elf','ready.json','corpus.json','split.json','readback-layout.json')]]}}
    report['artifact_sha256']={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'metrics_all':report['metrics_all'],'output':str(out)}))


if __name__=='__main__': main()
