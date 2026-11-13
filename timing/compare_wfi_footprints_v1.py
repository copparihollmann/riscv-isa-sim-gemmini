#!/usr/bin/env python3
"""Compare every region of the exact WFI footprint ELF; never fit parameters."""
import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import math
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ELF='6de1157eea2aeffa801e93edb4d85c60ee5a6b13b9ef3df9d527472711de7de9'
ROLE='memory_footprint_WFI_global_time_groups_fitting_v1'
VALIDATOR=ROOT/'benchmarks/memory_footprints_mtime_wfi_groups_v8/validate.py'
spec=importlib.util.spec_from_file_location('wfi_footprint_validator',VALIDATOR)
validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)

def need(value,reason):
    if not value:raise ValueError(reason)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def load(path):
    def refuse(x):raise ValueError('Nonfinite JSON: '+x)
    return json.loads(Path(path).read_text(),parse_constant=refuse)
def inventory(mapping):
    need(isinstance(mapping,dict)and mapping,'Nonempty input inventory required')
    for name,wanted in mapping.items():
        need(Path(name).is_absolute()and isinstance(wanted,str)and len(wanted)==64,'Absolute SHA inventory')
        need(sha(name)==wanted,'Changed bound input: '+name)
def raw_rows(text):
    return[json.loads(l[len('IRIS_REGION '):])for l in text.splitlines()if l.startswith('IRIS_REGION ')]
def bracket(row):
    before,after=row['mtime_before'],row['mtime_after']
    need(type(before)is int and type(after)is int and 0<=before<=after<2**64,'Typed forward CLINT samples')
    ticks=after-before;quantized=ticks*1000
    return {'mtime_before':before,'mtime_after':after,'mtime_delta':ticks,
            'quantized_source_core_cycles':quantized,
            'enclosing_window_lower_source_core_cycles':max(0,quantized-1000),
            'enclosing_window_upper_source_core_cycles':quantized+1000}
def metrics(rows):
    need(rows,'Nonempty comparison group')
    signed=sorted(r['signed_error_percent']for r in rows)
    absolute=sorted(abs(x)for x in signed)
    total_hw=sum(r['hardware_cycles']for r in rows);total_sw=sum(r['software_cycles']for r in rows)
    return {'regions':len(rows),'median_signed_error_percent':statistics.median(signed),
            'median_absolute_error_percent':statistics.median(absolute),
            'p90_absolute_error_percent':absolute[math.ceil(.9*len(absolute))-1],
            'max_absolute_error_percent':absolute[-1],
            'min_signed_error_percent':signed[0],'max_signed_error_percent':signed[-1],
            'within_2percent':sum(x<=2 for x in absolute),
            'within_2percent_fraction':sum(x<=2 for x in absolute)/len(rows),
            'hardware_cycle_sum':total_hw,'software_cycle_sum':total_sw,
            'cycle_sum_signed_error_percent':100*(total_sw-total_hw)/total_hw,
            'instret_mismatches':sum(not r['instret_equal']for r in rows),
            'CLINT_enclosing_window_intervals_overlap':sum(r['CLINT_enclosing_intervals_overlap']for r in rows)}

