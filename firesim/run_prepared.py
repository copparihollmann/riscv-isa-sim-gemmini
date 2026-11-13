#!/usr/bin/env python3
"""Verify an immutable prepared job, optionally execute its existing manager."""
import argparse
import fcntl
import json
import signal
import sys
from pathlib import Path
from urllib.parse import unquote,urlparse

from batch_runner import digest,execute,save_manifest,validate_cases

def verify(output):
    manifest=json.loads((output/'run.json').read_text())
    if manifest.get('status')!='prepared' or manifest.get('commands')!=[]:
        raise ValueError('A fresh prepared job is required; preserve previous attempts')
    if any(p.is_file() for p in (output/'manager/results-workload').rglob('*')):
        raise ValueError('Fresh prepared job contains old results')
    if digest(Path(__file__).with_name('batch_runner.py'))!=manifest['runner_sha256']:
        raise ValueError('Prepared runner source changed; prepare a new job')
    if not manifest.get('prepared_file_sha256'):
        raise ValueError('Prepared file closure missing; prepare a new job')
    for name,expected in manifest['prepared_file_sha256'].items():
        path=(output/name).resolve()
        if output not in path.parents or digest(path)!=expected:
            raise ValueError('Prepared file changed: '+name)
    for name,expected in manifest['input_sha256'].items():
        if digest(name)!=expected:raise ValueError('Prepared source input changed: '+name)
    for key in ('image','driver'):
        artifact=manifest[key];uri=urlparse(artifact['uri'])
        if uri.scheme!='file' or not artifact['sha256'] or digest(unquote(uri.path))!=artifact['sha256']:
            raise ValueError('Verified local '+key+' artifact required')
    validate_cases(manifest['cases'],manifest.get('require_goldens',False))
    return manifest

def main():
    def interrupted(signum,frame):raise KeyboardInterrupt('Interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
    p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path)
    p.add_argument('--execute',action='store_true');p.add_argument('--authorization-id','--allocation-id',dest='allocation_id')
    p.add_argument('--host',default='sohumpc');p.add_argument('--timeout',type=int,default=1800)
    args=p.parse_args();output=args.job.resolve()
    try:
        if args.timeout<=0:raise ValueError('Positive timeout required')
        manifest=verify(output)
        if args.execute:
            manifest['execution_runner_sha256']=digest(Path(__file__))
            with (output.parent/'.iris-firesim-manager.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                execute(output/'manager',output,args.host,args.allocation_id,args.timeout,manifest)
        print(json.dumps({'status':manifest['status'],'local_integrity_verified':True,
                          'hardware_executed':args.execute,'job':str(output)}))
    except (Exception,KeyboardInterrupt) as error:
        print('iris-prepared-job: '+str(error),file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
