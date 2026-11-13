#!/usr/bin/env python3
"""Run one bundled bare-metal/Zephyr ELF through the pinned FireSim manager.

No command uses a shell. Preparation is local; --execute requires a current
allocation and successful remote inspection. Target cycles come from the ELF.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
import tarfile


INSPECTOR_PATH = Path(__file__).resolve().parent / 'operator/firesim-iris-inspect'
INSPECTOR_INSTALL_PATH = '/usr/local/bin/firesim-iris-inspect'
INSPECTOR_VERSION = 'iris-fpga-inspection-v1'
WORKSPACE = Path(__file__).resolve().parents[1]
CAPTURE_SOURCE = Path(__file__).resolve().with_name('capture_run.py')
# Historical default only: a different reviewed candidate supplies its own audit.
# Every prepared job freezes that exact report digest and archive identities.
OBSERVABILITY_REPORT = WORKSPACE / 'build/firesim-observability-candidate-v2/report.json'


class EvidenceCaptureError(RuntimeError):
    """Evidence failed after a completed guest; retain the guest's outcome."""


def remote_inspection_program():
    # Uploaded code executes ONLY as the SSH user. The sole elevated command
    # has a fixed protected path, no arguments and /dev/null input.
    source = INSPECTOR_PATH.read_text()
    expected = hashlib.sha256(source.encode()).hexdigest()
    prefix = ('import json,os,subprocess\nfrom pathlib import Path\n'
              'namespace={"__name__":"iris_inspector_library"}\n'
              'exec(compile(' + repr(source) + ',"<readonly-unprivileged-inspector>","exec"),namespace)\n'
              'EXPECTED_SHA=' + repr(expected) + '\n'
              'HELPER=' + repr(INSPECTOR_INSTALL_PATH) + '\n'
              'VERSION=' + repr(INSPECTOR_VERSION) + '\n')
    return prefix + REMOTE_INSPECTION


REMOTE_INSPECTION = r'''base=namespace['collect']()
try:
 base['sessions']=subprocess.check_output(['/usr/bin/who'],text=True,stderr=subprocess.PIPE).splitlines()
except (OSError,subprocess.CalledProcessError) as exc:
 base['session_query_error']=str(exc)
probe={'path':HELPER,'expected_sha256':EXPECTED_SHA,'expected_version':VERSION,'attempted':False}
report=base
try:
 try:
  Path(HELPER).lstat()
 except FileNotFoundError:
  probe['state']='absent'
  report['inspection_method']='complete-unprivileged' if base['inspection_complete'] else 'incomplete-unprivileged'
 else:
  metadata=namespace['protected_regular'](HELPER)
  if metadata['sha256']!=EXPECTED_SHA:raise ValueError('unknown helper source digest')
  probe.update(state='trusted-helper',metadata=metadata,attempted=True)
  result=subprocess.run(['/usr/bin/sudo','-n','--',HELPER],stdin=subprocess.DEVNULL,text=True,capture_output=True,timeout=25)
  probe.update(exit_status=result.returncode,stderr=result.stderr,stdout_sha256=namespace['sha'](result.stdout.encode()))
  if result.returncode:raise ValueError('fixed inspection helper privilege/execution failed')
  elevated=json.loads(result.stdout)
  helper=elevated.get('privileged_helper',{})
  if (elevated.get('schema')!=VERSION or elevated.get('uid')!=base['uid'] or elevated.get('user')!=base['user'] or
      elevated.get('boot_id')!=base.get('boot_id') or elevated.get('inspection_uid')!=0 or elevated.get('inspection_euid')!=0 or
      helper.get('path')!=HELPER or helper.get('version')!=VERSION or helper.get('sha256')!=EXPECTED_SHA or
      helper.get('uid')!=0 or helper.get('mode')!=metadata['mode'] or helper.get('bytes')!=metadata['bytes'] or
      helper.get('isolated') is not True or helper.get('no_site') is not True or helper.get('stdin')!='devnull'):
   raise ValueError('privileged inspection caller/source/isolation identity mismatch')
  report=elevated
  report['sessions']=base['sessions']
  if 'session_query_error' in base:report['session_query_error']=base['session_query_error']
  report['inspection_method']='fixed-root-helper'
  report['unprivileged_inspection']={'inspection_complete':base['inspection_complete'],'inspection_errors':base['inspection_errors']}
except (OSError,ValueError,TypeError,subprocess.TimeoutExpired) as exc:
 report=base
 report['inspection_complete']=False
 report['inspection_errors'].append({'stage':'privileged_helper','error':str(exc)})
 report['inspection_method']='refused-helper'
 probe.update(state='refused',error=str(exc))
report['privilege_probe']=probe
print(json.dumps(report,sort_keys=True))'''


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ssh_prefix(host):
    if host.startswith('-') or not host or any(c.isspace() for c in host):
        raise ValueError('Invalid SSH host')
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=12', host]


def inspect_remote(host):
    result = subprocess.run(ssh_prefix(host) + ['python3', '-'],
                            input=remote_inspection_program(), text=True,
                            capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('SSH inspection failed: ' + result.stderr.strip())
    return json.loads(result.stdout)


def require_safe_remote(remote, allocation_id, boot_id=None, owned_dir=None):
    if remote.get('inspection_complete') is not True:
        raise RuntimeError('Incomplete all-user process/device inspection; hardware actions refused')
    if (not remote.get('fpga_db_present') or not set(remote.get('fpga_bdfs',[])) & set(remote.get('pci_inventory',[]))):
        raise RuntimeError('Remote FPGA lacks its database/PCIe presence')
    if boot_id is not None and remote.get('boot_id') != boot_id:
        raise RuntimeError('Host rebooted during allocation; hardware actions refused')
    if remote.get('inspection_method') != 'fixed-root-helper':
        raise RuntimeError('Pinned root inspector must pass before hardware actions')
    allocation = remote.get('launch_authorization', {})
    try:
        expiry = dt.datetime.fromisoformat(allocation['expires_at_utc'])
        valid_expiry = expiry.utcoffset() is not None and expiry > dt.datetime.now(dt.timezone.utc)
    except (KeyError, TypeError, ValueError):
        valid_expiry = False
    if (not remote.get('launch_authorization_verified') or not valid_expiry or
            allocation.get('authorization_id') != allocation_id or
            allocation.get('user') != remote.get('user') or
            allocation.get('uid') != remote.get('uid') or
            allocation.get('boot_id') != remote.get('boot_id') or
            allocation.get('authorization_source') != 'explicit_current_user_launch_instruction'):
        raise RuntimeError('Current user launch authorization/account/boot allocation binding is unverified')
    for item in remote.get('busy_processes', []) + remote.get('device_holders', []):
        cwd = item.get('cwd') if isinstance(item, dict) else None
        owned = (owned_dir is not None and isinstance(item, dict) and
                 item.get('uid') == remote.get('uid') and cwd is not None and
                 (cwd == owned_dir or cwd.startswith(owned_dir + '/')))
        if not owned:
            raise RuntimeError('FPGA occupied or ownership uncertain; refusing hardware action: ' + repr(item))


def bind_launch_authorization(host, remote, manifest):
    specification = manifest.get('launch_authorization_receipt', {})
    path, expected = specification.get('remote_path'), specification.get('sha256')
    if (not isinstance(path,str) or not re.fullmatch(r'/home/[a-z_][a-z0-9_-]*/\.iris-model/authorizations/[a-zA-Z0-9_-]+\.json',path)
            or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)):
        raise RuntimeError('Frozen user launch authorization receipt required')
    code = r'''import hashlib,json,os,stat
from pathlib import Path
p=Path(PATH);before=p.lstat()
if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_mode&0o077:raise ValueError('Untrusted user authorization receipt')
if p.resolve()!=p:raise ValueError('Authorization path contains symlinks')
with os.fdopen(os.open(p,os.O_RDONLY|os.O_NOFOLLOW),'rb') as f:
 data=f.read(32769);after=os.fstat(f.fileno())
if len(data)>32768 or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('Authorization receipt changed')
print(json.dumps({'receipt':json.loads(data),'sha256':hashlib.sha256(data).hexdigest(),'uid':os.getuid()}))'''
    result = subprocess.run(ssh_prefix(host)+['/usr/bin/python3','-I','-S','-'],
        input='PATH='+repr(path)+'\n'+code,text=True,capture_output=True,timeout=25)
    if result.returncode:raise RuntimeError('User authorization receipt read failed: '+result.stderr.strip())
    record=json.loads(result.stdout)
    if record.get('sha256')!=expected or record.get('uid')!=remote.get('uid'):
        raise RuntimeError('User authorization receipt digest/account mismatch')
    remote['launch_authorization']=record['receipt'];remote['launch_authorization_verified']=True
    return remote


