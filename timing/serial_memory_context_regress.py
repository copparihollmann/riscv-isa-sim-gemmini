#!/usr/bin/env python3
"""Replay independent frozen component tests on host-only fixed-context archives."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];V=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--derivative',type=Path,default=R/'build/serial-memory-context-sdk-v2');p.add_argument('--output',type=Path,required=True);a=p.parse_args();d=a.derivative.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh regression evidence required')
    source=json.loads((d/'report.json').read_text());serial=d/'serial/sdk';fased=d/'fased/sdk';out.mkdir();start=time.monotonic();commands=[];cases=[]
    for kind,cpp,libs in [('latency','fased_service_test.cpp',[fased/'libiris_fased_service.a']),('serial','serial_memory_check.cpp',[serial/'libiris_serial_memory.a',fased/'libiris_fased_service.a'])]:
        command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(serial),'-I'+str(fased),'-I'+str(V),str(R/'timing'/cpp),*map(str,libs),'-pthread','-latomic','-o',str(out/kind)];commands.append(command)
        with(out/(kind+'.compile.stdout')).open('w')as stdout,(out/(kind+'.compile.stderr')).open('w')as stderr:c=subprocess.run(command,stdout=stdout,stderr=stderr)
        assert c.returncode==0,kind
    for name,kind,args,expected,message in [('latency-independent-ledger','latency',[],0,None),('latency-wrong-oracle','latency',['--wrong-latency'],1,'egressReq_r_valid'),('serial-four-bank','serial',[],0,None),('serial-typed-guards','serial',['--typed-guards'],0,None),('serial-corrupt-data','serial',['--wrong-data'],1,'transport value or byte address changed'),('serial-active-invalid-opcode','serial',['--invalid-opcode'],1,'Assertion failed'),('serial-strict-reset','serial',['--source-always'],1,'Assertion failed')]:
        command=[str(out/kind),*args];commands.append(command);t=time.monotonic()
        with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:r=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=60)
        text=(out/(name+'.stdout')).read_text()+(out/(name+'.stderr')).read_text();cases.append({'name':name,'argv':command,'exit_status':r.returncode,'expected':expected,'passed':r.returncode==expected and(message is None or message in text),'execution_host_seconds':time.monotonic()-t,'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
    latency=json.loads((out/'latency-independent-ledger.stdout').read_text());serial_rows=[json.loads(line)for line in(out/'serial-four-bank.stdout').read_text().splitlines()]
    original_l=json.loads((R/'build/fased-service-check-v8/report.json').read_text())['independent_ledger'];original_s=json.loads((R/'build/serial-memory-check-v5/report.json').read_text())['source_path_runs'];assert latency==original_l and serial_rows==original_s
    report={'schema':'iris.fixed_context_component_regressions.v1','status':'passed'if all(x['passed']for x in cases)else'failed','cases':cases,'argv':commands,'latency_ledger':latency,'serial_rows':serial_rows,'byte_identical_qualified_semantic_output':True,'input_sha256':{str(p):sha(p)for p in [Path(__file__),R/'timing/fased_service_test.cpp',R/'timing/serial_memory_check.cpp',d/'report.json',R/'build/fased-service-check-v8/report.json',R/'build/serial-memory-check-v5/report.json',serial/'libiris_serial_memory.a',fased/'libiris_fased_service.a',Path('/usr/bin/g++')]},'unchanged_RTL_model_runtime_objects':{k:len(v['unchanged_object_sha256'])for k,v in source['components'].items()},'host_seconds':time.monotonic()-start,'hardware_contacted':False,'source_RTL_or_timing_logic_changed':False,'calibration_usable':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'latency_checks':latency['checks'],'serial_checks':serial_rows[-1]['checks'],'host_seconds':report['host_seconds']}));raise SystemExit(report['status']!='passed')
if __name__=='__main__':main()
