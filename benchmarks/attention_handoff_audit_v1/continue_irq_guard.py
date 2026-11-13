"""One reviewed IRQ-sensitivity diagnostic; no automatic broad continuation."""
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

SOURCE=Path(__file__).resolve().parent
A=Path('/users/copparihollmann/iris-work/out/artifacts/probes/utilization-correction-v1/approved-operator-campaign-20261110-v1')
BASE=A/'attention-recovery-20261111-v1';T=BASE/'managed-tools';K=BASE/'irqguard-campaign-v1'
PACKET=BASE/'irq-guard-v1'
DEADLINE=dt.datetime.fromisoformat('2026-11-12T06:00:00+00:00')
spec=importlib.util.spec_from_file_location('attention_managed_helpers',T/'queue.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
helpers.W=K
sha,load,need,command,event=helpers.sha,helpers.load,helpers.need,helpers.command,helpers.event
spec=importlib.util.spec_from_file_location('attention_archive',T/'archive_integrity.py')
archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)


def main():
    K.mkdir(exist_ok=False)
    owner=dict(pid=os.getpid(),pgid=os.getpgrp(),proc_start=Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()[19],
               source_sha256=sha(__file__),deadline_utc=DEADLINE.isoformat(),coordinator='/root')
    (K/'owner.json').write_text(json.dumps(owner,indent=2)+'\n')
    event('waiting_for_exact_IRQ_guard_native_qualification',hardware_actions=False)
    while True:
        need(helpers.now()<DEADLINE,'Finite qualification wait expired')
        if (K/'STOP').exists():event('stopped_before_hardware',hardware_actions=False);return
        try:native=load(PACKET/'native-run.json')
        except (FileNotFoundError,json.JSONDecodeError):time.sleep(10);continue
        need(native['native_pass']is True,'Exact IRQ-guard candidate failed native checks');break
    gate=load(PACKET/'native-admission/report.json')
    need(gate['pass_']is True and gate['trials']==42 and gate['handoff_records']==47937,'Complete exact native gate required')
    need(sha(PACKET/'native.stdout')==native['stdout_sha256']and sha(PACKET/'native.stderr')==native['stderr_sha256'],'Native evidence changed')
    review=load(BASE/'all-FF-hypothesis-review.json')
    need(review['pass_']is True and review['hardware_diagnostic_all64_bad_channels_predicted_bit_exact']is True,'Explicit hypothesis review required')
    for p,h in review['evidence_sha256'].items():need(sha(p)==h,'Changed hypothesis evidence')
    prior_job=helpers.J/'attention_handoff42-20261111-v1';prior=load(prior_job/'run.json');helpers.cleanup_ok(prior)
    verified,_,_=archive.verify(prior_job,prior['elf_sha256'])
    need(verified['archive_sha256']=='aa7ac3109b6e44215a8fbafadb15c86c588f55c146eaf76d0ddc234887cfc676','Reviewed previous diagnostic archive differs')
    meta=load(PACKET/'build-receipt.json');need(meta['IRQ_policy_changed']is True and meta['team_math_IRQ_guarded']is True,'Expected isolated intervention')
    ready=load(BASE/'attention_handoff42-v4/ready.json');pins=meta['input_sha256'].copy()
    for p in [Path(__file__).resolve(),T/'queue.py',T/'prepare.py',T/'analyze.py',T/'archive_integrity.py',T/'configure_progress.py',
              T/'attention_progress_watchdog.py',SOURCE/'qualify.py',SOURCE/'build_irq_guard.py',SOURCE/'run_native.py',
              PACKET/'build-receipt.json',PACKET/'native-run.json',PACKET/'native.stdout',PACKET/'native.stderr',PACKET/'native-admission/report.json',
              BASE/'all-FF-hypothesis-review.json',BASE/'RVV-pre-registration-failure.json']:
        pins[str(p)]=sha(p)
    # Preserve independently qualified transport/numerical reader dependencies.
    for p,h in ready['inputs'].items():
        if ('target-tools-i8-v2/' in p or p.endswith('/merlin/runtime/out_b64.py')):pins[p]=h
    for p,h in pins.items():need(sha(p)==h,'Frozen candidate source differs: '+p)
    ready.update(inputs=pins,ELF=dict(path=meta['ELF'],sha256=meta['ELF_sha256']),packet=str(PACKET),
                 qualification=dict(path=str(PACKET/'native-admission/report.json'),sha256=sha(PACKET/'native-admission/report.json')),
                 diagnostic_intervention='H0 IRQs masked only inside each merlin_staged_worker call; restored before ACK. No production policy change.',
                 IRQ_policy_changed=True,timing_intrusive=True,performance_ineligible=True)
    ready_dir=BASE/'attention_irqguard42';ready_dir.mkdir(exist_ok=False)
    ready_path=ready_dir/'ready.json';ready_path.write_text(json.dumps(ready,indent=2)+'\n')
    job=helpers.J/'attention_irqguard42-20261111-v1'
    with helpers.LOCK.open('a')as lock:
        while True:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                need(helpers.now()<DEADLINE,'Another cooperating coordinator owns launch lock');time.sleep(15)
        need(not (K/'STOP').exists(),'Stopped before launch')
        need((DEADLINE-helpers.now()).total_seconds()>9540,'Insufficient full setup/inactivity/cleanup/capture reserve')
        instruction=A/'user-launch-instruction-v6-nov13.txt';grant=A/'continuation-user-grant-source-v2.json'
        recorder=helpers.ROOT/'firesim/record_launch_authorization.py'
        need(sha(instruction)=='8442075c8e6db76e4cd70a2790ee86e1b29f6a093aaeb5808d41221a5866abeb','Actual user instruction differs')
        need(sha(grant)=='62de15c8199b772c7e76cc2e58838aeb5ebeeefeb524d2e189ce1068178eb67c','Actual grant differs')
        need(sha(recorder)=='3b3993ab04bd0d42976689e29b20fd839b17ff9498e2f7c562b1fca97b051eee','Recorder differs')
        expiry=min(helpers.now()+dt.timedelta(hours=5,minutes=59),DEADLINE)
        event('fresh_complete_idle_inspection_and_authorization',expires_utc=expiry.isoformat())
        need(command([helpers.FS,'-B',str(recorder),'--instruction',str(instruction),'--output',str(K/'authorization'),'--expires-at-utc',expiry.isoformat()],'authorization',180)==0,'Fresh idle inspection/authorization refused')
        receipt=K/'authorization/receipt.json';current=load(receipt)['authorization'];previous=prior['launch_authorization_receipt']['authorization']
        need(all(current[k]==previous[k]for k in ['uid','user','hostname','boot_id']),'Host account/boot changed')
        need(not job.exists(),'Never overwrite a hardware job')
        need(command([helpers.FS,'-B',str(T/'prepare.py'),'--ready',str(ready_path),'--expected-ready-sha256',sha(ready_path),
                      '--authorization-receipt',str(receipt),'--output',str(job),'--watchdog-seconds','6000'],'prepare',900)==0,'Fresh managed preparation refused')
        run=load(job/'run.json');need(run['status']=='prepared'and not run['commands'],'Fresh job required')
        checklist=job/'capture-checklist.json';capture=load(checklist)
        capture.update(IRQ_policy_changed=True,diagnostic_intervention=ready['diagnostic_intervention'],production_policy_changed=False)
        checklist.write_text(json.dumps(capture,indent=2)+'\n');run['frozen_capture_checklist_sha256']=sha(checklist)
        run.update(IRQ_policy_changed=True,diagnostic_intervention=ready['diagnostic_intervention'],performance_ineligible=True)
        for p in [Path(__file__).resolve(),instruction,grant]:run['input_sha256'][str(p)]=sha(p)
        for p,h in run['input_sha256'].items():
            dest=job/'prepared-inputs'/h
            if not dest.exists():
                data=Path(p).read_bytes();need(hashlib.sha256(data).hexdigest()==h,'Input changed during snapshot');dest.write_bytes(data)
            need(sha(dest)==h,'Input snapshot differs')
        run['prepared_file_sha256']={str(p.relative_to(job)):sha(p)for p in job.rglob('*')if p.is_file()and p.name!='run.json'and not p.is_symlink()and not any(x.is_symlink()for x in p.parents if x!=job)}
        helpers.save_manifest(job,run);helpers.prepared_verify(job)
        launch=K/'launch';launch.mkdir();(launch/'launch_once.py').write_bytes((helpers.OLD/'launch_once.py').read_bytes())
        (launch/'root-review.json').write_text(json.dumps(dict(job=str(job),prepared_manifest_sha256=sha(job/'run.json'),launch_sha256=sha(job/'launch.sh')),indent=2)+'\n')
        event('entering_managed_IRQ_guard_diagnostic',job=str(job),trials=42,performance_ineligible=True)
        rc=command([helpers.FS,'-B',str(launch/'launch_once.py')],'coordinator',None)
        run=load(job/'run.json');need(not run.get('cleanup_error')and not run.get('lock_retained_for_operator'),'Uncertain cleanup: no recovery or subsequent job')
        need(run.get('capture',{}).get('status')=='captured','Capture required after owned cleanup')
        analysis=command([helpers.FS,'-B',str(T/'analyze.py'),'--job',str(job),'--output',str(K/'admission')],'analysis',1200)
        result=load(K/'admission/report.json')
        outcome=dict(job=str(job),launch_returncode=rc,analysis_returncode=analysis,admitted=result['pass_'],
                     report=str(K/'admission/report.json'),report_sha256=sha(K/'admission/report.json'),performance_ineligible=True,
                     no_automatic_broad_continuation=True)
        (K/'outcome.json').write_text(json.dumps(outcome,indent=2)+'\n')
        event('IRQ_guard_diagnostic_complete_after_owned_cleanup_and_capture',**outcome)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        if K.exists():event('refused_or_failed',error=repr(exc),no_automatic_recovery=True)
        raise
