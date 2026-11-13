#!/usr/bin/env python3
"""Attribute mathematical kernel work to independently validated FPGA regions."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(analysis,output):
    if output.exists()or analysis==output or analysis in output.parents:
        raise ValueError('Fresh report outside analysis required')
    receipt=analysis/'report.json';corpus_path=analysis/'corpus.json';uart_path=analysis/'uartlog'
    proof=json.loads(receipt.read_text());corpus=json.loads(corpus_path.read_text())
    if proof.get('schema')!='iris.compiler_i8_wrap_archive_analysis.v1'or proof.get('pass')is not True:
        raise ValueError('Actual successful archive analysis required')
    for path in (corpus_path,uart_path):
        if digest(path)!=proof['artifact_sha256'][path.name]:
            raise ValueError('Validated numerical input changed')
    cases={c['case_id']:c for c in corpus['cases']}
    rows=[]
    for line in uart_path.read_text().splitlines():
        if not line.startswith('IRIS_REGION '):continue
        row=json.loads(line.split(' ',1)[1]);base=row['parent_case_id'].split('.variant-',1)[0]
        case=cases[base];ticks=row['end_cycle']-row['start_cycle']
        compute=row['hart']in(0,1)
        macs=case['m']*case['n']*case['k']if compute else None
        rows.append({'case_id':row['case_id'],'hart':row['hart'],'variant':row['variant'],'trial_id':row['trial_id'],
            'observed_region_mcycles':ticks,'observed_region_minstret':row['instret_delta'],
            'retired_instructions_per_region_mcycle':row['instret_delta']/ticks,
            'mathematical_i8_macs':macs,'mathematical_macs_per_region_mcycle':macs/ticks if compute else None,
            'producer_output_elements':None if compute else 4,
            'producer_output_elements_per_region_mcycle':None if compute else 4/ticks,
            'physical_unit_busy_fraction':None,'physical_memory_bytes':None,'roofline':None})
    if len(rows)!=126:raise ValueError('Complete validated corpus required')
    paths=[Path(__file__).resolve(),receipt,corpus_path,uart_path]
    inputs={str(p.resolve()):digest(p)for p in paths}
    output.mkdir(parents=True);snap=output/'inputs';snap.mkdir()
    for path in paths:
        (snap/digest(path)).write_bytes(path.read_bytes())
    report={'schema':'iris.compiler_i8_wrap_logical_work.v1','actual_archive_sha256':proof['archive_sha256'],
        'input_sha256':inputs,'rows':rows,'formula':'For each compute invocation, mathematical int8 MACs = M*N*K from the independently bound corpus.',
        'counter_policy':'Use raw archived per-region mcycle/minstret without overhead subtraction. These are measured kernel throughput ratios, not calibrated simulator predictions.',
        'scope':'Logical application work including clamped/tail shapes; neither physical issued MACs nor retired vector elements. Region includes the kernel and its explicit completion fence.',
        'unknown':['Physical CPU/vector/VME occupancy and pipeline stall attribution','Per-level memory bytes and contention waits','Sustained hardware peaks and a sourced physical roofline'],
        'coverage_policy':'Inherit exact numerical/write-coverage qualifications of the selected archive; a mathematical work formula does not strengthen them.',
        'hardware_contacted':False,'timing_calibrated':False,'whole_model_certified':False}
    if any(digest(path)!=expected for path,expected in inputs.items()):raise ValueError('Input changed during reporting')
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'regions':len(rows),'calibrated':False,'physical_utilization_inferred':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.analysis.resolve(),a.output.resolve())
