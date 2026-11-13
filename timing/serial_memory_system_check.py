#!/usr/bin/env python3
"""Check the public composed API with an explicit independent AXI read actor."""
import argparse,hashlib,json,shlex,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,default=R/'build/serial-memory-system-native-v2');p.add_argument('--fased-sdk',type=Path,default=R/'build/serial-memory-context-sdk-v2/fased/sdk');p.add_argument('--output',type=Path,required=True);a=p.parse_args();native=a.build.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh public API proof required')
    meta=json.loads((native/'build.json').read_text());assert meta['exit_status']==0
    fased=a.fased_sdk.resolve();libs=[native/'sdk/libiris_serial_memory_system.a',*[Path(q)for q in meta['required_static_libraries_in_link_order']],fased/'libiris_fased_service.a']
    assert sha(libs[0])==meta['library_sha256']
    for q,digest in meta['required_child_library_sha256'].items():assert sha(q)==digest
    headers=[native/'sdk',*[Path(q)for q in meta['required_include_directories']],fased];out.mkdir();start=time.monotonic();runtime=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
    command=['/usr/bin/g++','-O3','-std=c++20','-MD','-MF',str(out/'test.d'),*['-I'+str(q)for q in headers],'-I'+str(runtime),str(R/'timing/serial_memory_system_check.cpp'),*map(str,libs),'-pthread','-latomic','-o',str(out/'check')]
    with(out/'compile.stdout').open('w')as stdout,(out/'compile.stderr').open('w')as stderr:c=subprocess.run(command,stdout=stdout,stderr=stderr)
    report={'schema':'iris.public_source_memory_system_checks.v1','compile_argv':command,'compile_exit_status':c.returncode,'source_identity':meta['source_identity'],'input_sha256':{str(q):sha(q)for q in [Path(__file__),R/'timing/serial_memory_system_check.cpp',native/'build.json',Path('/usr/bin/g++'),*libs]},'include_directories':list(map(str,headers)),'source_clock_periods':[2,2,1,10],'source_relative_calendar_only':True,'explicit_component_fixture_parameters':{'readLatency':30,'writeLatency':30,'readMaxReqs':16,'writeMaxReqs':16},'external_AXI_actor':'independent read-only address pattern; unexpected outer writes refuse; data corruption negative','reset_assertion_policy':'explicit serial SuppressOnlyWhileBothExternalResets; SourceAlways remains default','no_FASED_latency_or_backing_in_public_SDK':True,'CPU_Hella_and_Icache_are_external_fixtures':True,'source_elaborations':meta['source_elaborations'],'hardware_contacted':False,'source_image_association_verified':False,'calibration_usable':False,'timing_certified':False}
    if c.returncode==0:
        deps={Path(x)for x in shlex.split((out/'test.d').read_text().replace('\\\n',' ').split(':',1)[1])};report['compiled_dependency_sha256']={str(q):sha(q)for q in sorted(deps)if q.is_file()};cases=[]
        for name,args,expected,message in [('public-system-and-guards',[],0,None),('wrong-external-data',['--wrong-data'],1,'warm source data mismatch'),('physical-port-schema',['--schema'],0,None)]:
            argv=[str(out/'check'),*args]
            with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:r=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=60)
            text=(out/(name+'.stdout')).read_text()+(out/(name+'.stderr')).read_text();cases.append({'name':name,'argv':argv,'exit_status':r.returncode,'expected':expected,'passed':r.returncode==expected and(message is None or message in text),'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
        report.update(cases=cases,status='passed'if all(x['passed']for x in cases)else'failed',binary_sha256=sha(out/'check'))
        if cases[0]['passed']:report['source_runs']=[json.loads(line)for line in(out/'public-system-and-guards.stdout').read_text().splitlines()]
        if cases[-1]['passed']:
            schema=json.loads((out/'physical-port-schema.stdout').read_text());assert schema['source_identity']==meta['source_identity'];assert all(len({x['name']for x in schema[key]})==len(schema[key])for key in ['inputs','outputs']);report['physical_schema_sha256']=sha(out/'physical-port-schema.stdout');report['physical_ports']={key:len(schema[key])for key in ['inputs','outputs']}
        linked=subprocess.check_output(['/usr/bin/ldd',str(out/'check')],text=True);(out/'linked-runtime.txt').write_text(linked);report['host_runtime_sha256']={q:sha(q)for q in set(linked.split())if q.startswith('/')and Path(q).is_file()}
    else:report['status']='compile_failed'
    report['host_seconds']=time.monotonic()-start;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in ['status','source_identity','source_runs','host_seconds']}));raise SystemExit(report['status']!='passed')
if __name__=='__main__':main()
