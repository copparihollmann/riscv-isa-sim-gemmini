"""Optional read-only FASED settings observation inside the owned managed run."""
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '4990a9d4db717fc2b1cb30aa14b0f2b8653f30f9c58f93e9d164aae0f89b59e9'
BINARY_SHA = '0becce9fa23ffe402395ded77d3c761a83a0117095bd49e9d8a07028d38bf780'
HEADER_SHA = '89344115e3310113fa743169e4c47dc5d200a3f4585e23bf5a5b2fbc73cdfa51'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(build, output, manifest):
    """Admit only the exact reviewed no-write source/binary/register contract."""
    build, output = Path(build), Path(output)
    receipt = json.loads((build / 'report.json').read_text())
    audit = manifest['observability_audit']
    audit_path = Path(audit['report'])
    details = json.loads(audit_path.read_text())
    if digest(audit_path) != audit['sha256'] or audit.get('verified') is not True:
        raise ValueError('Exact frozen observability audit required for BAR observation')
    if (receipt.get('schema') != 'iris.readonly_memory_observer_build.v1' or receipt.get('pass') is not True
            or receipt.get('source_sha256') != SOURCE_SHA or receipt.get('binary_sha256') != BINARY_SHA
            or digest(build / 'readonly-fased-latency') != BINARY_SHA
            or details.get('generated_header_sha256') != HEADER_SHA
            or details.get('fased', {}).get('readable', {}).get('writeLatency') != 0
            or details.get('fased', {}).get('readable', {}).get('readLatency') != 4):
        raise ValueError('Unreviewed memory observer source/binary/header/register layout')
    for group in ('input_sha256', 'artifact_sha256'):
        for name, expected in receipt[group].items():
            path = Path(name) if group == 'input_sha256' else build / name
            if digest(path) != expected:
                raise ValueError('Observer build closure changed: ' + str(path))
            manifest['input_sha256'][str(path)] = expected
    target = output / 'memory-observation'; target.mkdir()
    shutil.copyfile(build / 'readonly-fased-latency', target / 'readonly-fased-latency')
    shutil.copyfile(build / 'report.json', target / 'build.json')
    for path in (Path(__file__).resolve(), build / 'report.json'):
        manifest['input_sha256'][str(path)] = digest(path)
    specification = {'schema': 'iris.readonly_memory_observation_plan.v1',
        'binary': 'memory-observation/readonly-fased-latency', 'binary_sha256': BINARY_SHA,
        'source_sha256': SOURCE_SHA, 'helper_sha256': digest(Path(__file__)),
        'build_receipt_sha256': digest(build / 'report.json'), 'generated_header_sha256': HEADER_SHA,
        'device': '/dev/xdma0_user', 'bdf': '0000:01:00.0',
        'phase': 'after managed programming and complete idle inspection, before driver initialization',
        'access': 'O_RDONLY/PROT_READ; no register writes', 'optional': True,
        'presence_guard': 'FireSim magic before/after; not image identity',
        'clock_units': 'FASED memory-model target-clock cycles, not CPU cycles',
        'hardware_source_association_verified': False, 'calibration_usable': False}
    manifest['readonly_memory_observation'] = specification
    (target / 'plan.json').write_text(json.dumps(specification, indent=2) + '\n')
    return specification