def await_setup_quiescence(host, remote, manifest, output, lock_identity):
    """Wait for Vivado's idle-timeout daemon; never act while it is busy."""
    deadline=time.monotonic()+45
    expected='/tools/xilinx/2026.1/Vivado_Lab/bin/unwrapped/lnx64.o/hw_server -d -I20 -s TCP:127.0.0.1:3121'
    while (remote.get('inspection_complete')is True and not remote.get('device_holders')
            and remote.get('boot_id')==lock_identity['boot_id'] and remote.get('busy_processes')
            and all(isinstance(p,dict) and p.get('comm')=='hw_server' and p.get('uid')==0
                and p.get('cwd')=='/home/'+remote['user'] and p.get('command')==expected
                and type(p.get('start_time_ticks'))is int for p in remote['busy_processes'])):
        if time.monotonic()>=deadline:break
        manifest.setdefault('setup_quiescence_wait',[]).append(remote);save_manifest(output,manifest)
        time.sleep(2)
        checked_remote_lock(host,manifest['lock_token'],None,lock_identity)
        remote=bind_launch_authorization(host,inspect_remote(host),manifest)
    return remote


def checked_remote_lock(host, token, acquire, identity=None):
    # Token is an internal UUID, never caller-provided shell text. Python comes
    # over stdin, so SSH's remote-shell argument parsing cannot alter its code.
    if not re.fullmatch('[0-9a-f]{32}',token) or not isinstance(identity,dict):
        raise ValueError('Internal lock token and account/boot authorization identity required')
    code = ("import os,json,stat,grp,pwd\nfrom pathlib import Path\n"
            "parent=Path('/scratch/firesim/iris-locks')\ns=parent.lstat()\n"
            "if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_gid!=grp.getgrnam('firesim').gr_gid or stat.S_IMODE(s.st_mode)!=0o2770 or parent.resolve()!=parent:raise ValueError('Untrusted shared group lock directory')\n"
            "expected="+repr(dict(identity,token=token))+"\n"
            "if expected['uid']!=os.getuid() or expected['user']!=pwd.getpwuid(os.getuid()).pw_name or expected['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip():raise ValueError('Lock account/boot changed')\n"
            "p=parent/'fpga0'\n")
    if acquire:
        code += "p.mkdir(mode=0o750)\nwith (p/'owner.json').open('x') as f:json.dump(expected,f,sort_keys=True)\n(p/'owner.json').chmod(0o640)\n"
    else:
        code += ("s=p.lstat();f=(p/'owner.json').lstat()\n"
                 "if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.getuid() or s.st_mode&0o022 or not stat.S_ISREG(f.st_mode) or f.st_uid!=os.getuid() or f.st_mode&0o022:raise ValueError('Lock ownership/type changed')\n"
                 "if json.loads((p/'owner.json').read_text())!=expected:raise ValueError('Lock token/account/boot/authorization changed')\n")
        if acquire is False:code += "(p/'owner.json').unlink()\np.rmdir()\n"
    subprocess.run(ssh_prefix(host) + ['python3', '-'], input=code,
                   text=True, check=True, timeout=25, capture_output=True)


def verify_remote_staging(host, owned_dir, manifest, output=None):
    if not re.fullmatch(r'/scratch/[a-z_][a-z0-9_-]*/firesim/[0-9a-f]{32}', owned_dir):
        raise ValueError('Invalid internally-owned staging directory')
    expected = {'firesim.tar.gz': manifest['image']['sha256'],
                'driver-bundle.tar.gz': manifest['driver']['sha256'],
                'iris-batch0-batch.elf': manifest['elf_sha256']}
    code = r'''import hashlib,json,os,stat
from pathlib import Path
base=Path(BASE)/'sim_slot_0'
private=Path(BASE);info=private.lstat()
if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('untrusted private staging directory')
info=base.lstat()
if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid():raise ValueError('untrusted simulation slot')
rows={}
for name in NAMES:
 path=base/name
 if not stat.S_ISREG(path.lstat().st_mode):raise ValueError('staged path is not a regular file')
 fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  before=os.fstat(stream.fileno())
  if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid():raise ValueError('untrusted staged regular file')
  digest=hashlib.sha256()
  for data in iter(lambda:stream.read(1024*1024),b''):digest.update(data)
  after=os.fstat(stream.fileno())
  current=path.lstat()
  signature=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
  if signature(before)!=signature(after) or signature(before)!=signature(current):raise ValueError('staged file changed while hashing')
  rows[name]={'sha256':digest.hexdigest(),'bytes':after.st_size}
print(json.dumps({'uid':os.getuid(),'base':str(base),'files':rows}))'''
    code = 'BASE=' + repr(owned_dir) + '\nNAMES=' + repr(sorted(expected)) + '\n' + code
    started = time.monotonic()
    record = {'scope': 'post-infrasetup staged archives/ELF; does not attest the programmed image',
              'status': 'attempting', 'expected': expected,
              'probe_source_sha256': hashlib.sha256(code.encode()).hexdigest()}
    manifest.setdefault('transport_audits', []).append(record)
    if output is not None:
        save_manifest(output, manifest)
    stdout, stderr = b'', b''
    try:
        result = subprocess.run(ssh_prefix(host) + ['/usr/bin/python3', '-I', '-S', '-'],
                                input=code.encode(), capture_output=True, timeout=120)
        stdout, stderr = result.stdout, result.stderr
        record['returncode'] = result.returncode
        if result.returncode:
            raise RuntimeError('Read-only staging audit failed: ' + stderr.decode(errors='replace').strip())
        report = json.loads(stdout)
        record['report'] = report
        if (report.get('uid') != manifest['remote']['uid'] or
                report.get('base') != owned_dir + '/sim_slot_0' or
                set(report.get('files', {})) != set(expected) or
                any(report['files'][name].get('sha256') != value for name, value in expected.items())):
            raise RuntimeError('Staged image/driver/ELF digests do not match prepared inputs')
        record['status'] = 'verified'
    except BaseException as error:
        if isinstance(error, subprocess.TimeoutExpired):
            stdout, stderr = error.stdout or b'', error.stderr or b''
            record['timed_out'] = True
        record.update(status='failed', error=str(error))
        raise
    finally:
        record.update(host_elapsed_seconds=time.monotonic() - started,
                      stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                      stderr_sha256=hashlib.sha256(stderr).hexdigest())
        if output is not None:
            prefix = 'staging-' + str(len(manifest['transport_audits']))
            for suffix, data in [('stdout', stdout), ('stderr', stderr)]:
                target = output / (prefix + '.' + suffix)
                with target.open('xb') as stream:
                    stream.write(data)
                record[suffix + '_path'] = target.name
            save_manifest(output, manifest)
    return record