def compare_rows(sw,hw,corpus,joins):
    need(len(sw)==len(hw)==360,'All360 rows required; no filtering')
    spec={c['id']:c for c in corpus['cases']};paired=[];seen=set()
    need(len(joins)==360,'All360 actual model CSR joins required')
    identity=['case_id','parent_case_id','suite','region','trial_id','pass_index','hart',
              'footprint_bytes','body_loads','requested_bytes','checksum','expected_checksum','pass']
    for index,(s,h,j)in enumerate(zip(sw,hw,joins)):
        for field in identity:
            need(type(s.get(field))is type(h.get(field))and s.get(field)==h.get(field),f'Row{index} identity/golden mismatch: '+field)
        key=(s['case_id'],s['hart']);need(key not in seen,'Duplicate region');seen.add(key)
        need(type(s['pass'])is bool and s['pass']and s['checksum']==s['expected_checksum'],'Actual positive checksum required')
        need(j['case_id']==s['case_id']and j['hart']==s['hart'],'Model CSR ownership join mismatch')
        c=spec[s['parent_case_id']]
        sc=s['end_cycle']-s['start_cycle'];hc=h['end_cycle']-h['start_cycle']
        need(type(sc)is int and type(hc)is int and sc>0 and hc>0,'Positive program counter deltas required')
        sb,hb=bracket(s),bracket(h)
        lo=sb['enclosing_window_lower_source_core_cycles']-hb['enclosing_window_upper_source_core_cycles']
        hi=sb['enclosing_window_upper_source_core_cycles']-hb['enclosing_window_lower_source_core_cycles']
        hwlo=hb['enclosing_window_lower_source_core_cycles'];hwhi=hb['enclosing_window_upper_source_core_cycles']
        relative_lo=100*(sb['enclosing_window_lower_source_core_cycles']/hwhi-1)
        relative_hi=100*(sb['enclosing_window_upper_source_core_cycles']/hwlo-1)if hwlo else None
        span=j['end_global_read_cycle']-j['start_global_read_cycle']
        paired.append({'index':index,'case_id':s['case_id'],'semantic_parent_case_id':c['semantic_parent_case_id'],
            'hart':s['hart'],'footprint_bytes':s['footprint_bytes'],'mask':c['mask'],'active_harts':c['active_harts'],
            'trial_id':s['trial_id'],'pass_index':s['pass_index'],'internal_split':c['internal_split'],
            'body_loads':s['body_loads'],'requested_bytes':s['requested_bytes'],
            'software_start_mcycle':s['start_cycle'],'software_end_mcycle':s['end_cycle'],
            'hardware_start_mcycle':h['start_cycle'],'hardware_end_mcycle':h['end_cycle'],
            'software_cycles':sc,'hardware_cycles':hc,'cycle_difference':sc-hc,
            'signed_error_percent':100*(sc-hc)/hc,'absolute_error_percent':100*abs(sc-hc)/hc,
            'software_cycles_per_body_load':sc/s['body_loads'],'hardware_cycles_per_body_load':hc/s['body_loads'],
            'software_instret_delta':s['instret_delta'],'hardware_instret_delta':h['instret_delta'],
            'instret_equal':s['instret_delta']==h['instret_delta'],
            'software_CLINT':sb,'hardware_CLINT':hb,
            'CLINT_enclosing_difference_lower_source_core_cycles':lo,
            'CLINT_enclosing_difference_upper_source_core_cycles':hi,
            'CLINT_enclosing_intervals_overlap':lo<=0<=hi,
            'CLINT_enclosing_signed_error_lower_percent':relative_lo,
            'CLINT_enclosing_signed_error_upper_percent':relative_hi,
            'software_global_CSR_read_span':span,
            'software_CSR_span_within_CLINT_enclosing_upper':span<=sb['enclosing_window_upper_source_core_cycles']})
    return paired

def groups(rows,fields):
    buckets=collections.defaultdict(list)
    for r in rows:buckets[tuple(r[f]for f in fields)].append(r)
    return[{**dict(zip(fields,key)),**metrics(value)}for key,value in sorted(buckets.items())]