REMOTE = r'''
import base64,datetime,grp,hashlib,json,os,pathlib,pwd,re,stat,subprocess,sys
def sha(p):
 return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def protected(p):
 p=pathlib.Path(p).resolve(strict=True)
 for parent in [p]+list(p.parents):
  info=parent.stat()
  if info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Unprotected runtime path: '+str(parent))
 return {'path':str(p),'sha256':sha(p)}
def own_lock():
 parent=pathlib.Path('/scratch/firesim/iris-locks');p=parent/'fpga0'
 info=parent.lstat()
 if parent.resolve()!=parent or info.st_uid!=0 or info.st_gid!=grp.getgrnam('firesim').gr_gid or stat.S_IMODE(info.st_mode)!=0o2770:raise ValueError('Untrusted shared lock parent')
 for item in [p,p/'owner.json']:
  info=item.lstat()
  if info.st_uid!=UID or info.st_mode&0o022 or item.is_symlink():raise ValueError('Untrusted owned lock')
 if json.loads((p/'owner.json').read_text())!=LOCK:raise ValueError('Shared lock token/account/boot/authorization changed')
 boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
 if LOCK['uid']!=os.getuid() or LOCK['user']!=pwd.getpwuid(os.getuid()).pw_name or LOCK['boot_id']!=boot:raise ValueError('Lock account/boot mismatch')
 path=pathlib.Path(AUTH);info=path.lstat()
 if path.resolve()!=path or not stat.S_ISREG(info.st_mode) or info.st_uid!=UID or info.st_mode&0o077:raise ValueError('Untrusted authorization receipt')
 data=path.read_bytes()
 if len(data)>32768 or hashlib.sha256(data).hexdigest()!=LOCK['authorization_sha256']:raise ValueError('Authorization changed')
 auth=json.loads(data);expiry=datetime.datetime.fromisoformat(auth['expires_at_utc'])
 if expiry.utcoffset() is None or expiry<=datetime.datetime.now(datetime.timezone.utc) or auth['authorization_id']!=LOCK['authorization_id'] or auth['uid']!=UID or auth['boot_id']!=boot:raise ValueError('Authorization expired or rebound')
record={'schema':'iris.remote_readonly_memory_observation.v1','status':'unavailable','hardware_writes':False,'hardware_access_started':False,'selected_parameters':None,'uid':os.getuid(),'base':BASE}
try:
 base=pathlib.Path(BASE)
 if not re.fullmatch(r'/scratch/[a-z_][a-z0-9_-]*/firesim/[0-9a-f]{32}',BASE):raise ValueError('Invalid owned directory')
 info=base.lstat()
 if base.resolve()!=base or not stat.S_ISDIR(info.st_mode) or info.st_uid!=UID or UID!=os.getuid() or info.st_mode&0o077:raise ValueError('Private directory account/type/permissions changed')
 own_lock()
 directory=base/'memory-observation';directory.mkdir(mode=0o700)
 binary=directory/'readonly-fased-latency'
 data=base64.b64decode(BINARY,validate=True)
 if len(data)>1048576 or hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Observer payload digest mismatch')
 fd=os.open(binary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o700)
 with os.fdopen(fd,'wb') as f:f.write(data)
 if sha(binary)!=EXPECTED:raise ValueError('Staged observer changed')
 record['binary_sha256']=EXPECTED
 record['python_runtime']=protected('/usr/bin/python3')
 record['python_version']=sys.version
 env={'PATH':'/usr/bin:/bin','LANG':'C'}
 traced=subprocess.run([str(binary)],env=dict(env,LD_TRACE_LOADED_OBJECTS='1'),cwd=directory,stdin=subprocess.DEVNULL,capture_output=True,timeout=5)
 record['runtime_trace_stdout_b64']=base64.b64encode(traced.stdout).decode()
 record['runtime_trace_stderr_b64']=base64.b64encode(traced.stderr).decode()
 if traced.returncode:raise ValueError('Dynamic runtime inspection failed')
 libraries=sorted(set(re.findall(r'(/[^\s()]+)',traced.stdout.decode('ascii'))))
 if len(libraries)!=2 or not any(pathlib.Path(p).name=='libc.so.6' for p in libraries) or not any(pathlib.Path(p).name=='ld-linux-x86-64.so.2' for p in libraries):raise ValueError('Unexpected dynamic observer dependencies')
 record['dynamic_runtime']=[protected(p) for p in libraries]
 device=pathlib.Path('/dev/xdma0_user');node=device.lstat()
 if not stat.S_ISCHR(node.st_mode):raise ValueError('XDMA user node is not a character device')
 devno=str(os.major(node.st_rdev))+':'+str(os.minor(node.st_rdev))
 target=(pathlib.Path('/sys/dev/char')/devno).resolve(strict=True)
 if '0000:01:00.0' not in target.parts:raise ValueError('XDMA node does not match the inspected FPGA BDF')
 bdf=pathlib.Path('/sys/bus/pci/devices/0000:01:00.0')
 if (bdf/'vendor').read_text().strip()!='0x10ee' or (bdf/'device').read_text().strip()!='0x903f':raise ValueError('FPGA PCI identity changed')
 record['device_identity']={'major_minor':devno,'sysfs_path':str(target),'bdf':'0000:01:00.0','inode':node.st_ino}
 own_lock()
 record['hardware_access_started']=True
 result=subprocess.run([str(binary),'--read-idle-device','/dev/xdma0_user'],env=env,cwd=directory,stdin=subprocess.DEVNULL,capture_output=True,timeout=5)
 record.update(returncode=result.returncode,probe_stdout_b64=base64.b64encode(result.stdout).decode(),probe_stderr_b64=base64.b64encode(result.stderr).decode())
 after=device.lstat()
 if (node.st_rdev,node.st_ino)!=(after.st_rdev,after.st_ino) or target!=(pathlib.Path('/sys/dev/char')/devno).resolve(strict=True):raise ValueError('Device identity changed during observation')
 if sha(binary)!=EXPECTED:raise ValueError('Observer executable changed during observation')
 own_lock()
 record['probe']=json.loads(result.stdout)
 record['status']='sampled' if result.returncode==0 else 'probe_refused'
except Exception as exc:
 record['error']=str(exc)
print(json.dumps(record,sort_keys=True))
'''


