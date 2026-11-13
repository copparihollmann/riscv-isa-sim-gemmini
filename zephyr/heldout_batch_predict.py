#!/usr/bin/env python3
"""Freeze exact runtime bytes before independent v6 execution; never fit parameters."""
import argparse,datetime,hashlib,json,os,re,shutil,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
V6='987e0b3c4e8c3f45c1549501edee6a7f1e6ba1b73f7289cb4fc877a1460e3ed2'
ELF='da2de5ef01d7030741058859162fb6286fa73baf8816ab1365bdfe3ea6785cd4'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True)
    p.add_argument('--fixture',type=Path,required=True);p.add_argument('--parameters',type=Path,required=True);p.add_argument('--fit-report',type=Path,required=True)
    p.add_argument('--runtime-binding',type=Path,required=True);p.add_argument('--batch',type=Path,default=ROOT/'build/fast-heldout-zephyr-compact-v6')
    p.add_argument('--seed',type=int,default=0);p.add_argument('--timeout',type=int,default=1800);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);saved=out/'inputs';saved.mkdir()
    binary,uart,fixture,parameters,fit_report,binding=[x.resolve()for x in(a.binary,a.uart,a.fixture,a.parameters,a.fit_report,a.runtime_binding)]
    envelope=json.loads(binding.read_text());manifest=a.batch.resolve()/'manifest.json';workload=json.loads(manifest.read_text())
    if sha(manifest)!=V6 or workload['ELF_sha256']!=ELF:raise ValueError('Exact frozen v6 required')
    if envelope.get('schema')!='iris.empirical_runtime_binding.v1' or envelope.get('actual_parameter_fit_performed')is not True or envelope.get('global_heldout_timings_consumed')is not False or not envelope.get('calibration_identity'):
        raise ValueError('Actual fitted independent runtime envelope required')
    selected={'native_binary_sha256':binary,'uart_library_sha256':uart,'fixture_sha256':fixture,'parameters_sha256':parameters,'fit_report_sha256':fit_report}
    for field,path in selected.items():
        if sha(path)!=envelope.get(field):raise ValueError('Runtime envelope selects different '+field)
    split=envelope['split'];train=set(split['training_parent_case_ids']);validation=set(split['validation_parent_case_ids'])
    if not train or not validation or train&validation:raise ValueError('Disjoint frozen parameter partitions required')
    held={x['parent_case_id']for x in workload['phases']}
    if held&(train|validation):raise ValueError('Heldout parents appear in fitting partitions')
    inputs=[Path(__file__),ROOT/'zephyr/heldout_batch_run.py',ROOT/'spike/run_functional.py',
        ROOT/'zephyr/compiler_pipeline.py',ROOT/'zephyr/freeze_heldouts.py',ROOT/'firesim/batch_runner.py',
        ROOT/'zephyr/uart_profiles.py',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',manifest,
        binary,uart,fixture,parameters,fit_report,binding]
    for name,expected in envelope.get('input_sha256',{}).items():
        path=Path(name)
        if not path.is_absolute()or not path.is_file()or sha(path)!=expected:raise ValueError('Runtime envelope source input changed '+name)
        inputs.append(path)
    for image in [binary,uart]:
        dependencies=subprocess.check_output(['ldd',str(image)],text=True)
        if 'not found'in dependencies:raise ValueError('Missing native runtime library')
        inputs.extend(Path(name).resolve()for name in re.findall(r'(?:=>\s*)?(/[^\s()]+)',dependencies)if Path(name).is_file())
    hashes={str(x.resolve()):sha(x)for x in inputs}
    for path,h in hashes.items():
        dest=saved/h
        if not dest.exists():shutil.copyfile(path,dest)
        if sha(dest)!=h:raise ValueError('Frozen runtime snapshot changed')
    def reference_audit():
        hits=[]
        for base in[ROOT/'build',ROOT/'runs']:
            for current,dirs,files in os.walk(base):
                if len(Path(current).relative_to(base).parts)>=3:dirs[:]=[]
                for name in files:
                    path=Path(current)/name
                    if path.suffix!='.json'or path.stat().st_size>20_000_000:continue
                    try:d=json.loads(path.read_text())
                    except(UnicodeError,json.JSONDecodeError):continue
                    if not isinstance(d,dict):continue
                    if d.get('ELF_sha256')==ELF and d.get('timing_kind')=='actual-archived-FireSim-reference':hits.append(str(path))
                    if d.get('schema')=='iris.independent_heldout_Zephyr_batch_archive_analysis.v1'and d.get('functional_checks_passed')is True:hits.append(str(path))
        return hits
    audit=reference_audit()
    if audit:raise ValueError('Actual heldout reference already observed; preserve and enroll a fresh independent workload: '+str(audit))
    cmd=[sys.executable,str(ROOT/'zephyr/heldout_batch_run.py'),'--batch',str(a.batch.resolve()),'--expected-manifest-sha256',V6,
        '--output',str(out/'run'),'--binary',str(binary),'--uart',str(uart),'--seed',str(a.seed),'--timeout',str(a.timeout),
        '--timing-kind','experimental-empirical','--engine-arg=--iris-timing-fixture='+str(fixture),
        '--engine-arg=--iris-timing-trace='+str(out/'native-summary.json')]
    env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(out/'features.jsonl'))
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();start=time.monotonic()
    (out/'before-execution.json').write_text(json.dumps({'started_at_UTC':started,'input_sha256':hashes,'argv':cmd,
        'environment':{'IRIS_EMPIRICAL_FEATURES':env['IRIS_EMPIRICAL_FEATURES']},'prior_reference_receipts':audit,
        'runtime_envelope_verified':True,'hardware_contacted':False},indent=2)+'\n')
    with(out/'validator.stdout').open('wb')as stdout,(out/'validator.stderr').open('wb')as stderr:
        proc=subprocess.Popen(cmd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        try:code=proc.wait(timeout=a.timeout+120)
        except subprocess.TimeoutExpired:
            # Keep the group leader unreaped during the grace period so its
            # PGID cannot be reused. Spike may handle SIGTERM without exiting;
            # always finish the owned group, even if the Python child exited.
            try:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            time.sleep(.2)
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait()
            raise RuntimeError('Owned prediction process group exceeded explicit bound; preserved inputs/logs')
    elapsed=time.monotonic()-start;raw=out/'run/report.json';result=json.loads(raw.read_text())
    if code or result.get('pass')is not True:raise ValueError('Preserved actual prediction run failed; see run/report.json')
    if any(sha(path)!=h for path,h in hashes.items()):raise ValueError('Runtime inputs changed during prediction')
    if reference_audit():raise ValueError('Reference appeared before prediction freeze; preserve this as a nonblind diagnostic')
    for path in [out/'native-summary.json',out/'features.jsonl']:
        if not path.is_file()or path.stat().st_size==0:raise ValueError('Actual engine summary/prefix stream missing or empty')
    result['input_sha256'].update(hashes)
    result.update(started_at_UTC=started,frozen_at_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        raw_validator_receipt=str(raw),raw_validator_receipt_sha256=sha(raw),runtime_binding_sha256=sha(binding),
        runtime_envelope_verified=True,calibration_identity=envelope['calibration_identity'],
        reference_blinding='Coordinator withholds hardware until this freeze; local build/runs JSON audit found no actual v6 reference. Not a claim about inaccessible external observations.',
        wrapper_argv=cmd,wrapper_environment={'IRIS_EMPIRICAL_FEATURES':env['IRIS_EMPIRICAL_FEATURES']},wrapper_host_seconds=elapsed,
        native_summary_sha256=sha(out/'native-summary.json'),feature_prefix_sha256=sha(out/'features.jsonl'),
        global_heldout_timings_used_for_fitting=False,timing_certified=False)
    result['artifact_sha256']={str(x.relative_to(out)):sha(x)for x in out.rglob('*')if x.is_file()}
    (out/'prediction.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':True,'regions':188,'global_elapsed_windows':8,'prediction_sha256':sha(out/'prediction.json'),
        'host_seconds':result['host_seconds'],'calibration_identity':envelope['calibration_identity']}))
if __name__=='__main__':main()
