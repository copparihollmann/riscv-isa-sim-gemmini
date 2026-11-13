#!/usr/bin/env python3
"""Qualify source clocked serial path with independent transaction/value fixtures."""
import argparse,hashlib,json,shlex,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,default=R/'build/serial-memory-native-v4');p.add_argument('--fased',type=Path,default=R/'build/fased-service-native-v3');p.add_argument('--output',type=Path,required=True);a=p.parse_args();native=a.build.resolve();fased=a.fased.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh qualification output required')
    n=json.loads((native/'build.json').read_text());f=json.loads((fased/'build.json').read_text());assert n['exit_status']==f['exit_status']==0
    lib=native/'sdk/libiris_serial_memory.a';flib=fased/'sdk/libiris_fased_service.a';assert sha(lib)==n['library_sha256']and sha(flib)==f['library_sha256']
    assert sha(R/'timing/serial_memory.hpp')==sha(native/'sdk/serial_memory.hpp')
    runtime=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');out.mkdir();start=time.monotonic()
    argv=['/usr/bin/g++','-O3','-std=c++20','-MD','-MF',str(out/'test.d'),'-I'+str(native/'sdk'),'-I'+str(fased/'sdk'),'-I'+str(runtime),str(R/'timing/serial_memory_check.cpp'),str(lib),str(flib),'-pthread','-latomic','-o',str(out/'check')]
    with(out/'compile.stdout').open('w')as stdout,(out/'compile.stderr').open('w')as stderr:c=subprocess.run(argv,stdout=stdout,stderr=stderr)
    report={'schema':'iris.serial_memory_path_independent_checks.v1','compile_argv':argv,'compile_exit_status':c.returncode,'source_identity':n['source_identity'],'fased_source_identity':f['source_identity'],'input_sha256':{str(q):sha(q)for q in [Path(__file__),R/'timing/serial_memory_check.cpp',R/'timing/serial_memory.hpp',native/'build.json',lib,fased/'build.json',flib,Path('/usr/bin/g++')]},'source_clock_periods':[2,1,10],'component_fixture_parameters':{'readLatency':30,'writeLatency':30,'readMaxReqs':16,'writeMaxReqs':16,'provenance':'Explicit synthetic component test; not admitted observed hardware defaults.'},'reset_assertion_policy':'SourceAlways remains SDK default. Positive fixture explicitly suppresses diagnostic STOP_COND/PRINTF_COND only while both physical external resets are asserted; datapath/FIFOs/reset clocks unchanged, all active assertions enabled.','reset_FASED_input_policy':'Inactive zero metadata is supplied while both test resets are asserted; pre-reset raw pin values are not protocol observations.','hardware_contacted':False,'source_image_association_verified':False,'whole_soc_reference_compared':False,'calibration_usable':False,'timing_certified':False}
    if c.returncode==0:
        dependencies={Path(x)for x in shlex.split((out/'test.d').read_text().replace('\\\n',' ').split(':',1)[1])};report['compiled_dependency_sha256']={str(q):sha(q)for q in sorted(dependencies)if q.is_file()}
        cases=[]
        for name,args,expected,message in [('four-bank-data-and-clock',[],0,None),('typed-external-and-phase-guards',['--typed-guards'],0,None),('wrong-functional-data',['--wrong-data'],1,'transport value or byte address changed'),('active-invalid-opcode',['--invalid-opcode'],1,'Assertion failed'),('strict-first-reset-monitor',['--source-always'],1,'Assertion failed')]:
            command=[str(out/'check'),*args]
            with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:r=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=60)
            text=(out/(name+'.stdout')).read_text()+(out/(name+'.stderr')).read_text();cases.append({'name':name,'argv':command,'exit_status':r.returncode,'expected':expected,'passed':r.returncode==expected and(message is None or message in text),'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
        report.update(cases=cases,binary_sha256=sha(out/'check'),status='passed'if all(x['passed']for x in cases)else'failed')
        if cases[0]['passed']:report['source_path_runs']=[json.loads(line)for line in(out/'four-bank-data-and-clock.stdout').read_text().splitlines()]
        linked=subprocess.check_output(['/usr/bin/ldd',str(out/'check')],text=True);(out/'linked-runtime.txt').write_text(linked);report['host_runtime_sha256']={q:sha(q)for q in set(linked.split())if q.startswith('/')and Path(q).is_file()}
    else:report['status']='compile_failed'
    report['host_seconds']=time.monotonic()-start;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in ['status','source_identity','host_seconds']}));raise SystemExit(report['status']!='passed')
if __name__=='__main__':main()