def observe(output, owned_dir, uid, ssh):
    """Caller must own the lock and perform fresh complete idle checks around this."""
    output = Path(output)
    manifest = json.loads((output / 'run.json').read_text())
    plan = manifest['readonly_memory_observation']
    if manifest.get('lifecycle_started') is not True or manifest.get('active_phase') != 'runworkload':
        raise ValueError('Observer requires the active owned managed lifecycle')
    lock = {key: manifest['shared_lock'][key] for key in
            ('uid', 'user', 'boot_id', 'authorization_id', 'authorization_sha256')}
    lock['token'] = manifest['lock_token']
    if type(uid) is not int or uid != lock['uid'] or not re.fullmatch('[0-9a-f]{32}', lock['token']):
        raise ValueError('Invalid owned observer account/lock')
    if (plan.get('binary_sha256') != BINARY_SHA or plan.get('source_sha256') != SOURCE_SHA
            or plan.get('generated_header_sha256') != HEADER_SHA
            or plan.get('helper_sha256') != digest(Path(__file__))):
        raise ValueError('Frozen read-only observer contract changed')
    binary = output / 'memory-observation/readonly-fased-latency'
    if digest(binary) != BINARY_SHA:
        raise ValueError('Frozen observer executable changed')
    code = ('BASE=' + repr(owned_dir) + '\nUID=' + repr(uid) + '\nEXPECTED=' + repr(BINARY_SHA)
            + '\nLOCK=' + repr(lock) + '\nAUTH=' + repr(manifest['launch_authorization_receipt']['remote_path'])
            + '\nBINARY=' + repr(base64.b64encode(binary.read_bytes()).decode()) + '\n' + REMOTE)
    target = output / 'memory-observation'
    try:
        result = subprocess.run(ssh + ['/usr/bin/python3', '-I', '-S', '-'],
                                input=code.encode(), capture_output=True, timeout=25)
    except subprocess.TimeoutExpired as error:
        (target / 'transport.stdout').write_bytes(error.stdout or b'')
        (target / 'transport.stderr').write_bytes(error.stderr or b'')
        record = {'schema': 'iris.managed_memory_observation.v1', 'optional': True,
                  'status': 'unavailable', 'error': 'Read-only observation transport timed out',
                  'selected_parameters': None, 'calibration_usable': False,
                  'transport_stdout_sha256': digest(target / 'transport.stdout'),
                  'transport_stderr_sha256': digest(target / 'transport.stderr')}
        (target / 'observation.json').write_text(json.dumps(record, indent=2) + '\n')
        return record
    (target / 'transport.stdout').write_bytes(result.stdout)
    (target / 'transport.stderr').write_bytes(result.stderr)
    record = {'schema': 'iris.managed_memory_observation.v1', 'optional': True,
        'status': 'unavailable', 'selected_parameters': None, 'returncode': result.returncode,
        'sampled_before_driver_initialization': True, 'calibration_usable': False,
        'hardware_source_association_verified': False, 'loaded_image_readback_verified': False,
        'clock_units': 'FASED memory-model target-clock cycles, not CPU cycles',
        'transport_stdout_sha256': digest(target / 'transport.stdout'),
        'transport_stderr_sha256': digest(target / 'transport.stderr')}
    if result.returncode == 0:
        remote = json.loads(result.stdout)
        record['remote'] = remote
        for source, destination in [('probe_stdout_b64', 'probe.stdout'), ('probe_stderr_b64', 'probe.stderr')]:
            if source in remote:
                (target / destination).write_bytes(base64.b64decode(remote[source], validate=True))
        probe = remote.get('probe', {})
        valid = (remote.get('status') == 'sampled' and remote.get('returncode') == 0
                 and remote.get('binary_sha256') == BINARY_SHA
                 and remote.get('uid') == uid and remote.get('base') == owned_dir
                 and remote.get('device_identity', {}).get('bdf') == '0000:01:00.0'
                 and probe.get('test_file') is False and probe.get('hardware_writes') is False
                 and probe.get('access') == 'O_RDONLY/PROT_READ'
                 and probe.get('register_width_bits') == 32 and probe.get('presence_byte_offset') == 356
                 and probe.get('presence_verified_before_and_after') is True
                 and probe.get('stable_two_samples') is True)
        for name, offset in [('writeLatency', 0), ('readLatency', 4)]:
            value = probe.get(name, {})
            valid = (valid and value.get('byte_offset') == offset and type(value.get('first')) is int
                     and value['first'] == value.get('second') and 0 <= value['first'] < 2**32 - 1)
        if valid:
            record.update(status='observed_candidate_values', selected_parameters={
                name: probe[name]['first'] for name in ('writeLatency', 'readLatency')})
    (target / 'observation.json').write_text(json.dumps(record, indent=2) + '\n')
    return record
