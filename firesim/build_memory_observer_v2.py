#!/usr/bin/env python3
"""Build/audit the five-register no-write observer using ordinary fake files only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

from audit_fased_config_v2 import audit, REGISTERS

ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def trace_no_write(text,fixture):
    path=str(fixture);lines=[line for line in text.splitlines() if path in line]
    opens=[line for line in lines if re.match(r'^(?:open|openat)\(',line)]
    maps=[line for line in lines if line.startswith('mmap(')]
    if len(opens)!=1 or 'O_RDONLY' not in opens[0] or any(x in opens[0]for x in ('O_WRONLY','O_RDWR','O_CREAT','O_TRUNC')):
        raise ValueError('Fake target not opened solely read-only')
    if len(maps)!=1 or 'PROT_READ, MAP_SHARED'not in maps[0] or 'PROT_WRITE'in maps[0]:
        raise ValueError('Fake target mapping is not read-only')
    if any(re.match(r'^(?:write|writev|pwrite64|ioctl)\(',line)for line in lines):
        raise ValueError('Observer attempted target write/ioctl')
    return {'target_open_calls':len(opens),'target_mappings':len(maps),'target_write_or_ioctl_calls':0}


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve()
    if o.exists():raise ValueError('Fresh build directory required')
    checked=audit();o.mkdir(parents=True);(o/'binary-MMIO-audit.json').write_text(json.dumps(checked,indent=2)+'\n')
    source=ROOT/'firesim/readonly_fased_config_v2.c';local=o/source.name;shutil.copyfile(source,local)
    compiler=Path('/usr/bin/cc').resolve();binary=o/'readonly-fased-config-v2'
    cmd=[str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-save-temps=obj','-Wl,-Map,'+str(o/'link.map'),'-o',str(binary),str(local)]
    r=subprocess.run(cmd,capture_output=True,timeout=30);(o/'build.stdout').write_bytes(r.stdout);(o/'build.stderr').write_bytes(r.stderr)
    if r.returncode:raise ValueError('Observer build failed; logs preserved')
    fakes=o/'fake-registers';fakes.mkdir();values=dict(writeLatency=37,readLatency=41,writeMaxReqs=5,readMaxReqs=7,relaxFunctionalModel=1)
    def fake(name,changes=None,presence=0x46697265):
        raw=bytearray(4096)
        for k,v in dict(values,**(changes or {})).items():struct.pack_into('<I',raw,REGISTERS[k],v)
        struct.pack_into('<I',raw,356,presence);path=fakes/(name+'.bin');path.write_bytes(raw);return path
    valid=fake('valid');controls=[]
    def run(label,argv,expected):
        before={str(p):sha(p)for p in fakes.iterdir()if p.is_file()};r=subprocess.run([str(binary)]+argv,capture_output=True,timeout=5)
        (o/(label+'.stdout')).write_bytes(r.stdout);(o/(label+'.stderr')).write_bytes(r.stderr)
        if r.returncode!=expected or any(sha(p)!=d for p,d in before.items()):raise ValueError('Control or no-write failure '+label)
        controls.append(dict(label=label,expected_exit_status=expected,actual_exit_status=r.returncode,files_unchanged=True))
        return json.loads(r.stdout) if r.stdout else None
    observed=run('positive',['--test-file',str(valid)],0)
    for k,v in values.items():
        if observed[k]!={'byte_offset':REGISTERS[k],'first':v,'second':v}:raise ValueError('Wrong extended field readout '+k)
    run('positive-relax0',['--test-file',str(fake('valid-relax0',{'relaxFunctionalModel':0}))],0)
    for name in REGISTERS:
        run('allones-'+name,['--test-file',str(fake('allones-'+name,{name:0xffffffff}))],1)
        run('changed-'+name,['--test-file-pair',str(valid),str(fake('changed-'+name,{name:0 if name=='relaxFunctionalModel'else values[name]+1}))],1)
    run('bad-presence-before',['--test-file',str(fake('bad-presence',presence=0))],1)
    run('bad-presence-after',['--test-file-pair',str(valid),str(fakes/'bad-presence.bin')],1)
    run('invalid-relax-domain',['--test-file',str(fake('relax2',{'relaxFunctionalModel':2}))],1)
    short=fakes/'truncated.bin';short.write_bytes(b'\0'*359);run('truncated',['--test-file',str(short)],1)
    run('wrong-device-argument',['--read-idle-device','/tmp/NOT-A-DEVICE'],2)
    trace=o/'strace-fake-readonly.log';r=subprocess.run(['/usr/bin/strace','-qq','-yy','-o',str(trace),'-e','trace=open,openat,mmap,write,writev,pwrite64,ioctl',str(binary),'--test-file',str(valid)],capture_output=True,timeout=5)
    (o/'strace.stdout').write_bytes(r.stdout);(o/'strace.stderr').write_bytes(r.stderr)
    if r.returncode:raise ValueError('Read-only fake strace failed')
    trace_proof=trace_no_write(trace.read_text(),valid)
    badtrace=trace.read_text()+f'\npwrite64(3<{valid}>, "bad", 3, 0) = 3\n'
    try:trace_no_write(badtrace,valid)
    except ValueError:trace_guard=True
    else:raise ValueError('Trace no-write checker accepted corruption')
    inputs={str(p):sha(p)for p in[Path(__file__),source,ROOT/'firesim/audit_fased_config_v2.py',compiler,Path('/usr/bin/strace')]}
    inputs.update(checked['input_sha256'])
    for name in('cc1','as','collect2','ld'):
        name=subprocess.check_output([str(compiler),'-print-prog-name='+name],text=True).strip();tool=Path(name).resolve()if'/'in name else Path(shutil.which(name)).resolve();inputs[str(tool)]=sha(tool)
    for token in re.findall(r'^LOAD\s+(\S+)',(o/'link.map').read_text(),re.M):
        path=Path(token)
        if path.is_file()and o not in path.resolve().parents:inputs[str(path.resolve())]=sha(path)
    report={'schema':'iris.readonly_fased_config_observer_build.v2','pass':True,'hardware_contacted':False,
            'argv':cmd,'source_sha256':sha(source),'binary_sha256':sha(binary),'registers':REGISTERS,
            'fake_controls':controls,'strace_no_write':trace_proof,'strace_write_corruption_rejected':trace_guard,
            'test_file_pair_scope':'Explicit regular-file peripheral snapshot change; never used with device mode',
            'source_defaults_used_as_observed_values':False,'configuration_readback_only':True,
            'source_image_association_verified':False,'calibration_usable':False,
            'input_sha256':inputs,'artifact_sha256':{str(p.relative_to(o)):sha(p)for p in o.rglob('*')if p.is_file()}}
    snapshots=o/'inputs';snapshots.mkdir()
    for name,d in inputs.items():
        target=snapshots/d
        if not target.exists():shutil.copyfile(name,target)
    (o/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'controls':len(controls),'binary_sha256':sha(binary),'source_sha256':sha(source),'report_sha256':sha(o/'report.json')}))


if __name__=='__main__':main()