def create_remote_private_directory(host, owned_dir):
    if not re.fullmatch(r'/scratch/[a-z_][a-z0-9_-]*/firesim/[0-9a-f]{32}', owned_dir):
        raise ValueError('Invalid internally-owned directory')
    code = ('import json,os,stat\nfrom pathlib import Path\np=Path(' + repr(owned_dir) + ')\n'
            'p.parent.mkdir(parents=True,exist_ok=True)\n'
            'if p.parent.resolve()!=p.parent:raise ValueError("private parent path contains symlinks")\n'
            'p.mkdir(mode=0o700)\nst=p.lstat()\n'
            'if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode&0o077:raise ValueError("private directory ownership/mode mismatch")\n'
            'print(json.dumps({"path":str(p),"uid":os.getuid(),"mode":stat.S_IMODE(st.st_mode)}))\n')
    result = subprocess.run(ssh_prefix(host) + ['/usr/bin/python3', '-I', '-S', '-'],
                            input=code, text=True, capture_output=True, timeout=25)
    if result.returncode:
        raise RuntimeError('Private run directory creation refused: ' + result.stderr.strip())
    report = json.loads(result.stdout)
    if report.get('path') != owned_dir or report.get('mode') != 0o700:
        raise RuntimeError('Private run directory receipt mismatch')
    return report


def capture_quiescent_run(output, manifest):
    archive = output.with_name(output.name + '.capture.tar.gz')
    stdout = archive.with_name(archive.name + '.stdout')
    stderr = archive.with_name(archive.name + '.stderr')
    command = [sys.executable, str(CAPTURE_SOURCE), str(output), '--output', str(archive),
               '--workspace', str(WORKSPACE)]
    record = {'status': 'attempting', 'argv': command, 'archive': str(archive),
              'stdout_path': str(stdout), 'stderr_path': str(stderr),
              'utility_sha256': digest(CAPTURE_SOURCE),
              'archive_contains_pre_capture_result_manifest': True}
    manifest['capture'] = record
    save_manifest(output, manifest)
    record['captured_run_manifest_sha256'] = digest(output / 'run.json')
    started = time.monotonic()
    try:
        with stdout.open('xb') as out, stderr.open('xb') as err:
            result = subprocess.run(command, stdout=out, stderr=err, timeout=300)
        record.update(returncode=result.returncode, host_elapsed_seconds=time.monotonic() - started,
                      stdout_sha256=digest(stdout), stderr_sha256=digest(stderr))
        if result.returncode or not archive.is_file():
            raise EvidenceCaptureError('Capture utility failed; preserve its partial archive and raw errors')
        record.update(status='captured', archive_sha256=digest(archive))
    except (OSError, subprocess.TimeoutExpired, EvidenceCaptureError) as error:
        record.update(status='failed', error=str(error),
                      partial_archive=str(archive) + '.partial',
                      partial_archive_present=Path(str(archive) + '.partial').exists())
    save_manifest(output, manifest)
    return record['status'] == 'captured'


