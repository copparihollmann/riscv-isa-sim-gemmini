#!/usr/bin/env python3
"""Diagnose complete leading phases of a failed heldout run; never certify it."""
import argparse
import hashlib
import json
import math
import sys
import tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'zephyr'))
from analyze_campaign import read_archive,select_guest_uart
from batch_runner import parse_regions
from compiler_pipeline import producer_golden
from freeze_heldouts import output_hash
from heldout_batch_compare import compare_regions,metrics
from uart_profiles import check_report
V6='987e0b3c4e8c3f45c1549501edee6a7f1e6ba1b73f7289cb4fc877a1460e3ed2'
ELF='da2de5ef01d7030741058859162fb6286fa73baf8816ab1365bdfe3ea6785cd4'
FROZEN_PREDICTIONS={
 '28':('build/heldout-v6-prediction-28a0-priority-v2/prediction.json','fa7a7b4aee69bf38f45b06fd4dfb54b06ccf3263c4d2aceaafde66eba1c476a5'),
 '525':('build/heldout-v6-prediction-525-compute-v1/prediction.json','50c4f58fec8b95f8abed3d16b51ae7eebaa8acecb3f59b4a8da59c07f2ab83e6'),
 '7de':('build/heldout-v6-prediction-7de-fadd-shape-v1/prediction.json','bc8aaabac0a5e7b52e3b6fc1c3fa1e8b58ccf4b2debc170a08e3a3e89d832ceb'),
 '9b2':('build/heldout-v6-prediction-9b2-fadd-shape-store-v1/prediction.json','c9b976950d7be2af698a7240b3d79ccba0bba900344ee5b6a5231b0fcfa69b02')}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def records(text,prefix):
    return [json.loads(x[len(prefix):])for x in text.splitlines()if x.startswith(prefix)]
def declared_predictions(specs):
    if len(specs)!=4:raise ValueError('All four recorded prospective predictions required')
    seen=set()
    for name,path,digest in specs:
        if name not in FROZEN_PREDICTIONS or name in seen:raise ValueError('Unknown or duplicate prospective prediction')
        relative,wanted=FROZEN_PREDICTIONS[name]
        if Path(path).resolve()!=(ROOT/relative).resolve()or digest!=wanted:raise ValueError('Prediction differs from recorded prospective identity')
        seen.add(name)
    return specs
def failed_lifecycle(current,run):
    if(any(x.get('status')!='failed'or x.get('cleanup_status')!='passed'or x.get('cleanup_error')is not None for x in(current,run))
       or current.get('error')!=run.get('error')or current.get('lock_release_error')or current.get('lock_retained_for_operator',False)is not False):raise ValueError('Archived/current failed outcome and successful owned cleanup must agree')
    commands=run.get('commands')
    if not isinstance(commands,list)or len(commands)!=4:raise ValueError('Exactly four managed phases required')
    result=[]
    for i,(row,task)in enumerate(zip(commands,('kill','infrasetup','runworkload','kill'))):
        elapsed=row.get('host_elapsed_seconds')
        if(row.get('task')!=task or type(row.get('cleanup_phase'))is not bool or row['cleanup_phase']!=(i==3)
           or type(row.get('returncode'))is not int or type(row.get('timed_out'))is not bool
           or type(elapsed)not in(int,float)or not math.isfinite(elapsed)or elapsed<0
           or row.get('status')not in('passed','failed')):raise ValueError('Malformed owned lifecycle')
        if i in(0,1,3)and(row['status']!='passed'or row['returncode']!=0 or row['timed_out']):raise ValueError('Owned setup/cleanup phase did not pass')
        if row['status']=='passed'and(row['returncode']!=0 or row['timed_out']):raise ValueError('Successful phase has failed process outcome')
        result.append({k:row[k]for k in('task','status','returncode','host_elapsed_seconds','cleanup_phase','timed_out')})
    return result
def archived_identity(run,ids):
    if(run.get('campaign_role')!='independent_heldout_zephyr_Merlin_batch_v6'or run.get('fitting_allowed')is not False
       or run.get('corpus_sha256')!=V6 or run.get('elf_sha256')!=ELF
       or run.get('frozen_prediction_sha256')!=FROZEN_PREDICTIONS['9b2'][1]
       or ids.get('job/prediction.json')!=FROZEN_PREDICTIONS['9b2'][1]
       or ids.get('job/manager/workloads/iris-batch/batch.elf')!=ELF):raise ValueError('Exact independent workload/executed ELF/archived primary prediction identity')
