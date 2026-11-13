#!/usr/bin/env python3
"""Bind and qualify actual cache/NoC/L2/SerialTL/Bringup/FASED composition."""
import argparse,hashlib,json,shlex,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('fresh composition proof required')
    serial=R/'build/serial-memory-native-v4/sdk';fased=R/'build/fased-service-native-v3/sdk';memory=R/'build/memory-fabric-coupled-native-v4/sdk';context=R/'build/memory-fabric-context-sdk-v2'
    headers=[serial,fased,memory,context/'cache/sdk',context/'noc/sdk',context/'adapters/sdk'];libs=[memory/'libiris_memory_fabric.a',context/'cache/sdk/libiris_cache_hierarchy.a',context/'noc/sdk/libiris_noc.a',context/'adapters/sdk/libiris_memory_adapters.a',serial/'libiris_serial_memory.a',fased/'libiris_fased_service.a']
    capsules=[R/'build/memory-fabric-component-v1/report.json',R/'build/serial-memory-component-v1/report.json',R/'build/fased-service-component-v1/report.json'];checked={}
    for q in capsules:
        j=json.loads(q.read_text())
        for lib in libs:
            matches=[x for x in j['artifacts']if x['original']==str(lib)]
            if matches:assert sha(lib)==matches[0]['sha256'];checked[str(lib)]=matches[0]['sha256']
    assert len(checked)==len(libs)
    out.mkdir();start=time.monotonic();runtime=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
    command=['/usr/bin/g++','-O3','-std=c++20','-MD','-MF',str(out/'test.d'),*['-I'+str(q)for q in headers],'-I'+str(runtime),str(R/'timing/serial_memory_fabric_check.cpp'),*map(str,libs),'-pthread','-latomic','-o',str(out/'check')]
    with(out/'compile.stdout').open('w')as stdout,(out/'compile.stderr').open('w')as stderr:c=subprocess.run(command,stdout=stdout,stderr=stderr)
    report={'schema':'iris.source_memory_path_composition_checks.v1','compile_argv':command,'compile_exit_status':c.returncode,'input_sha256':{str(q):sha(q)for q in [Path(__file__),R/'timing/serial_memory_fabric_check.cpp',R/'timing/serial_memory_check.cpp',Path('/usr/bin/g++'),*capsules,*libs]},'exact_library_sha256':checked,'SDK_paths':list(map(str,headers)),'source_relative_periods':{'Rocket_and_Iris_uncore':2,'Bringup_and_FASED_target':1,'SerialTL':10},'model_edge_policy':'settle every component globally; hold preedge inputs; commit selected sourceclock peers; no handoff or fitted path delay','external_value_service':'explicit synthetic AXI64 backing actor; FASED timings30/30/16/16 are explicit fixture values','post_cork_synthetic_service_removed':True,'source_reset_diagnostic_policy':'positive serial fixture explicitly masks STOP/PRINTF only while both external resets asserted; SourceAlways default/negative preserved in serial capsule','CPU_source_scope':'actual Rocket Dcache/width/xbar/CDC +fullNoC+L2 +actual external path; CPU Hella/Icache producers are physical fixtures, not live CPU pipelines','hardware_contacted':False,'whole_soc_reference_compared':False,'source_image_association_verified':False,'timing_certified':False,'calibration_usable':False}
    if c.returncode==0:
        deps={Path(x)for x in shlex.split((out/'test.d').read_text().replace('\\\n',' ').split(':',1)[1])};report['compiled_dependency_sha256']={str(q):sha(q)for q in sorted(deps)if q.is_file()};cases=[]
        for name,args,expected,message in [('source-cache-through-serial',[],0,None),('wrong-functional-data',['--wrong-data'],1,'warm cache data mismatch'),('wrong-return-source',['--wrong-return-source'],1,'IRIS_COUPLED_RETURN_SOURCE_NOT_OWNED')]:
            argv=[str(out/'check'),*args]
            with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:r=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=60)
            text=(out/(name+'.stdout')).read_text()+(out/(name+'.stderr')).read_text();cases.append({'name':name,'argv':argv,'exit_status':r.returncode,'expected':expected,'passed':r.returncode==expected and(message is None or message in text),'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
        report.update(cases=cases,status='passed'if all(x['passed']for x in cases)else'failed',binary_sha256=sha(out/'check'))
        if cases[0]['passed']:report['source_runs']=[json.loads(line)for line in(out/'source-cache-through-serial.stdout').read_text().splitlines()]
        linked=subprocess.check_output(['/usr/bin/ldd',str(out/'check')],text=True);(out/'linked-runtime.txt').write_text(linked);report['host_runtime_sha256']={q:sha(q)for q in set(linked.split())if q.startswith('/')and Path(q).is_file()}
    else:report['status']='compile_failed'
    report['host_seconds']=time.monotonic()-start;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in ['status','host_seconds','source_runs']}));raise SystemExit(report['status']!='passed')
if __name__=='__main__':main()