def main(args):
    software,hardware,job,output=[Path(p).resolve()for p in(args.software,args.hardware,args.hardware_job,args.output)]
    need(not output.exists(),'Fresh output directory required')
    hr=load(hardware/'report.json');need(sha(hardware/'report.json')==args.expected_hardware_report_sha256,'Exact root-approved hardware analysis SHA required')
    need(hr.get('pass')is True and hr.get('archive_verified')is True and hr.get('regions')==360,'Complete strict hardware analysis required')
    need(hr.get('fitting_only')is True and hr.get('global_heldout')is False,'Fitting data role required')
    need(hr.get('compiled_case_records')==105 and hr.get('declared_host_cases')==210,'Exact105/210 compiled corpus')
    need([(p['task'],p['status'])for p in hr['lifecycle']]==[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')],'Full managed lifecycle required')
    need(all(p['returncode']==0 and p['timed_out']is False for p in hr['lifecycle']),'Unbounded or failed hardware phase')
    jr=load(job/'run.json');need(jr['status']=='completed_uncertified'and jr['cleanup_status']=='passed'and jr.get('error')is None and jr.get('cleanup_error')is None,'Quiescent successful owned cleanup required')
    need(jr['campaign_role']==ROLE and jr['elf_sha256']==ELF,'Exact WFI campaign role / ELF required')
    cap=jr['capture'];need(cap['status']=='captured'and cap['returncode']==0,'Quiescent archive required')
    archive=Path(cap['archive']);need(sha(archive)==cap['archive_sha256']==hr['archive_sha256'],'Actual archive byte identity required')
    need(sha(job/'run.json')==hr['current_manifest_sha256'],'Hardware manifest changed since analysis')
    inventory(hr['input_sha256'])
    for name,wanted in hr['output_sha256'].items():need(sha(hardware/name)==wanted,'Hardware analysis output changed: '+name)
    need(sha(hardware/'observed.elf')==ELF,'Actual observed hardware ELF mismatch')
    sr=load(software/'run.json');sq=load(software/'qualification.json');csr=load(software/'CSR-endpoint-qualification.json')
    need(sr['pass']is True and sr['status']=='passed_guest_exit'and sr['exit_status']==0 and sr['timed_out']is False,'Actual normal software exit required')
    need(sr['ELF_sha256']==ELF and sq['pass']is True and sq['normal_guest_exit_verified']is True,'Qualified same-ELF software run required')
    need(csr['pass']is True and csr['regions']==360 and csr['actual_counter_endpoints']==720,'All720 actual model CSR endpoints required')
    inventory(sq['input_sha256']);inventory(csr['input_sha256'])
    for name,wanted in sr['output_sha256'].items():need(sha(name)==wanted,'Software raw output changed: '+name)
    corpus=load(hardware/'corpus.json');validator.validate_corpus(corpus)
    source_corpus=ROOT/'build/memory-footprints-mtime-wfi-groups-fit-v8/corpus.json'
    need(sha(hardware/'corpus.json')==sha(source_corpus),'Exact new software/hardware corpus identity required')
    st=(software/'stdout').read_text();ht=(hardware/'uartlog').read_text()
    validator.validate(st,corpus);validator.validate(ht,corpus)
    sw,hw=raw_rows(st),raw_rows(ht);exported=[json.loads(l)for l in(hardware/'regions.jsonl').read_text().splitlines()]
    need(len(exported)==360,'Complete hardware exported rows required')
    for raw,export in zip(hw,exported):need(all(export.get(k)==v and type(export.get(k))is type(v)for k,v in raw.items()),'Exported hardware rows differ from raw UART')
    rows=compare_rows(sw,hw,corpus,csr['joins'])
    output.mkdir(parents=True)
    (output/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True,allow_nan=False)+'\n'for r in rows))
    with(output/'regions.csv').open('w',newline='')as f:
        columns=[k for k,v in rows[0].items()if not isinstance(v,(dict,list))];w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)
    aggregates={name:groups(rows,fields)for name,fields in[
        ('by_hart',['hart']),('by_size',['footprint_bytes']),('by_mask',['mask']),('by_pass',['pass_index']),
        ('by_trial',['trial_id']),('by_internal_split',['internal_split']),
        ('by_hart_size_mask_pass',['hart','footprint_bytes','mask','pass_index'])]}
    (output/'groups.json').write_text(json.dumps(aggregates,indent=2,allow_nan=False)+'\n')
    paths=[Path(__file__).resolve(),VALIDATOR,source_corpus,hardware/'report.json',job/'run.json',archive,
           *[hardware/n for n in('observed.elf','corpus.json','uartlog','regions.jsonl')],
           *[software/n for n in('run.json','qualification.json','CSR-endpoint-qualification.json','stdout','native-summary.json')]]
    report={'schema':'iris.same_ELF_WFI_footprint_software_hardware_comparison.v1','pass':True,
        'comparison_complete':True,'ELF_sha256':ELF,'regions':360,'filtering_performed':False,
        'fitting_only':True,'global_heldout':False,'parameters_refit':False,'native_changed':False,'hardware_contacted':False,
        'summary':metrics(rows),'software_execution':{k:sq[k]for k in('host_seconds','actual_MIPS','global_modeled_target_cycles','retired_instructions_by_hart')},
        'error_definition':'100*(software_mcycle_delta-hardware_mcycle_delta)/hardware_mcycle_delta; positive means overprediction',
        'p90_definition':'Nearest-rank empirical quantile, index ceil(0.9*N)-1',
        'CLINT_scope':{'raw_samples_retained':True,'window':'Encloses CSR ROI plus sampling overhead; no overhead subtraction',
            'mtime_hz':500000,'source_core_cycles_per_tick':1000,'each_window_quantization_bound_source_core_cycles':1000,
            'difference_quantization_bound_source_core_cycles':2000,'subtick_relative_upper_error_when_reference_lower_zero':None,
            'absolute_per_hart_mcycle_origins_compared':False,'WFI_outside_ROI_can_pause_mcycle':True,
            'physical_frequency_or_cache_traffic_measured':False},
        'timing_2percent_certified':False,'full_model_certified':False,'source_loaded_image_attestation':False,
        'input_sha256':{str(p):sha(p)for p in paths},
        'output_sha256':{p.name:sha(p)for p in output.iterdir()if p.is_file()}}
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'pass':True,'report_sha256':sha(output/'report.json'),'summary':report['summary']}))

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__)
    for name in('software','hardware','hardware-job','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--expected-hardware-report-sha256',required=True)
    main(p.parse_args())