def complete_prefix(text,corpus):
    """The source prints producer evidence last in each completed phase report."""
    lines=text.splitlines(keepends=True)
    if any(x.lstrip().startswith(('IRIS_FATAL','IRIS_HELDOUT_FATAL','IRIS_BATCH_DONE'))for x in lines):raise ValueError('This diagnostic requires incomplete nonfatal output')
    headers=[i for i,l in enumerate(lines)if l.startswith('IRIS_HELDOUT_PHASE ')]
    if not 0<len(headers)<=8:raise ValueError('Nonempty bounded leading phase announcements required')
    completed=0;cut=len(lines)
    for phase,index in enumerate(headers):
        row=json.loads(lines[index][len('IRIS_HELDOUT_PHASE '):]);wanted={k:corpus['phases'][phase][k]for k in('phase','op','workers','kind')}
        if(row!=wanted or any(type(row.get(k))is not int for k in('phase','workers'))):raise ValueError('Missing/reordered/malformed phase announcement')
        end=headers[phase+1]if phase+1<len(headers)else len(lines)
        footer=[x for x in lines[index:end]if x.startswith('IRIS_HELDOUT_PRODUCER ')]
        if len(footer)>1:raise ValueError('Duplicate producer phase footer')
        if not footer:
            if phase+1!=len(headers):raise ValueError('Incomplete earlier phase before later announcement')
            cut=index;break
        # An unterminated/truncated final footer is excluded, never decoded as
        # a complete record. Other complete footer errors must fail validation.
        try:json.loads(footer[0][len('IRIS_HELDOUT_PRODUCER '):])
        except json.JSONDecodeError:
            if phase+1==len(headers)and footer[0]==lines[-1]and not footer[0].endswith('\n'):cut=index;break
            raise ValueError('Malformed complete phase footer')
        completed+=1
    if not 0<completed<8:raise ValueError('Strictly incomplete nonempty complete-phase prefix required')
    return ''.join(lines[:cut]),{'observed_phase_announcements':len(headers),'excluded_incomplete_trailing_phase':completed<len(headers),
        'excluded_suffix_bytes':len(''.join(lines[cut:]).encode()),'complete_prefix_sha256':hashlib.sha256(''.join(lines[:cut]).encode()).hexdigest()}
