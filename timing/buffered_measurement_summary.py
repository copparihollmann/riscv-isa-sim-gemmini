#!/usr/bin/env python3
"""Summarize archived FPGA microbenchmark work rates, without latency inference."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source=a.analysis.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    report=json.loads((source/'report.json').read_text())
    if any(report.get(k)is not True for k in ('pass','archive_verified','functional_checks_passed','managed_run_passed')):
        raise ValueError('Independently validated managed FPGA archive required')
    corpus=json.loads((source/'corpus.json').read_text());cases={c['case_id']:c for c in corpus['cases']}
    data=json.loads((source/'regions.json').read_text());groups=collections.defaultdict(list)
    for row in data:
        c=cases[row['case_id']]
        if row['checksum']!=c['expected_checksums'][row['hart']] or row['pass']is not True:
            raise ValueError('Independent golden mismatch')
        groups[c['parent_case_id'],row['hart']].append(row)
    summaries=[];family_counts=collections.Counter()
    for (parent,hart),samples in sorted(groups.items()):
        samples.sort(key=lambda x:x['trial_id'])
        if [s['trial_id'] for s in samples]!=[0,1,2]:raise ValueError('Every parent/hart needs three repetitions')
        c=cases[samples[0]['case_id']];kind=c.get('kind',c.get('kernel','unknown'))
        times=[s['end_cycle']-s['start_cycle'] for s in samples];median=statistics.median(times)
        metadata=c.get('metadata',{})
        macs=metadata.get('macs') if kind in ('vme_int','vme_fp8') else None
        elements=metadata.get('elements') if kind=='vector_int' else metadata.get('floating_operations') if kind=='vector_fp' else None
        readbytes=c.get('kernel_read_bytes_per_hart');writebytes=c.get('kernel_write_bytes_per_hart')
        entry={'parent_case_id':parent,'semantic_parent_case_id':c['semantic_parent_case_id'],'hart':hart,
            'suite':c['suite'],'kind':kind,'mask':c['mask'],'n':c.get('n',c.get('argument')),
            'sew':c.get('sew'),'lmul':c.get('lmul'),'input_formats':metadata.get('input_formats'),
            'target_region':c.get('target_region'),'stride':c.get('stride'),'spread':c.get('spread'),
            'cycle_samples':times,'cycle_median':median,'cycle_min':min(times),'cycle_max':max(times),
            'instruction_samples':[s['instret_delta'] for s in samples],
            'known_algorithmic_MACs_per_hart':macs,'region_MACs_per_guest_cycle':None if macs is None else macs/median,
            'known_vector_elements_per_hart':elements,'region_elements_per_guest_cycle':None if elements is None else elements/median,
            'known_kernel_requested_read_bytes':readbytes,'known_kernel_requested_write_bytes':writebytes,
            'region_requested_bytes_per_guest_cycle':None if readbytes is None or writebytes is None else (readbytes+writebytes)/median,
            'raw_ROI_includes_loop_fence_and_drain_overhead':True,'overhead_subtracted':False,
            'physical_peak_efficiency':None,'physical_per_level_bandwidth':None}
        summaries.append(entry);family_counts[kind]+=len(samples)
    (out/'groups.json').write_text(json.dumps(summaries,indent=2)+'\n')
    columns=['parent_case_id','hart','kind','mask','n','sew','lmul','target_region','stride','spread',
        'cycle_median','cycle_min','cycle_max','known_algorithmic_MACs_per_hart','region_MACs_per_guest_cycle',
        'known_vector_elements_per_hart','region_elements_per_guest_cycle','known_kernel_requested_read_bytes',
        'known_kernel_requested_write_bytes','region_requested_bytes_per_guest_cycle']
    with (out/'rates.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        writer.writerows({key:row[key] for key in columns} for row in summaries)
    inputs={str(source/name):sha(source/name) for name in ('report.json','corpus.json','regions.json','repetitions.json','uartlog')}
    inputs.update({str(Path(__file__).resolve()):sha(Path(__file__).resolve()),
        str(ROOT/'benchmarks/v2/batch.c'):sha(ROOT/'benchmarks/v2/batch.c'),
        str(ROOT/'benchmarks/v2/cases.py'):sha(ROOT/'benchmarks/v2/cases.py'),
        str(ROOT/'benchmarks/memory_routes/guest.c'):sha(ROOT/'benchmarks/memory_routes/guest.c')})
    result={'schema':'iris.buffered_FPGA_measurement_rates.v1','pass':True,'regions':len(data),
        'parent_hart_groups':len(groups),'repetitions':3,'source_archive_sha256':report['archive_sha256'],
        'ELF_sha256':sha(source/'campaign.elf'),'family_region_counts':dict(family_counts),
        'global_heldout_timings_consumed':False,'model_accuracy_claimed':False,'latencies_identified':False,
        'semantics':'Algorithmic work divided by raw median per-hart measured mcycle delta, including loop/fence/drain overhead; no overhead subtraction or aggregate cross-hart wall time.',
        'repetition_semantics':'Evolving cache/predictor/shared-memory histories within one ELF, not an irreducible stochastic noise floor.',
        'feasibility':[
            {'component':'scalar and fetch','evidence':'New buffered scalar streams plus separate2313-region layout batch and source frontend oracle.',
             'limitation':'Cold predictor/cache history is material; warm loop success does not certify cold paths.'},
            {'component':'vector and VME','evidence':'Raw per-hart integer/IEEE vector and integer/all-four-format FP8 VME loop rates.',
             'limitation':'Rates include frontend/drain overhead; hardware unit busy fractions/peaks are not captured.'},
            {'component':'memory and multicore contention','evidence':'TCM0/1, scratchpad and DRAM explicit routes/bank patterns at all seven hart masks.',
             'limitation':'Combined region cost does not uniquely identify cache/NoC/serial-TL/DRAM component latencies or physical per-level traffic.'},
            {'component':'Zephyr scheduling','evidence':'Separate actual3hart numeric/context/IRQ functional gates and frozen v6 model prediction.',
             'limitation':'This new reference is baremetal; final independent Zephyr reference remains unmeasured.'}],
        'accuracy_2percent_certified':False,'source_image_association_verified':False,
        'input_sha256':inputs,'output_sha256':{name:sha(out/name) for name in ('groups.json','rates.csv')}}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':True,'regions':len(data),'groups':len(groups),'report_sha256':sha(out/'report.json')}))


if __name__=='__main__':main()