def collect_optional_observability(host, owned_dir, output, expected_uid):
    """Copy optional ordinary files after owned cleanup; never open devices."""
    if not re.fullmatch(r'/scratch/[a-z_][a-z0-9_-]*/firesim/[0-9a-f]{32}', owned_dir):
        raise ValueError('Invalid owned observability directory')
    destination = output / 'optional-observability'
    destination.mkdir(exist_ok=False)
    names = ('memory_stats0.csv', 'latency_histogram.csv', 'heartbeat.csv', 'sim-run.sh', 'uartlog')
    code = r'''import hashlib,io,json,os,stat,sys,tarfile
from pathlib import Path
base=Path(BASE)/'sim_slot_0'
private=Path(BASE);directory=private.lstat()
if not stat.S_ISDIR(directory.st_mode) or directory.st_uid!=os.getuid() or directory.st_mode&0o077:raise ValueError('untrusted owned evidence directory')
directory=base.lstat()
if not stat.S_ISDIR(directory.st_mode) or directory.st_uid!=os.getuid():raise ValueError('untrusted evidence slot')
rows=[]
class Reader:
 def __init__(self,stream):self.stream=stream;self.digest=hashlib.sha256()
 def read(self,count=-1):
  data=self.stream.read(count);self.digest.update(data);return data
def sig(info):return(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for name in NAMES:
  path=base/name
  try:
   if not stat.S_ISREG(path.lstat().st_mode):raise ValueError('optional path is not a regular file')
   fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
  except FileNotFoundError:rows.append({'name':name,'status':'missing'});continue
  with os.fdopen(fd,'rb') as stream:
   before=os.fstat(stream.fileno())
   if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid():raise ValueError('untrusted optional regular file')
   info=tarfile.TarInfo(name);info.size=before.st_size;reader=Reader(stream);archive.addfile(info,reader)
   if sig(before)!=sig(os.fstat(stream.fileno())) or sig(before)!=sig(path.lstat()):raise ValueError('optional evidence still changing')
   rows.append({'name':name,'status':'empty'if not before.st_size else'captured','sha256':reader.digest.hexdigest(),'bytes':before.st_size})
 data=json.dumps({'files':rows,'uid':os.getuid(),'base':str(base)}).encode();info=tarfile.TarInfo('optional-manifest.json');info.size=len(data);archive.addfile(info,io.BytesIO(data))'''
    code = 'BASE=' + repr(owned_dir) + '\nNAMES=' + repr(names) + '\n' + code
    raw, errors = destination/'transport.tar', destination/'transport.stderr'
    record = {'optional': True, 'status': 'attempting', 'source': owned_dir + '/sim_slot_0',
              'known_names': list(names), 'probe_source_sha256': hashlib.sha256(code.encode()).hexdigest()}
    started = time.monotonic()
    try:
        with raw.open('xb') as stream, errors.open('xb') as stderr:
            result = subprocess.run(ssh_prefix(host) + ['/usr/bin/python3', '-I', '-S', '-'],
                                    input=code.encode(), stdout=stream, stderr=stderr, timeout=180)
        record.update(returncode=result.returncode, host_elapsed_seconds=time.monotonic()-started,
                      raw_transport_sha256=digest(raw), stderr_sha256=digest(errors))
        if result.returncode:
            raise ValueError('Optional observability copyback failed; preserve raw transport/errors')
        with tarfile.open(raw, 'r:') as archive:
            members = archive.getmembers()
            if any(not member.isfile() or member.name not in (*names, 'optional-manifest.json') for member in members):
                raise ValueError('Unexpected observability transport entry')
            if len({member.name for member in members}) != len(members):
                raise ValueError('Duplicate observability transport entry')
            metadata = json.loads(archive.extractfile('optional-manifest.json').read())
            if (metadata.get('uid') != expected_uid or metadata.get('base') != owned_dir + '/sim_slot_0' or
                    [row.get('name') for row in metadata.get('files', [])] != list(names)):
                raise ValueError('Optional evidence inventory mismatch')
            expected_members = {'optional-manifest.json'} | {
                row['name'] for row in metadata['files'] if row['status'] != 'missing'}
            if {member.name for member in members} != expected_members:
                raise ValueError('Optional evidence members disagree with inventory')
            for row in metadata['files']:
                if row['status'] == 'missing':
                    continue
                if row['status'] not in ('captured', 'empty'):
                    raise ValueError('Unknown optional evidence state')
                path = destination/row['name']
                with archive.extractfile(row['name']) as source, path.open('xb') as target:
                    shutil.copyfileobj(source, target)
                if digest(path) != row['sha256'] or path.stat().st_size != row['bytes']:
                    raise ValueError('Optional evidence digest mismatch')
        record.update(status='collected', files=metadata['files'])
    except (OSError, ValueError, TypeError, AttributeError, KeyError, tarfile.TarError, subprocess.TimeoutExpired) as error:
        record.update(status='unavailable', error=str(error))
    return record


def validate_cases(cases, require_goldens=False):
    if not isinstance(cases, list) or not cases:
        raise ValueError('Case manifest must be a nonempty JSON array')
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or not case['id']:
            raise ValueError('Every case requires a nonempty id')
        if case['id'] in ids:
            raise ValueError('Duplicate case id')
        ids.add(case['id'])
        if not case.get('active_harts') or any(type(h) is not int or h < 0 for h in case['active_harts']):
            raise ValueError('Each case requires nonnegative active_harts')
        if len(set(case['active_harts'])) != len(case['active_harts']):
            raise ValueError('Duplicate active hart')
        expected=case.get('expected_checksums_by_hart')
        if expected is not None:
            if (not isinstance(expected,list) or max(case['active_harts'])>=len(expected) or
                any(type(v) is not int or not 0<=v<2**64 for v in expected)):
                raise ValueError('Invalid independent per-hart checksums')
        elif require_goldens:
            raise ValueError('Independent host checksums required for every case')
    return cases


