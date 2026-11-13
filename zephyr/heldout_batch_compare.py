#!/usr/bin/env python3
"""Read-only independent heldout timing comparison; no fit/update capability."""
import argparse,csv,hashlib,json,math,statistics
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def metrics(rows):
    values=sorted(abs(x['signed_error_percent'])for x in rows)
    return {'regions':len(rows),'median_absolute_error_percent':statistics.median(values),
        'p90_absolute_error_percent':values[max(0,math.ceil(.9*len(values))-1)],
        'max_absolute_error_percent':max(values),'within_two_percent':sum(x['within_two_percent']for x in rows)}

def compare_regions(predicted,reference):
    def index(rows):
        result={}
        for r in rows:
            key=(r['case_id'],r['region'],r['hart'])
            if key in result:raise ValueError('Duplicate region')
            if any(type(r.get(k))is not int for k in ('start_cycle','end_cycle','checksum','instret_delta'))or r['end_cycle']<=r['start_cycle']:raise ValueError('Invalid measured counter interval')
            result[key]=r
        return result
    p,r=index(predicted),index(reference)
    if set(p)!=set(r):raise ValueError('Different measured region identities')
    rows=[]
    for key in sorted(p):
        a,b=p[key],r[key]
        if a['checksum']!=b['checksum']or a.get('parent_case_id')!=b.get('parent_case_id'):raise ValueError('Numerical/source identity differs')
        pc=a['end_cycle']-a['start_cycle'];rc=b['end_cycle']-b['start_cycle'];err=100*(pc-rc)/rc
        rows.append({'case_id':key[0],'region':key[1],'hart':key[2],'model_cycles':pc,'reference_cycles':rc,
            'signed_error_percent':err,'within_two_percent':abs(pc-rc)*100<=2*rc,
            'model_instret':a['instret_delta'],'reference_instret':b['instret_delta'],
            'counter_scope':'producer hart mcycle; may stop in WFI, see globalCLINT interval'if key[1]=='pipeline_end_to_end'else'per-hart program-visible mcycle region',
            'trial_id':b.get('trial_id'),'dataset_id':b.get('dataset_id')})
    return rows

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--prediction',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--archive-evidence',type=Path,required=True,help='Coordinator independent archive/managed-lifecycle verification receipt')
    p.add_argument('--frozen-prediction-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prediction=json.loads(a.prediction.read_text());reference=json.loads(a.reference.read_text());evidence=json.loads(a.archive_evidence.read_text())
    if sha(a.prediction)!=a.frozen_prediction_sha256:raise ValueError('Prediction changed since pre-reference freeze')
    if prediction.get('pass')is not True or prediction.get('timing_kind')!='experimental-empirical' or reference.get('pass')is not True:raise ValueError('Actual successful model and reference validation required')
    if prediction['ELF_sha256']!=reference['ELF_sha256']or prediction['workload_manifest_sha256']!=reference['workload_manifest_sha256']:raise ValueError('Identical ELF and heldout workload required')
    if not all(evidence.get(k)is True for k in ('archive_verified','functional_checks_passed','managed_run_passed')):raise ValueError('Independent verified managed archive required')
    if evidence.get('cleanup_status')!='passed'or evidence.get('capture_status')!='captured':raise ValueError('Owned cleanup/archive incomplete')
    phases=evidence.get('lifecycle',[])
    if [x.get('task')for x in phases]!=['kill','infrasetup','runworkload','kill']or any(x.get('status')!='passed'for x in phases):raise ValueError('Managed four-phase lifecycle required')
    if evidence.get('guest_uart',{}).get('sha256')!=reference.get('artifact_sha256',{}).get('stdout'):raise ValueError('Reference is not exact independently archived UART')
    rows=compare_regions(prediction['regions'],reference['regions'])
    if len(rows)!=188:raise ValueError('Complete188region heldout expected')
    globalrows=[];pp=prediction.get('global_elapsed_windows',[]);rr=reference.get('global_elapsed_windows',[])
    if len(pp)!=8 or len(rr)!=8:raise ValueError('Eight independently sampled globalCLINT intervals required')
    for phase,(x,y)in enumerate(zip(pp,rr)):
        if x['phase']!=phase or y['phase']!=phase or x['core_cycles_per_tick']!=1000 or y['core_cycles_per_tick']!=1000:raise ValueError('CLINT identity/source ratio')
        pc=(x['end_mtime']-x['start_mtime'])*1000;rc=(y['end_mtime']-y['start_mtime'])*1000
        if pc<=0 or rc<=1000:raise ValueError('Interval too short for a useful500kHz comparison')
        # Each interval's two independently quantized endpoints contribute
        # strictly less than one tick to its elapsed-time uncertainty.
        low=100*((pc-1000)/(rc+1000)-1);high=100*((pc+1000)/(rc-1000)-1)
        globalrows.append({'phase':phase,'model_quantized_core_cycles':pc,'reference_quantized_core_cycles':rc,
            'signed_error_percent':100*(pc-rc)/rc,'signed_error_interval_percent':[low,high],
            'within_two_percent':max(abs(low),abs(high))<=2,'per_interval_quantization_bound_cycles':1000,
            'scope':'CLINT data-sample interval enclosing producer entry through outputs consumed; excludes boot/threadcreation/printing'})
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    with(out/'regions.csv').open('w',newline='')as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (out/'global-elapsed.json').write_text(json.dumps(globalrows,indent=2)+'\n')
    groups={}
    for r in rows:
        group=r['case_id'].rsplit('.',1)[0]
        groups.setdefault(group,[]).append(r)
    report={'schema':'iris.independent_compatible_heldout_timing_comparison.v1','status':'measured_comparison_not_certification',
        'ELF_sha256':prediction['ELF_sha256'],'workload_manifest_sha256':prediction['workload_manifest_sha256'],
        'model_prediction_sha256':sha(a.prediction),'reference_validation_sha256':sha(a.reference),
        'signed_error_definition':'100*(model-reference)/reference','per_region':rows,'per_group':{k:metrics(v)for k,v in groups.items()},
        'overall':metrics(rows),'global_elapsed_windows':globalrows,'global_elapsed_metrics':metrics(globalrows),
        'model_host_seconds':prediction.get('host_seconds'),'reference_host_seconds_not_target_time':reference.get('host_seconds'),
        'global_heldout_timings_used_for_fitting':False,'timing_certified':False,'whole_batch_end_to_end_certified':False,
        'hardware_contacted_by_comparison':False,'loaded_image_identity_verified':evidence.get('loaded_image_verified',False),
        'source_image_association_verified':evidence.get('source_image_association_verified',False),
        'qualification':'Perregion counters and explicitly bounded perphase globalelapsed only. All188passing2% would still not certify fullSoC/otherworkloads. Errors must notinformparameterupdates withoutretiringthisholdout.',
        'input_sha256':{str(x.resolve()):sha(x)for x in[Path(__file__),a.prediction,a.reference,a.archive_evidence]},
        'artifact_sha256':{x.name:sha(x)for x in out.iterdir()if x.is_file()}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'regions':len(rows),'overall':report['overall'],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
