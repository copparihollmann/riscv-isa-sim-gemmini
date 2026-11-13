#!/usr/bin/env python3
"""Record the current user's explicit instruction; no reservation or lifecycle."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

from batch_runner import inspect_remote, ssh_prefix



def requested_expiry(value, now):
    """Honor an explicit user deadline within the existing six-hour horizon."""
    horizon = now + dt.timedelta(hours=6)
    if value is None:
        return horizon
    expiry = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if expiry.utcoffset() is None or not now < expiry <= horizon:
        raise ValueError('Explicit authorization expiry requires a future timezone-aware deadline within six hours')
    return expiry.astimezone(dt.timezone.utc)

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--host',default='sohumpc')
    p.add_argument('--instruction',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expires-at-utc',help='Explicit user-authorized timezone-aware expiry, at most six hours ahead')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    remote=inspect_remote(a.host);(out/'inspection.json').write_text(json.dumps(remote,indent=2)+'\n')
    if (remote.get('inspection_complete')is not True or remote.get('inspection_method')!='fixed-root-helper'
            or remote.get('busy_processes') or remote.get('device_holders')):
        raise RuntimeError('Complete pinned-root inspection must prove idle before recording this launch instruction')
    instruction=a.instruction.read_text();now=dt.datetime.now(dt.timezone.utc)
    identity='user-launch-'+now.strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    authorization={'schema':'iris.user_launch_authorization.v1','authorization_id':identity,
        'authorization_source':'explicit_current_user_launch_instruction','user':remote['user'],'uid':remote['uid'],
        'boot_id':remote['boot_id'],'hostname':remote['hostname'],'issued_at_utc':now.isoformat(),
        'expires_at_utc':requested_expiry(a.expires_at_utc,now).isoformat(),
        'expiry_scope':'Runner receipt freshness horizon; not an operator reservation or grant beyond the user instruction',
        'instruction':instruction,'instruction_sha256':hashlib.sha256(instruction.encode()).hexdigest(),
        'scope':'Managed Iris smoke and subsequent compatible fitting batches; complete idle inspection, held group lock, kill -> infrasetup -> runworkload -> kill',
        'operator_or_Ethan_exclusive_reservation_claimed':False}
    data=(json.dumps(authorization,indent=2)+'\n').encode();(out/'authorization.json').write_bytes(data)
    code=r'''import hashlib,json,os,pwd,stat,sys
from pathlib import Path
data=sys.stdin.buffer.read();record=json.loads(data)
if record['uid']!=os.getuid() or record['user']!=pwd.getpwuid(os.getuid()).pw_name or record['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():raise ValueError('Authorization account/boot changed')
parent=Path.home()/'.iris-model';parent.mkdir(mode=0o700,exist_ok=True)
parent=parent/'authorizations';parent.mkdir(mode=0o700,exist_ok=True)
if parent.resolve()!=parent or parent.stat().st_uid!=os.getuid() or parent.stat().st_mode&0o077:raise ValueError('Untrusted user authorization directory')
p=parent/(record['authorization_id']+'.json')
with p.open('xb')as f:f.write(data)
p.chmod(0o600)
print(json.dumps({'remote_path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'uid':os.getuid()}))'''
    import shlex
    command=ssh_prefix(a.host)+[shlex.join(['/usr/bin/python3','-I','-S','-c',code])]
    result=subprocess.run(command,input=data,capture_output=True,timeout=30)
    (out/'remote.stdout').write_bytes(result.stdout);(out/'remote.stderr').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('User receipt staging failed; preserve both streams')
    row=json.loads(result.stdout)
    if row['sha256']!=hashlib.sha256(data).hexdigest() or row['uid']!=remote['uid']:raise RuntimeError('User receipt staging identity mismatch')
    receipt={'schema':'iris.remote_user_launch_authorization_receipt.v1',**row,'authorization':authorization,
             'hardware_lifecycle_invoked':False,'operator_reservation_created':False}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'receipt':str(out/'receipt.json'),'authorization_id':identity,'remote_path':row['remote_path']}))


if __name__=='__main__':main()