def prepare(deploy, output, elf, cases, runtime_path, hwdb_path, driver_tar=None,
            observability_report=None, profile_interval=1000000):
    # PyYAML is available in the Chipyard environment and on the audited host.
    import yaml
    output.mkdir(parents=True, exist_ok=False)
    manager = output / 'manager'
    manager.mkdir()
    if (deploy.parent / 'platforms').exists():
        (output / 'platforms').symlink_to(deploy.parent / 'platforms', target_is_directory=True)
    for entry in deploy.iterdir():
        if entry.name in {'firesim', 'logs', 'results-workload', 'generated-topology-diagrams', 'workloads'} or entry.name.startswith('config_'):
            continue
        (manager / entry.name).symlink_to(entry.resolve(), target_is_directory=entry.is_dir())
    for name in ('logs', 'results-workload', 'generated-topology-diagrams', 'workloads'):
        (manager / name).mkdir()
    source = (deploy / 'firesim').read_text()
    old = 'env.disable_known_hosts = True'
    key = 'env.key_filename = os.path.expanduser("~/firesim.pem")'
    if source.count(old) != 1 or source.count(key) != 1:
        raise ValueError('Manager SSH integration changed; audit before patching')
    source = source.replace(old, 'env.disable_known_hosts = False\n    env.reject_unknown_hosts = True')
    source = source.replace(key, 'env.user = os.environ["IRIS_FIRESIM_SSH_USER"]\n    env.key_filename = os.environ["IRIS_FIRESIM_SSH_KEY"]')
    (manager / 'firesim').write_text(source)
    (manager / 'firesim').chmod(0o755)
    workload_dir = manager / 'workloads' / 'iris-batch'
    workload_dir.mkdir()
    shutil.copy2(elf, workload_dir / 'batch.elf')
    if digest(elf) != digest(workload_dir / 'batch.elf'):
        raise ValueError('ELF changed during preparation')
    (manager / 'workloads' / 'iris-batch.json').write_text(json.dumps({
        'benchmark_name': 'iris-batch', 'common_bootbinary': 'batch.elf',
        'common_rootfs': None, 'workloads': [{'name': 'iris-batch0'}],
        'common_simulation_outputs': ['uartlog']}, indent=2) + '\n')
    runtime = yaml.safe_load(runtime_path.read_text())
    runtime['workload']['workload_name'] = 'iris-batch.json'
    runtime['workload']['terminate_on_completion'] = True
    if type(profile_interval) is not int or profile_interval <= 0:
        raise ValueError('Positive target-cycle profiling interval required')
    target_config = runtime.setdefault('target_config', {})
    if '+profile-interval' in target_config.get('plusarg_passthrough', ''):
        raise ValueError('Ambiguous manual profile-interval plusarg; use the recorded runtime field')
    original_profile_interval = target_config.get('profile_interval')
    target_config['profile_interval'] = profile_interval
    # Clock/memory timing and tracing stay as supplied. The profiling interval
    # override above requests observation; it does not create missing widgets.
    (manager / 'config_runtime.yaml').write_text(yaml.safe_dump(runtime, sort_keys=False))
    for name in ('config_build.yaml', 'config_build_recipes.yaml'):
        if (deploy / name).exists():
            shutil.copy2(deploy / name, manager / name)
    recipes_path=manager/'config_build_recipes.yaml'
    if recipes_path.is_file():
        recipes=yaml.safe_load(recipes_path.read_text())
        for recipe in recipes.values():
            if isinstance(recipe,dict) and recipe.get('TARGET_PROJECT_MAKEFRAG'):
                original=Path(recipe['TARGET_PROJECT_MAKEFRAG'])
                if not original.is_absolute():original=(deploy/original).resolve()
                if not original.exists():raise ValueError('Build recipe makefrag is missing: '+str(original))
                recipe['TARGET_PROJECT_MAKEFRAG']=str(original)
        recipes_path.write_text(yaml.safe_dump(recipes,sort_keys=False))
    image_name = runtime['target_config']['default_hw_config']
    hwdb = yaml.safe_load(hwdb_path.read_text())
    if driver_tar is not None:
        hwdb[image_name]['driver_tar'] = driver_tar.resolve().as_uri()
    (manager / 'config_hwdb.yaml').write_text(yaml.safe_dump(hwdb, sort_keys=False))
    tar_uri = hwdb[image_name].get('bitstream_tar')
    image = {'name': image_name, 'uri': tar_uri, 'sha256': None}
    if isinstance(tar_uri, str) and tar_uri.startswith('file://'):
        image['sha256'] = digest(tar_uri[7:])
    inputs = {str(p): digest(p) for p in (deploy / 'firesim', runtime_path, hwdb_path, elf,
                                         INSPECTOR_PATH, CAPTURE_SOURCE,
                                         Path(__file__).with_name('CAMPAIGN_POLICY.md'))}
    for name in ('config_build.yaml','config_build_recipes.yaml'):
        path=deploy/name
        if path.is_file():inputs[str(path)]=digest(path)
    # The private manager imports these shared source files through symlinks.
    # Bind their actual bytes, not only a branch name or the front-end script.
    shared_sources = set(deploy.rglob('*.py'))
    for directory in (deploy / 'sudo-scripts',
                      deploy.parent / 'platforms/corigine_mimicturbo_gt/scripts'):
        if directory.is_dir():
            shared_sources.update(p for p in directory.rglob('*') if p.is_file())
    for path in sorted(shared_sources):
        inputs[str(path)] = digest(path)
    for path in (Path(__file__).with_name('source-clones.json'),
                 Path(__file__).with_name('firesim-observed-dirty.patch'),
                 INSPECTOR_PATH.with_name('managed-path-audit.json')):
        if path.is_file():
            inputs[str(path)] = digest(path)
    driver_uri = hwdb[image_name].get('driver_tar')
    driver = {'uri': driver_uri, 'sha256': None}
    if isinstance(driver_uri, str) and driver_uri.startswith('file://'):
        driver['sha256'] = digest(driver_uri[7:])
        inputs[driver_uri[7:]] = driver['sha256']
    observability = {'verified': False, 'reason': 'No exact candidate instrumentation audit supplied'}
    if observability_report is not None:
        observability_report = Path(observability_report).resolve()
        audit = json.loads(observability_report.read_text())
        if audit.get('schema') not in ('iris.candidate_image_observability.v2',
                                       'iris.candidate_image_observability.v3'):
            raise ValueError('Unsupported instrumentation audit schema')
        identities = audit.get('input_sha256', {})
        image_hashes = {value for name, value in identities.items() if Path(name).name == 'firesim.tar.gz'}
        driver_hashes = {value for name, value in identities.items() if Path(name).name == 'driver-bundle.tar.gz'}
        if (image['sha256'] not in image_hashes or driver['sha256'] not in driver_hashes or
                audit.get('loaded_image_verified') is not False):
            raise ValueError('Instrumentation audit does not bind this exact image/driver candidate')
        inputs[str(observability_report)] = digest(observability_report)
        observability = {'verified': True, 'report': str(observability_report),
                         'sha256': digest(observability_report), 'candidate_only': True,
                         'loaded_image_verified': False,
                         'bridge_constructors': audit['generated_bridge_constructors'],
                         'fased': audit['fased'],
                         'unavailable': audit['collateral_unavailable_instrumentation']}
    manifest = {'schema_version': 1, 'created_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'status': 'prepared', 'cases': cases, 'image': image, 'driver': driver,
                'input_sha256': inputs, 'elf_sha256': digest(elf),
                'prepared_manager_sha256': digest(manager / 'firesim'),
                'prepared_runtime_sha256': digest(manager / 'config_runtime.yaml'),
                'prepared_hwdb_sha256': digest(manager / 'config_hwdb.yaml'),
                'prepared_file_sha256': {str(p.relative_to(output)):digest(p) for p in sorted(manager.rglob('*'))
                    if p.is_file() and not p.is_symlink() and not any(parent.is_symlink() for parent in p.parents if parent!=output)},
                'runner_sha256': digest(Path(__file__)),
                'observability_audit': observability,
                'capture_checklist_frozen': observability['verified'],
                'observability_override': {'field': 'target_config.profile_interval',
                    'original': original_profile_interval, 'prepared': profile_interval,
                    'target_cycle_argument': '+profile-interval=' + str(profile_interval),
                    'changes_clock_or_memory_parameters': False},
                'optional_copyback': ['memory_stats0.csv', 'latency_histogram.csv', 'heartbeat.csv', 'sim-run.sh', 'uartlog'],
                'capture_policy': 'quiescent job after owned cleanup; separate raw phase streams; archive outside job',
                'shared_manager_source_files_bound': len(shared_sources),
                'source_association_status': 'actual local inputs bound; loaded-image/driver build association unverified',
                'commands': [], 'target_cycles': None,
                'note': 'Host elapsed seconds are not target cycles. Cases execute inside a single prebuilt ELF.'}
    save_manifest(output, manifest)
    return manager, manifest


def save_manifest(output, manifest):
    temporary = output / 'run.json.tmp'
    temporary.write_text(json.dumps(manifest, indent=2) + '\n')
    temporary.replace(output / 'run.json')


