#!/usr/bin/env python3
"""Owned normal executed-ELF run with a frozen new pair and explicit fixture."""
import argparse,datetime,importlib.util,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(a):
    cap=a.capsule.resolve();fixture=a.fixture.resolve();elf=a.elf.resolve();out=a.output.resolve()
    m=json.loads((cap/'manifest.json').read_text())
    for name,h in m['artifact_sha256'].items():
        if sha(cap/name)!=h:raise ValueError('Frozen capsule changed '+name)
    parent=ROOT/'build/memory-footprints-WFI-groups-hybrid7bd5-selected-v1/run.json';base=json.loads(parent.read_text());argv=base['argv'][:];argv[0]=str(cap/'spike');argv[-1]=str(elf)
    argv=[('--extlib='+str(cap/'libsifive_uart.so'))if x.startswith('--extlib=')else('--iris-timing-fixture='+str(fixture))if x.startswith('--iris-timing-fixture=')else('--iris-timing-trace='+str(out/'native-summary.json'))if x.startswith('--iris-timing-trace=')else x for x in argv]
    out.mkdir(parents=True,exist_ok=False);env=dict(os.environ);env['IRIS_EMPIRICAL_FEATURES']=str(out/'features.jsonl');env.pop('IRIS_EMPIRICAL_ASYNC_TRACE',None)
    spec=importlib.util.spec_from_file_location('frozen_fatal_elf_parser',ROOT/'spike/empirical_launch_v2.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);fatal=mod.fatal_addresses(elf)
    if fatal:env['IRIS_FATAL_PCS']=','.join(hex(x)for x in sorted(set(fatal.values())))
    else:env.pop('IRIS_FATAL_PCS',None)
    inputs=[Path(__file__).resolve(),cap/'manifest.json',cap/'spike',cap/'libsifive_uart.so',fixture,elf,parent,ROOT/'spike/empirical_launch_v2.py',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];ids={str(p):sha(p)for p in inputs}
    r={'schema':'iris.empirical_ELF_execution.v1','status':'running','pass':False,'started_at_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ELF_sha256':sha(elf),'fixture_sha256':sha(fixture),'argv':argv,'input_sha256':ids,'hardware_contacted':False,'normal_guest_exit_verified':False,'timeout_seconds':a.timeout,'capsule_native':m['binary_sha256']}
    def save():(out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
    save();start=time.monotonic();proc=None
    try:
        with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
            proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,start_new_session=True);r['pid']=proc.pid;save();timed=False
            try:code=proc.wait(timeout=a.timeout)
            except subprocess.TimeoutExpired:
                timed=True;os.killpg(proc.pid,signal.SIGTERM)
                try:code=proc.wait(timeout=.2)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
        for p,h in ids.items():
            if sha(p)!=h:raise ValueError('Bound input changed '+p)
        done=not timed and code==0;r.update(status='passed_guest_exit'if done else'failed_guest_exit',**{'pass':done},normal_guest_exit_verified=done,exit_status=code,timed_out=timed)
    finally:
        if proc is not None and proc.poll()is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        r['host_seconds']=time.monotonic()-start;r['output_sha256']={str(p):sha(p)for p in [out/n for n in('stdout','stderr','native-summary.json','features.jsonl')]if p.is_file()};save()
    print(json.dumps({k:r.get(k)for k in('pass','status','host_seconds','exit_status','timed_out')}))
if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--capsule',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--elf',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=900);main(p.parse_args())
