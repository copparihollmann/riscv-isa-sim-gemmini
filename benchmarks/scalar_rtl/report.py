#!/usr/bin/env python3
"""Freeze observed scalar RTL differences without weakening the strict collector."""
import argparse,json,re,shutil
from pathlib import Path
from build import sha,ROOT


def checked_run(directory):
    receipt=directory/'results.json';run=json.loads(receipt.read_text())
    if run['exit_status']!=0 or run['timed_out'] is not False:raise ValueError('unsuccessful reference process')
    for path,digest in run['artifact_sha256'].items():
        if sha(directory/path)!=digest:raise ValueError('changed raw run artifact '+path)
    for path,digest in run['input_sha256'].items():
        if sha(directory/'inputs'/digest)!=digest:raise ValueError('changed archived input '+path)
    lines=(directory/'signature').read_text().splitlines()
    if len(lines)!=56 or any(not re.fullmatch('[0-9a-f]{16}',line) for line in lines):raise ValueError('invalid raw signature')
    words=[int(line,16) for line in lines]
    if words[:8]!=[0x495249535343414c,1,0,1,1,1,0,0]:raise ValueError('incomplete/failed guest')
    rows=[]
    for h in range(3):
        for k in range(2):
            start,end,ibegin,iend,checksum,ops,pad0,pad1=words[8+h*16+k*8:16+h*16+k*8]
            # No counter assertion is removed from collect.py. This report only
            # admits observations and makes discrepancies explicit and unqualified.
            if end<=start or iend<=ibegin or checksum!=(257 if k==0 else 292) or ops!=256 or pad0 or pad1:
                raise ValueError('invalid result/counter observation')
            rows.append({'hart':h,'kernel':'dependent256' if k==0 else 'independent256','cycles':end-start,
                         'instret_delta_observed':iend-ibegin,'architectural_sequential_expectation':257,
                         'counter_contract_matches':iend-ibegin==257})
    elf=Path(run['argv'][-1])
    return run,rows,run['input_sha256'][str(elf)]


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        record=json.loads((out/'report.json').read_text())
        for path,digest in record['artifact_sha256'].items():
            if sha(out/path)!=digest:raise ValueError('changed frozen evidence '+path)
        print(json.dumps({'status':record['status'],'verified':True,'qualified_accuracy':False}));return
    out.mkdir(parents=True,exist_ok=False)
    ref,rr,refelf=checked_run(a.reference.resolve());model,mr,modelelf=checked_run(a.model.resolve())
    if ref['kind']!='rtl' or model['kind']!='spike' or refelf!=modelelf:raise ValueError('same-ELF RTL/model evidence required')
    table=[]
    for r,m in zip(rr,mr):
        if (r['hart'],r['kernel'])!=(m['hart'],m['kernel']):raise ValueError('region mismatch')
        error=(m['cycles']-r['cycles'])*100/r['cycles']
        table.append({'hart':r['hart'],'kernel':r['kernel'],'rtl_cycles':r['cycles'],'model_cycles':m['cycles'],
                      'signed_error_percent':error,'within_2_percent':abs(error)<=2,
                      'rtl_instret_delta':r['instret_delta_observed'],'model_instret_delta':m['instret_delta_observed'],
                      'counter_contract_matches':r['counter_contract_matches'] and m['counter_contract_matches']})
    # Preserve both successful observations and the original strict failed check.
    for tag,directory in [('reference',a.reference.resolve()),('model',a.model.resolve())]:
        shutil.copytree(directory,out/tag)
    extra=[Path(__file__),ROOT/'benchmarks/scalar_rtl/build.py',ROOT/'benchmarks/scalar_rtl/collect.py',
           ROOT/'benchmarks/scalar_rtl/guest.c',ROOT/'benchmarks/scalar_rtl/streams.S',
           ROOT/'build/rtl-reference-hpm-rdtime-final/reference.json',ROOT/'build/pipeline-frozen-646538e0/manifest.json']
    (out/'source').mkdir()
    origins={}
    for path in extra:
        digest=sha(path);(out/'source'/digest).write_bytes(path.read_bytes());origins[str(path)]=digest
    record={'schema':'iris.scalar_rtl_observation.v1','status':'observed_unqualified_counter_phase_discrepancy',
            'same_elf_sha256':refelf,'source_fir_sha256':ref['source_fir_sha256'],'table':table,
            'reference_receipt_status':ref['status'],'reference_strict_error':ref.get('error'),
            'model_receipt_status':model['status'],'source_input_sha256':origins,
            'rtl_process_exit0_and_mailbox_checksums_verified':True,'strict_counter_check_passed':False,
            'qualified_accuracy':False,'held_out_validation':False,'purpose':'new component-identifying fitting observation',
            'timing_calibrated':False,'ethan_image_association_verified':False,'calibration_usable_for_firesim':False,
            'limitations':['Single warmed straight-line256-ALU shape; no fitted parameters or extrapolation.',
                'Shuttle256 versus model257 retired interval remains an unresolved source/read-phase discrepancy; collector failure is preserved.',
                'Model boundary costs and Rocket timing are explicit synthetic fixture inputs.',
                'Reference uses saved standalone IrisConfig FIR and explicit preload CRT; source/build and deployed FireSim association remain unverified.',
                'This is not held-out accuracy qualification or full functional certification.']}
    record['artifact_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()}
    (out/'report.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'status':record['status'],'table':table,'output':str(out)},indent=2))


if __name__=='__main__':main()