def parse_regions(console, cases, elf_sha256, image_sha256, require_regions=False, require_goldens=False):
    """Accept target counter records only; reject ambiguous overflow/duplicates."""
    validate_cases(cases,require_goldens)
    declared = {case['id']: set(case['active_harts']) for case in cases}
    specifications={case['id']:case for case in cases}
    records, seen = [], set()
    for line in console.splitlines():
        line = line.strip()
        if not line.startswith('IRIS_REGION'):
            continue
        record = json.loads(line[len('IRIS_REGION'):].strip())
        if not isinstance(record, dict):
            raise ValueError('IRIS_REGION payload must be an object')
        for key in ('case_id', 'region'):
            if not isinstance(record.get(key), str) or not record[key]:
                raise ValueError('Missing region identity: ' + key)
        for key in ('hart', 'start_cycle', 'end_cycle', 'instret_delta', 'checksum'):
            if type(record.get(key)) is not int or not 0 <= record[key] < 2**64:
                raise ValueError('Invalid unsigned target counter: ' + key)
        if 'pass' in record and record['pass'] is not True:
            raise ValueError('Guest region reports failed correctness')
        if 'expected_checksum' in record:
            expected = record['expected_checksum']
            if type(expected) is not int or not 0 <= expected < 2**64 or expected != record['checksum']:
                raise ValueError('Guest region checksum mismatch')
        if record['case_id'] not in declared or record['hart'] not in declared[record['case_id']]:
            raise ValueError('Region refers to an undeclared case or active hart')
        specification=specifications[record['case_id']]
        if specification.get('region',record['region'])!=record['region']:
            raise ValueError('Guest region disagrees with host case identity')
        expected=specification.get('expected_checksums_by_hart')
        if expected is not None and record['checksum']!=expected[record['hart']]:
            raise ValueError('Guest result disagrees with independent host checksum')
        if record['end_cycle'] < record['start_cycle']:
            raise ValueError('Counter wrap or reversed region; shorten or split the measurement')
        identity = (record['case_id'], record['region'], record['hart'])
        if identity in seen:
            raise ValueError('Duplicate region identity; give repeated trials distinct case ids')
        seen.add(identity)
        record.update(cycles=record['end_cycle'] - record['start_cycle'],
                      elf_sha256=elf_sha256, image_sha256=image_sha256,
                      independent_checksum_validated=expected is not None)
        records.append(record)
    if require_regions or require_goldens:
        measured = {(record['case_id'], record['hart']) for record in records}
        missing = [(name, hart) for name, harts in declared.items() for hart in harts
                   if (name, hart) not in measured]
        if missing:
            raise ValueError('Missing target regions for case/hart pairs: ' + repr(missing))
    return records


def decode_compact_console(manager, manifest, console):
    """Validate the explicitly admitted compact campaign before normalization.

    This is a collector for one frozen campaign, not a fallback for malformed
    JSON or an incomplete guest. The independent oracle verifies every encoded
    record and both completed hart sections before parse_regions sees it.
    """
    descriptor = manifest.get('compact_collector')
    if not isinstance(descriptor, dict) or descriptor.get('format') != 'IRIS_BIN_17Q_LE_base64_v1':
        raise ValueError('Unknown compact console format')
    review_path = WORKSPACE / 'firesim/rvv_compute1320_review.py'
    if descriptor.get('review_path') != str(review_path):
        raise ValueError('Unknown compact campaign reader')
    # Admission binds every transitive reader/oracle input, not just its entry
    # point. Check those bytes again before importing any campaign code.
    for name, expected in manifest['input_sha256'].items():
        if digest(name) != expected:
            raise ValueError('Compact reader input changed: ' + name)
    if (descriptor.get('review_sha256') != digest(review_path) or
            manifest['input_sha256'].get(str(review_path)) != descriptor['review_sha256']):
        raise ValueError('Compact reader source digest mismatch')
    job = manager.parent
    corpus_path, ready_path = job / 'corpus.json', job / 'ready.json'
    elf_path = manager / 'workloads/iris-batch/batch.elf'
    for path, key, bound in ((corpus_path, 'corpus_sha256', manifest['corpus_sha256']),
                             (ready_path, 'ready_sha256', manifest['reviewed_ready_sha256']),
                             (elf_path, 'ELF_sha256', manifest['elf_sha256'])):
        if descriptor.get(key) != bound or digest(path) != bound:
            raise ValueError('Compact console artifact binding mismatch: ' + key)
    spec = importlib.util.spec_from_file_location('iris_frozen_compute1320_reader', review_path)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    if manifest.get('campaign_role') != review.ROLE or manifest['elf_sha256'] != review.ELF:
        raise ValueError('Compact console campaign/ELF mismatch')
    corpus = json.loads(corpus_path.read_text())
    layout = json.loads((job / 'layout.json').read_text())
    admitted = json.loads((job / 'review.json').read_text())
    if (digest(job / 'layout.json') != manifest['prepared_file_sha256']['layout.json'] or
            digest(job / 'review.json') != manifest['prepared_file_sha256']['review.json'] or
            review.inspect(elf_path.read_bytes(), corpus, layout) != admitted['compiled_and_layout_proof'] or
            review.flatten(corpus) != manifest['cases']):
        raise ValueError('Compact compiled table/layout/host cases mismatch')
    validated = review.validator().validate(console, corpus)
    if validated.get('normal_completion') is not True or validated.get('regions') != manifest['expected_regions']:
        raise ValueError('Compact guest did not complete all independently checked regions')
    manifest['compact_console_validation'] = validated
    return review.expand(console, corpus)


def collect_guest_results(manager, manifest):
    logs = sorted((manager / 'results-workload').rglob('uartlog'))
    if not logs:
        raise RuntimeError('No guest console artifact was returned')
    console = '\n'.join(path.read_text(errors='replace') for path in logs)
    exits = [int(value) for value in re.findall(r'COMMAND_EXIT_CODE="([0-9]+)"', console)]
    if any(exits):
        raise RuntimeError('Guest simulation console reports nonzero process exit: ' + repr(exits))
    manifest['console_process_exit_codes'] = exits
    manifest['emulation_target_cycles'] = [int(value) for value in
        re.findall(r'Target Cycles Emulated:\s*([0-9]+)', console)]
    if manifest.get('compact_collector') is not None:
        if (exits != [0] or console.count('COMMAND_EXIT_CODE') != 1 or
                '[COMMAND_EXIT_CODE="0"]' not in console):
            raise RuntimeError('Compact guest requires exactly one verified console exit zero')
        console = decode_compact_console(manager, manifest, console)
    manifest['regions'] = parse_regions(console, manifest['cases'], manifest['elf_sha256'],
                                       manifest['image']['sha256'], manifest.get('require_regions', False),
                                       manifest.get('require_goldens',False))
    manifest['regions_validated'] = bool(manifest['regions'])
    manifest['region_checksums_independently_validated']=bool(manifest['regions']) and all(
        row['independent_checksum_validated'] for row in manifest['regions'])


