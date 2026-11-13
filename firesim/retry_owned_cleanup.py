#!/usr/bin/env python3
"""Retry an owned standard kill only for explicitly proved startup failures."""
import argparse
import json
import os
import uuid
from pathlib import Path
from urllib.parse import unquote,urlparse

from batch_runner import (prepare,digest,save_manifest,inspect_remote,bind_launch_authorization,
    require_safe_remote,checked_remote_lock,run_task,capture_quiescent_run)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--host',default='sohumpc')
    a=p.parse_args();job=a.job.resolve();old=json.loads((job/'run.json').read_text())
    parse_failure=(old['commands'] and all(c['task']=='kill' and c['status']=='failed' and
        'Unable to find TARGET_PROJECT_MAKEFRAG' in (job/c['stdout_path']).read_text() for c in old['commands']))
    tool_failure=([(c['task'],c['status'])for c in old['commands']]==[('kill','passed'),('infrasetup','failed')]
        and any('Could not find Xilinx Hardware Server!' in p.read_text(errors='replace')
                for p in (job/'manager/logs').glob('*infrasetup*.log')))
    quiescence_failure=([(c['task'],c['status'])for c in old['commands']]==[('kill','passed'),('infrasetup','passed')]
        and 'hw_server' in old.get('error','') and not any(c['task']=='runworkload'for c in old['commands']))
    wrapper_report=job/'dead-wrapper-recovery.json'
    wrapper_recovery=json.loads(wrapper_report.read_text()) if wrapper_report.is_file() else {}
    wrapper_failure=([(c['task'],c['status'])for c in old['commands']]==[
        ('kill','passed'),('infrasetup','passed'),('runworkload','interrupted'),('kill','timed_out')]
        and wrapper_recovery.get('schema')=='iris.owned_dead_driver_wrapper_recovery.v1'
        and wrapper_recovery.get('driver_restarted') is False
        and wrapper_recovery.get('lock_released') is False
        and wrapper_recovery.get('standard_kill_retry_required') is True
        and wrapper_recovery.get('action',{}).get('driver_already_zombie') is True
        and wrapper_recovery.get('action',{}).get('hardware_launch') is False)
    if (not old.get('lock_retained_for_operator') or old.get('cleanup_status')!='refused_or_failed'
            or not(parse_failure or tool_failure or quiescence_failure or wrapper_failure)):
        raise RuntimeError('Only explicitly proved startup/owned-wrapper failures are eligible; never recover an uncertain hardware job')
    if not (job/'run.before-parse-repair.json').exists():(job/'run.before-parse-repair.json').write_bytes((job/'run.json').read_bytes())
    out=job/('cleanup-parse-repair-'+uuid.uuid4().hex[:8])
    manager,m=prepare(Path('/scratch/eygao/iris-cy/sims/firesim/deploy'),out,
        job/'manager/workloads/iris-batch/batch.elf',old['cases'],job/'manager/config_runtime.yaml',
        job/'manager/config_hwdb.yaml',Path(unquote(urlparse(old['driver']['uri']).path)),
        observability_report=Path(old['observability_audit']['report']))
    m['launch_authorization_receipt']=old['launch_authorization_receipt']
    m['active_phase']='cleanup';m['execution_runtime_sha256']=digest(manager/'config_runtime.yaml')
    m['status']='owned_cleanup_only'
    identity={k:old['shared_lock'][k]for k in ('uid','user','boot_id','authorization_id','authorization_sha256')}
    token=old['lock_token'];authorization_id=old['authorization_id']
    checked_remote_lock(a.host,token,None,identity)
    remote=bind_launch_authorization(a.host,inspect_remote(a.host),m)
    require_safe_remote(remote,authorization_id,old['remote']['boot_id'],old['remote_simulation_dir'])
    m['remote']=remote;m['safety_inspection']=remote;save_manifest(out,m)
    env=dict(os.environ,IRIS_FIRESIM_SSH_USER=remote['user'])
    import subprocess
    config={line.partition(' ')[0]:line.partition(' ')[2]for line in subprocess.check_output(['ssh','-G',a.host],text=True,stderr=subprocess.DEVNULL).splitlines()}
    env['IRIS_FIRESIM_SSH_KEY']=str(Path(config['identityfile']).expanduser())
    run_task(manager,out,'kill',env,180,m)
    # Recheck ownership/boot and complete visibility before releasing our lock.
    remote=bind_launch_authorization(a.host,inspect_remote(a.host),m)
    require_safe_remote(remote,authorization_id,old['remote']['boot_id'],old['remote_simulation_dir'])
    checked_remote_lock(a.host,token,False,identity)
    m['status']='owned_cleanup_completed';save_manifest(out,m)
    old.update(cleanup_status='passed_after_owned_cleanup_repair',lock_retained_for_operator=False,
        cleanup_repair={'receipt':str(out/'run.json'),'sha256':digest(out/'run.json'),
                        'scope':'Proved startup/owned-wrapper failure; complete current inspection and original owned group lock preserved throughout a fresh standard kill'})
    save_manifest(job,old);capture_quiescent_run(job,old)
    print(json.dumps({'status':old['status'],'cleanup':old['cleanup_status'],'capture':old['capture']['status']}))


if __name__=='__main__':main()
