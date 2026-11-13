#!/usr/bin/env python3
"""Verify the managed archive and independent v6 Zephyr numerical observations."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
from analyze_campaign import read_archive,select_guest_uart
from batch_runner import digest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'zephyr'))
from heldout_batch_run import validate

V6='987e0b3c4e8c3f45c1549501edee6a7f1e6ba1b73f7289cb4fc877a1460e3ed2'
ELF='da2de5ef01d7030741058859162fb6286fa73baf8816ab1365bdfe3ea6785cd4'

def analyze(job,output):
    if output.exists()or job==output or job in output.parents:raise ValueError('Fresh analysis outside immutable job required')
    output.mkdir(parents=True);current=json.loads((job/'run.json').read_text())
    sources=[Path(__file__).resolve(),ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py',
        ROOT/'zephyr/heldout_batch_run.py',ROOT/'zephyr/heldout_batch_compare.py',ROOT/'zephyr/uart_profiles.py',
        ROOT/'zephyr/compiler_pipeline.py',ROOT/'zephyr/freeze_heldouts.py']
    report={'schema':'iris.independent_heldout_Zephyr_batch_archive_analysis.v1','pass':False,
        'archive_verified':False,'functional_checks_passed':False,'managed_run_passed':False,
        'job':str(job),'current_run_manifest_sha256':digest(job/'run.json'),'cleanup_status':current.get('cleanup_status'),
        'capture_status':current.get('capture',{}).get('status'),'hardware_contacted_by_analysis':False,
        'calibration_usable':False,'timing_accuracy_certified':False,'loaded_image_verified':False,
        'source_image_association_verified':False,'heldout':True,'fitting_allowed':False,
        'analysis_input_sha256':{str(p):digest(p)for p in sources}}
    try:
        capture=current['capture'];archive=Path(capture['archive'])
        if capture.get('status')!='captured'or digest(archive)!=capture['archive_sha256']:raise ValueError('Exact quiescent external archive required')
        data,identities=read_archive(archive,capture['captured_run_manifest_sha256']);manifest=json.loads(data['job/run.json'])
        report.update(archive_verified=True,archive=str(archive),archive_sha256=capture['archive_sha256'])
        if manifest.get('status')!=current['status']or manifest.get('cleanup_status')!=current['cleanup_status']or manifest.get('campaign_role')!='independent_heldout_zephyr_Merlin_batch_v6'or manifest.get('require_goldens')is not True or manifest.get('require_regions')is not True or manifest.get('fitting_allowed')is not False:
            raise ValueError('Archived execution/outcome/independence contract mismatch')
        frozen=manifest['input_sha256'][str(sources[0])]
        if frozen not in identities.values():raise ValueError('Prelaunch analyzer absent from archive')
        report['analysis_identity']={'prelaunch_analyzer_sha256':frozen,'executed_analyzer_sha256':digest(sources[0]),
            'post_run_analyzer_changed':frozen!=digest(sources[0])}
        for path in sources[1:]:
            expected=manifest['runner_sha256']if path.name=='batch_runner.py'else manifest['input_sha256'].get(str(path))
            if expected!=digest(path)or expected not in identities.values():raise ValueError('Archived validator/runner changed '+str(path))
        if identities.get('job/corpus.json')!=V6 or manifest.get('corpus_sha256')!=V6 or manifest.get('elf_sha256')!=ELF:
            raise ValueError('Exact pre-observation frozen v6 workload required')
        report.update(ELF_sha256=ELF,workload_manifest_sha256=V6,image=manifest['image'],driver=manifest['driver'],
            prepared_runtime_sha256=manifest['prepared_runtime_sha256'],prepared_hwdb_sha256=manifest['prepared_hwdb_sha256'],
            runner_sha256=manifest['runner_sha256'])
        corpus=json.loads(data['job/corpus.json'])
        with tarfile.open(archive,'r:gz')as stream:
            def extract(name,wanted=None):
                if name not in identities:raise ValueError('Missing archived artifact '+name)
                raw=stream.extractfile(name).read();h=hashlib.sha256(raw).hexdigest()
                if h!=identities[name]or wanted and h!=wanted:raise ValueError('Archived binding mismatch '+name)
                return raw
            cases_raw=extract('job/cases.json',corpus['cases_sha256']);golden_raw=extract('job/golden.json',corpus['golden_sha256'])
            elf_raw=extract('job/manager/workloads/iris-batch/batch.elf',ELF)
            prediction_raw=extract('job/prediction.json',manifest['frozen_prediction_sha256'])
            binding_raw=extract('job/runtime-binding.json',manifest['runtime_binding_sha256'])
            frozen_prediction=json.loads(prediction_raw)
            summary_raw=extract('job/model-summary.json',frozen_prediction['native_summary_sha256'])
            prefix_raw=extract('job/model-prefix.jsonl',frozen_prediction['feature_prefix_sha256'])
        prediction=json.loads(prediction_raw)
        if prediction.get('pass')is not True or prediction.get('timing_kind')!='experimental-empirical'or prediction.get('ELF_sha256')!=ELF or prediction.get('workload_manifest_sha256')!=V6 or len(prediction.get('regions',[]))!=188 or len(prediction.get('global_elapsed_windows',[]))!=8:
            raise ValueError('Frozen complete empirical prediction disagrees with selected reference')
        if manifest['runtime_binding_sha256']not in prediction.get('input_sha256',{}).values():raise ValueError('Prediction runtime envelope is unbound')
        for name,h in prediction['input_sha256'].items():
            if manifest['input_sha256'].get(name)!=h or h not in identities.values():raise ValueError('Prediction input absent from archive '+name)
        member,report['guest_uart']=select_guest_uart(data,identities);uart_bytes=data[member];uart=uart_bytes.decode('utf8',errors='strict')
        (output/'uartlog').write_bytes(uart_bytes);(output/'observed.elf').write_bytes(elf_raw)
        for name,raw in [('corpus.json',data['job/corpus.json']),('cases.json',cases_raw),('golden.json',golden_raw),('prediction.json',prediction_raw),('runtime-binding.json',binding_raw)]:
            (output/name).write_bytes(raw)
        (output/'model-summary.json').write_bytes(summary_raw);(output/'model-prefix.jsonl').write_bytes(prefix_raw)
        proof=validate(uart,corpus,json.loads(cases_raw),json.loads(golden_raw));report['guest_proof']=proof
        for region in proof['regions']:region['image_sha256']=manifest['image']['sha256']
        report['functional_checks_passed']=True
        report['lifecycle']=[{k:r.get(k)for k in ('task','status','cleanup_phase','host_elapsed_seconds','returncode','timed_out')}for r in manifest['commands']]
        if [(r['task'],r['status'])for r in manifest['commands']]!=[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')]or current['status']!='completed_uncertified'or current['cleanup_status']!='passed'or current.get('error')is not None or current.get('cleanup_error')is not None:
            raise ValueError('Complete successful managed fourphase lifecycle required')
        if digest(archive)!=capture['archive_sha256']:raise ValueError('Archive changed during analysis')
        if any(digest(name)!=h for name,h in report['analysis_input_sha256'].items()):raise ValueError('Analysis source changed')
        reference={'schema':'iris.independent_heldout_batch_validation.v1','pass':True,'errors':[],
            'ELF_sha256':ELF,'workload_manifest_sha256':V6,'timing_kind':'actual-archived-FireSim-reference',
            'image_sha256':manifest['image']['sha256'],'driver_sha256':manifest['driver']['sha256'],
            'fitting_allowed':False,'timing_certified':False,'hardware_contacted_by_analysis':False,
            'archive_sha256':capture['archive_sha256'],'artifact_sha256':{'stdout':hashlib.sha256(uart_bytes).hexdigest()},**proof}
        (output/'reference-validation.json').write_text(json.dumps(reference,indent=2)+'\n')
        report.update(pass_=True,managed_run_passed=True,frozen_prediction_sha256=manifest['frozen_prediction_sha256'],
            runtime_binding_sha256=manifest['runtime_binding_sha256'],reference_validation_sha256=digest(output/'reference-validation.json'))
        report['pass']=True;report.pop('pass_',None)
        report['qualification']='Actual3hartZephyr/Merlin INT32/W8A8 heldout observations from selected image, exactfrozenprediction separate. Timing comparison remains a separate read-only step; source-image/fullmodel certification false.'
    except(OSError,ValueError,KeyError,TypeError,UnicodeError,tarfile.TarError)as e:report['error']=str(e)
    report['artifact_sha256']={p.name:digest(p)for p in output.iterdir()if p.is_file()}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k)for k in ('pass','archive_verified','functional_checks_passed','managed_run_passed','error')}))
    return 0 if report['pass']else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();raise SystemExit(analyze(a.job.resolve(),a.output.resolve()))