def run_task(manager, output, task, env, timeout, manifest):
    command = [sys.executable, str(manager / 'firesim'), task,
               '-c', str(manager / 'config_runtime.yaml'), '-a', str(manager / 'config_hwdb.yaml')]
    index = len(manifest['commands']) + 1
    stdout_path = output / (str(index) + '-' + task + '.stdout')
    stderr_path = output / (str(index) + '-' + task + '.stderr')
    actual = {'manager_sha256': digest(manager / 'firesim'),
              'runtime_sha256': digest(manager / 'config_runtime.yaml'),
              'hwdb_sha256': digest(manager / 'config_hwdb.yaml'),
              'python_executable_sha256': digest(sys.executable)}
    expected = {'manager_sha256': manifest.get('prepared_manager_sha256'),
                'runtime_sha256': manifest.get('execution_runtime_sha256'),
                'hwdb_sha256': manifest.get('prepared_hwdb_sha256')}
    for key, value in expected.items():
        if value is not None and actual[key] != value:
            raise RuntimeError('Execution input changed before phase: ' + key)
    for name, expected_digest in manifest.get('input_sha256', {}).items():
        if digest(name) != expected_digest:
            raise RuntimeError('Prepared source input changed before phase: ' + name)
    record = {'task': task, 'phase_index': index, 'argv': command,
              'started_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'stdout_path': str(stdout_path.relative_to(output)),
              'stderr_path': str(stderr_path.relative_to(output)),
              'streams_merged': False, 'actual_input_sha256': actual,
              'timeout_seconds': timeout, 'timed_out': False, 'status': 'starting',
              'cleanup_phase': manifest.get('active_phase') == 'cleanup'}
    manifest['commands'].append(record)
    save_manifest(output, manifest)
    started = time.monotonic()
    with stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
        try:
            process = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        except BaseException as error:
            record.update(status='spawn_failed', error=str(error), host_elapsed_seconds=time.monotonic() - started,
                          stdout_sha256=digest(stdout_path), stderr_sha256=digest(stderr_path))
            save_manifest(output, manifest)
            raise
        record.update(pid=process.pid, status='running')
        save_manifest(output, manifest)
        try:
            returncode = process.wait(timeout=timeout)
        except BaseException as error:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            stdout.flush(); stderr.flush()
            record.update(host_elapsed_seconds=time.monotonic() - started, interrupted=True,
                          timed_out=isinstance(error, subprocess.TimeoutExpired),
                          returncode=process.returncode, status='timed_out' if isinstance(error, subprocess.TimeoutExpired) else 'interrupted',
                          stdout_sha256=digest(stdout_path), stderr_sha256=digest(stderr_path))
            save_manifest(output, manifest)
            raise
    record.update(returncode=returncode, host_elapsed_seconds=time.monotonic() - started,
                  status='passed' if returncode == 0 else 'failed',
                  stdout_sha256=digest(stdout_path), stderr_sha256=digest(stderr_path))
    save_manifest(output, manifest)
    if returncode:
        raise RuntimeError('FireSim task failed: ' + task + ', exit ' + str(returncode))


def execute(manager, output, host, allocation_id, timeout, manifest):
    try:
        _execute_managed(manager, output, host, allocation_id, timeout, manifest)
    except BaseException as error:
        if isinstance(error, EvidenceCaptureError):
            manifest['capture_error'] = str(error)
        else:
            manifest.update(status='failed', error=str(error))
        manifest.setdefault('cleanup_status', 'not_started')
        save_manifest(output, manifest)
        if 'capture' not in manifest and not manifest.get('lock_retained_for_operator'):
            try:
                capture_quiescent_run(output, manifest)
            except BaseException as capture_error:
                manifest['capture'] = {'status': 'failed', 'error': str(capture_error)}
                save_manifest(output, manifest)
        raise


def observe_selected_memory_settings(output, owned_dir, uid, host):
    try:
        from firesim.memory_observation import observe
    except ModuleNotFoundError:
        from memory_observation import observe
    return observe(output, owned_dir, uid, ssh_prefix(host))