def validate_prefix(text,corpus,cases,goldens):
    text,selection=complete_prefix(text,corpus)
    phases=records(text,'IRIS_HELDOUT_PHASE ');n=len(phases)
    if not 0<n<8:raise ValueError('Strictly incomplete nonempty phase prefix required')
    wanted=[{k:p[k]for k in('phase','op','workers','kind')}for p in corpus['phases'][:n]]
    if phases!=wanted or any(type(p.get(k))is not int for p in phases for k in ('phase','workers')):raise ValueError('Missing or reordered leading phases')
    # Parent identities alone are shared across shipped/twin. Use exact case stem.
    stems={'heldout.batch.%s.h%d.%s.'%(p['op'],p['workers'],p['kind'])for p in phases}
    selected=[c for c in cases if any(c['id'].startswith(s)for s in stems)]
    rows=parse_regions(text,selected,ELF,None,True,True)
    expected={(c['id'],h):c for c in selected for h in c['active_harts']}
    for r in rows:
        c=expected[r['case_id'],r['hart']]
        if r['cycles']<=0 or r['instret_delta']<=0 or r.get('parent_case_id')!=c['parent_case_id']:raise ValueError('Invalid prefix counters/source identity')
        if r['region']=='pipeline_end_to_end':
            if r.get('scope')!='producer_entry_to_all_outputs_consumed'or r.get('role')!='pipeline.end_to_end'or r['hart']!=2:raise ValueError('Producer scope')
        else:
            workers=2 if '.h2.'in r['case_id']else 1
            if any(type(r.get(k))is not int or r[k]!=c[k]for k in('trial_id','dataset_id'))or type(r.get('hart_mask'))is not int or r['hart_mask']!=(1<<workers)-1 or r.get('role')!=('scalar.compute'if'.twin.'in r['case_id']else'vme.compute'):raise ValueError('Compute placement/trial/role')
    outputs=records(text,'IRIS_HELDOUT_RESULT ')
    if len(outputs)!=n*15:raise ValueError('Every observed phase must have all15 independently checked results')
    for i,r in enumerate(outputs):
        phase,job=divmod(i,15);g=goldens[phase//4][job%3]
        want=dict(phase=phase,job=job,encoding='checked-word-hashes-v1',word_count=4096,accumulator_checksum=output_hash(g['accumulator_u32']),w8a8_checksum=output_hash(g['w8a8_f32_words']),mismatching_int32_words=0,mismatching_w8a8_words=0)
        if r!=want or any(type(r[k])is not int for k in want if k!='encoding'):raise ValueError('Independent INT32/W8A8 output mismatch')
    producers=records(text,'IRIS_HELDOUT_PRODUCER ')
    if len(producers)!=n:raise ValueError('Incomplete producer prefix')
    for p,phase in zip(producers,phases):
        if any(type(p.get(k))is not int or p[k]!=v for k,v in [('phase',phase['phase']),('hart',2),('jobs',15),('vector_checksum',producer_golden(5))])or p.get('vme_refused')is not True:raise ValueError('Producer identity/refusal/checksum')
        masks=p.get('overlap_masks')
        if not isinstance(masks,list)or len(masks)!=15 or any(type(m)is not int or not 0<=m<1<<phase['workers']for m in masks)or not any(masks[:2]):raise ValueError('Producer overlap evidence')
    windows=records(text,'IRIS_HELDOUT_ELAPSED ')
    if len(windows)!=n:raise ValueError('Missing CLINT phase interval')
    for i,w in enumerate(windows):
        if any(type(w.get(k))is not int for k in('phase','hart','start_mtime','end_mtime','timebase_hz','core_cycles_per_tick'))or w['phase']!=i or w['hart']!=2 or not 0<=w['start_mtime']<w['end_mtime']<1<<64 or w['timebase_hz']!=500000 or w['core_cycles_per_tick']!=1000 or w.get('source')!='CLINT.mtime.MMIO'or w.get('scope')!='producer_entry_to_all_outputs_consumed':raise ValueError('CLINT source/scope/interval')
    check_report(text.splitlines(),'ethan-firesim')
    return dict(complete_leading_phases=n,regions=rows,global_elapsed_windows=windows,independently_checked_INT32_words=n*15*4096,independently_checked_W8A8_words=n*15*4096,**selection)
def validate_prediction(pred,corpus,cases):
    if(pred.get('pass')is not True or pred.get('timing_kind')!='experimental-empirical'or pred.get('ELF_sha256')!=ELF or pred.get('workload_manifest_sha256')!=V6 or pred.get('fitting_allowed')is not False):raise ValueError('Wrong frozen model prediction')
    raw=pred.get('regions')
    if not isinstance(raw,list)or len(raw)!=188:raise ValueError('All188 prospective region predictions required')
    rows=parse_regions('\n'.join('IRIS_REGION '+json.dumps(r)for r in raw),cases,ELF,None,True,True)
    windows=pred.get('global_elapsed_windows')
    if not isinstance(windows,list)or len(windows)!=8:raise ValueError('All8 prospective global windows required')
    for i,w in enumerate(windows):
        if(any(type(w.get(k))is not int for k in('phase','hart','start_mtime','end_mtime','timebase_hz','core_cycles_per_tick'))or w['phase']!=i or w['hart']!=2 or not 0<=w['start_mtime']<w['end_mtime']<1<<64 or w['timebase_hz']!=500000 or w['core_cycles_per_tick']!=1000 or w.get('source')!='CLINT.mtime.MMIO'or w.get('scope')!='producer_entry_to_all_outputs_consumed'):raise ValueError('Malformed prospective global window')
    return rows,windows
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--prediction',nargs=3,action='append',metavar=('NAME','PATH','PRELAUNCH_SHA256'),required=True);a=p.parse_args()
    declared_predictions(a.prediction)
    job=a.job.resolve();current_raw=(job/'run.json').read_bytes();current_hash=hashlib.sha256(current_raw).hexdigest();current=json.loads(current_raw);cap=current['capture'];archive=Path(cap['archive'])
    if cap.get('status')!='captured'or sha(archive)!=cap['archive_sha256']or current.get('cleanup_status')!='passed'or current.get('status')!='failed' or current.get('lock_release_error')or current.get('lock_retained_for_operator'):raise ValueError('Failed run with complete owned cleanup and exact quiescent archive required')
    data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);run=json.loads(data['job/run.json'])
    archived_identity(run,ids);lifecycle=failed_lifecycle(current,run)
    with tarfile.open(archive,'r:gz')as t:
        def extract(name,expected=None):
            raw=t.extractfile(name).read()
            if hashlib.sha256(raw).hexdigest()!=ids[name]or expected and ids[name]!=expected:raise ValueError('Archived exact input '+name)
            return raw
        corpus=json.loads(extract('job/corpus.json',V6));cases=json.loads(extract('job/cases.json',corpus['cases_sha256']));goldens=json.loads(extract('job/golden.json',corpus['golden_sha256']))
        extract('job/manager/workloads/iris-batch/batch.elf',ELF)
    member,uart=select_guest_uart(data,ids);proof=validate_prefix(data[member].decode('utf8'),corpus,cases,goldens)
    inputs={str(Path(__file__).resolve()):sha(__file__),str(job/'run.json'):current_hash,str(archive):cap['archive_sha256']}
    for name in ['firesim/analyze_campaign.py','firesim/batch_runner.py','zephyr/compiler_pipeline.py','zephyr/freeze_heldouts.py','zephyr/heldout_batch_compare.py','zephyr/uart_profiles.py']:
        f=ROOT/name;inputs[str(f)]=sha(f)
        if ids.get('job/input-files/'+inputs[str(f)]) is None and inputs[str(f)]not in ids.values():raise ValueError('Diagnostic dependency not present in frozen archive: '+name)
    comparisons={};keys={(r['case_id'],r['region'],r['hart'])for r in proof['regions']}
    for name,path,expected in a.prediction:
        path=Path(path).resolve()
        if name in comparisons or sha(path)!=expected:raise ValueError('Exact unique prelaunch prediction required')
        pred=json.loads(path.read_text());inputs[str(path)]=expected
        predicted_regions,predicted_windows=validate_prediction(pred,corpus,cases)
        rows=compare_regions([r for r in predicted_regions if(r['case_id'],r['region'],r['hart'])in keys],proof['regions']);windows=[]
        for x,y in zip(predicted_windows[:proof['complete_leading_phases']],proof['global_elapsed_windows']):
            pc=(x['end_mtime']-x['start_mtime'])*1000;rc=(y['end_mtime']-y['start_mtime'])*1000
            if x['phase']!=y['phase']or pc<=0 or rc<=1000:raise ValueError('Bad comparable CLINT interval')
            windows.append(dict(phase=x['phase'],model_cycles=pc,reference_cycles=rc,signed_error_percent=100*(pc-rc)/rc,signed_error_interval_percent=[100*((pc-1000)/(rc+1000)-1),100*((pc+1000)/(rc-1000)-1)]))
        comparisons[name]=dict(prediction_sha256=expected,per_region=rows,overall=metrics(rows),global_elapsed_windows=windows)
    if any(sha(path)!=h for path,h in inputs.items()):raise ValueError('Diagnostic input changed')
    out=a.output.resolve()
    if out==job or job in out.parents:raise ValueError('Output must be outside immutable job')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(schema='iris.failed_heldout_complete_prefix_diagnostic.v2',status='incomplete_run_diagnostic_only',full_validation_passed=False,full_run_failed=True,timing_certified=False,fitting_allowed=False,model_selection_performed=False,hardware_contacted=False,source_image_association_verified=False,loaded_image_verified=False,run_error=run.get('error'),archive_verified=True,archive_sha256=cap['archive_sha256'],guest_uart=uart,lifecycle=lifecycle,proof=proof,comparisons=comparisons,input_sha256=inputs,prediction_anchoring={'9b2':'exact archived primary prelaunch prediction','28_525_7de':'root-recorded local prospective byte identities; no independent timestamp authority claimed'},qualification='All complete leading phases only; incomplete suffixes and failed run are not a heldout pass. No whole-run or scaling claim.')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],phases=proof['complete_leading_phases'],regions=len(proof['regions']),comparisons={k:v['overall']for k,v in comparisons.items()})))
if __name__=='__main__':main()