def _execute_managed(manager, output, host, allocation_id, timeout, manifest):
    if not allocation_id:
        raise ValueError('--authorization-id is required for execution')
    if not os.environ.get('FIRESIM_SOURCED'):
        raise RuntimeError('Source the Chipyard FireSim sourceme-manager.sh environment first')
    if not manifest['driver']['sha256']:
        raise RuntimeError('Supply a local matching --driver-tar; rebuilding a driver inside the shared source tree is disabled')
    if manifest.get('capture_checklist_frozen') is not True or manifest.get('observability_audit', {}).get('verified') is not True:
        raise RuntimeError('Exact candidate observability audit and frozen capture checklist required before hardware execution')
    # Query OpenSSH's actual resolved account and key; never read key bytes.
    resolved = subprocess.check_output(['ssh', '-G', host], text=True, stderr=subprocess.DEVNULL)
    config = {}
    for line in resolved.splitlines():
        key, _, value = line.partition(' ')
        config.setdefault(key, value)
    key_path = Path(config['identityfile']).expanduser()
    if not key_path.is_file():
        raise RuntimeError('Configured SSH identity file is unavailable')
    import yaml
    runtime = yaml.safe_load((manager / 'config_runtime.yaml').read_text())
    hosts = runtime['run_farm']['recipe_arg_overrides']['run_farm_hosts_to_use']
    if len(hosts) != 1 or set(hosts[0]) != {config['hostname']}:
        raise RuntimeError('Runtime must target exactly the SSH host that was inspected')
    remote = bind_launch_authorization(host, inspect_remote(host), manifest)
    manifest.update(remote=remote, authorization_id=allocation_id, allocation_id=allocation_id,
                    authorization_scope='Current explicit user launch instruction; no operator reservation claimed')
    save_manifest(output, manifest)
    require_safe_remote(remote, allocation_id)
    token = uuid.uuid4().hex
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', config['user']):
        raise RuntimeError('Unsupported remote account name')
    owned_dir = '/scratch/' + config['user'] + '/firesim/' + token
    runtime['run_farm']['recipe_arg_overrides']['default_simulation_dir'] = owned_dir
    (manager / 'config_runtime.yaml').write_text(yaml.safe_dump(runtime, sort_keys=False))
    manifest.update(remote_simulation_dir=owned_dir, lock_token=token,
                    execution_runtime_sha256=digest(manager / 'config_runtime.yaml'),
                    lifecycle_policy='kill -> infrasetup -> runworkload -> kill')
    save_manifest(output, manifest)
    lock_identity = {'uid':remote['uid'],'user':remote['user'],'boot_id':remote['boot_id'],
                     'authorization_id':allocation_id,'authorization_sha256':manifest['launch_authorization_receipt']['sha256']}
    manifest['shared_lock']={'path':'/scratch/firesim/iris-locks/fpga0','kind':'exclusive_atomic_directory',**lock_identity}
    checked_remote_lock(host, token, True, lock_identity)
    env = dict(os.environ, IRIS_FIRESIM_SSH_USER=config['user'], IRIS_FIRESIM_SSH_KEY=str(key_path))
    primary_error = None
    cleanup_error = None
    lifecycle_started = False
    manifest['lifecycle_started'] = False
    try:
        # Recheck allocation, boot identity and ALL users before EVERY action.
        for task in ('kill', 'infrasetup', 'runworkload'):
            manifest['active_phase'] = task
            checked_remote_lock(host, token, None, lock_identity)
            inspection = bind_launch_authorization(host, inspect_remote(host), manifest)
            if task=='runworkload':
                inspection=await_setup_quiescence(host,inspection,manifest,output,lock_identity)
            manifest.setdefault('safety_inspections', []).append(dict(stage=task, report=inspection))
            save_manifest(output, manifest)
            require_safe_remote(inspection, allocation_id, remote['boot_id'])
            lifecycle_started = True
            manifest['lifecycle_started'] = True
            if task == 'infrasetup':
                manifest['private_directory'] = create_remote_private_directory(host, owned_dir)
                if manifest['private_directory'].get('uid') != remote['uid']:
                    raise RuntimeError('Private directory SSH account identity changed')
                save_manifest(output, manifest)
            if task == 'runworkload':
                verify_remote_staging(host, owned_dir, manifest, output)
                save_manifest(output, manifest)
                if manifest.get('readonly_memory_observation') is not None:
                    # Optional BAR reads are hardware access too. Prove idle
                    # under the same held lock immediately before AND after.
                    checked_remote_lock(host, token, None, lock_identity)
                    before = bind_launch_authorization(host, inspect_remote(host), manifest)
                    manifest.setdefault('safety_inspections', []).append(
                        dict(stage='readonly_memory_before', report=before))
                    save_manifest(output, manifest)
                    require_safe_remote(before, allocation_id, remote['boot_id'])
                    try:
                        manifest['readonly_memory_observation_result'] = observe_selected_memory_settings(
                            output, owned_dir, remote['uid'], host)
                    except Exception as error:
                        manifest['readonly_memory_observation_result'] = {
                            'optional': True, 'status': 'unavailable', 'error': str(error),
                            'selected_parameters': None, 'calibration_usable': False}
                    save_manifest(output, manifest)
                    checked_remote_lock(host, token, None, lock_identity)
                    after = bind_launch_authorization(host, inspect_remote(host), manifest)
                    manifest.setdefault('safety_inspections', []).append(
                        dict(stage='readonly_memory_after', report=after))
                    save_manifest(output, manifest)
                    require_safe_remote(after, allocation_id, remote['boot_id'])
            run_task(manager, output, task, env, timeout, manifest)
        collect_guest_results(manager, manifest)
    except BaseException as error:
        primary_error = error
    finally:
        if lifecycle_started:
            try:
                manifest['active_phase'] = 'cleanup'
                checked_remote_lock(host, token, None, lock_identity)
                inspection = bind_launch_authorization(host, inspect_remote(host), manifest)
                manifest.setdefault('safety_inspections', []).append(dict(stage='cleanup', report=inspection))
                save_manifest(output, manifest)
                require_safe_remote(inspection, allocation_id, remote['boot_id'], owned_dir)
                run_task(manager, output, 'kill', env, min(timeout, 180), manifest)
                manifest['cleanup_status'] = 'passed'
            except BaseException as error:
                cleanup_error = error
                manifest['cleanup_status'] = 'refused_or_failed'
        else:
            manifest['cleanup_status'] = 'not_started'
        if lifecycle_started and cleanup_error is None:
            try:
                manifest['optional_observability'] = collect_optional_observability(host, owned_dir, output, remote['uid'])
            except BaseException as error:
                manifest['optional_observability'] = {'optional': True, 'status': 'unavailable', 'error': str(error)}
        try:
            if cleanup_error:
                manifest['lock_retained_for_operator'] = True
            else:
                checked_remote_lock(host, token, False, lock_identity)
        except BaseException as error:
            manifest['lock_release_error'] = str(error)
            manifest['lock_retained_for_operator'] = True
            cleanup_error = cleanup_error or error
        manifest['status'] = 'failed' if primary_error or cleanup_error else 'completed_uncertified'
        manifest['error'] = str(primary_error) if primary_error else None
        manifest['cleanup_error'] = str(cleanup_error) if cleanup_error else None
        manifest['artifact_sha256'] = {str(p.relative_to(output)): digest(p)
                                    for p in manager.joinpath('results-workload').rglob('*') if p.is_file()}
        save_manifest(output, manifest)
        if cleanup_error:
            manifest['capture'] = {'status': 'withheld', 'reason': 'Owned cleanup/lock release is unverified; preserve files and lock for operator'}
            save_manifest(output, manifest)
        else:
            try:
                capture_quiescent_run(output, manifest)
            except BaseException as error:
                manifest['capture'] = {'status': 'failed', 'error': str(error)}
                save_manifest(output, manifest)
    if primary_error or cleanup_error:
        raise RuntimeError(str(primary_error or cleanup_error))
    if manifest.get('capture', {}).get('status') != 'captured':
        raise EvidenceCaptureError('Guest outcome retained; evidence capture failed')


def main(argv=None):
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deploy', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True, help='One ELF containing all cases')
    parser.add_argument('--cases', type=Path, required=True, help='JSON array of cases and active_harts')
    parser.add_argument('--output', type=Path, required=True, help='New artifact directory')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--hwdb', type=Path)
    parser.add_argument('--driver-tar', type=Path, help='Matching prebuilt driver bundle; required for execution unless present in HWDB')
    parser.add_argument('--observability-report', type=Path, default=OBSERVABILITY_REPORT,
                        help='Reviewed exact image/driver instrumentation inventory')
    parser.add_argument('--host', default='sohumpc')
    parser.add_argument('--authorization-id','--allocation-id',dest='allocation_id',help='Current explicit user launch authorization receipt identifier')
    parser.add_argument('--timeout', type=int, default=1800, help='Host seconds per task, not target cycles')
    parser.add_argument('--execute', action='store_true', help='Otherwise prepare only')
    parser.add_argument('--require-regions', action='store_true', help='Require target CSR measurements for every declared case/hart')
    parser.add_argument('--require-goldens', action='store_true', help='Require all declared regions and independent frozen host checksums')
    args = parser.parse_args(argv)
    try:
        deploy, output, elf = args.deploy.resolve(), args.output.resolve(), args.elf.resolve()
        with elf.open('rb') as stream:
            if stream.read(4) != b'\x7fELF':
                raise ValueError('Input must be an ELF')
        cases = validate_cases(json.loads(args.cases.read_text()),args.require_goldens)
        if args.timeout <= 0:
            raise ValueError('Timeout must be positive')
        manager, manifest = prepare(deploy, output, elf, cases,
                                    (args.runtime or deploy / 'config_runtime.yaml').resolve(),
                                    (args.hwdb or deploy / 'config_hwdb.yaml').resolve(), args.driver_tar,
                                    observability_report=args.observability_report)
        manifest['require_regions'] = args.require_regions
        manifest['require_goldens'] = args.require_goldens
        save_manifest(output, manifest)
        if args.execute:
            lock = output.parent / '.iris-firesim-manager.lock'
            with lock.open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                execute(manager, output, args.host, args.allocation_id, args.timeout, manifest)
        print(output / 'run.json')
        return 0
    except (Exception, KeyboardInterrupt) as error:
        if 'manifest' in locals():
            if not isinstance(error, EvidenceCaptureError):
                manifest.update(status='failed', error=str(error))
            save_manifest(output, manifest)
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
