#!/usr/bin/env python3
"""Prove new host context cleanup and preserve rejecting historical controls."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];V=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--derivative',type=Path,default=R/'build/serial-memory-context-sdk-v1');p.add_argument('--output',type=Path,required=True);a=p.parse_args();der=a.derivative.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh host context proof required')
    out.mkdir();start=time.monotonic();meta=json.loads((der/'report.json').read_text());commands=[];cases=[]
    for kind in ['fixed','historical']:
        serial=der/'serial/sdk'if kind=='fixed'else R/'build/serial-memory-native-v4/sdk';fased=der/'fased/sdk'if kind=='fixed'else R/'build/fased-service-native-v3/sdk'
        command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(serial),'-I'+str(fased),'-I'+str(V),str(R/'timing/serial_memory_context_check.cpp'),str(serial/'libiris_serial_memory.a'),str(fased/'libiris_fased_service.a'),'-pthread','-latomic','-o',str(out/kind)];commands.append(command)
        with(out/(kind+'.compile.stdout')).open('w')as stdout,(out/(kind+'.compile.stderr')).open('w')as stderr:c=subprocess.run(command,stdout=stdout,stderr=stderr)
        assert c.returncode==0,kind
    for name,kind,args,expected,message in [('complete-fixed-lifecycle','fixed',[],0,None),('historical-complete-cleanup','historical',[],1,'serial_move_assignment_context_leak'),('historical-serial-constructor-unwind','historical',['--serial-constructor-only'],1,'serial_constructor_unwind_context_leak'),('historical-fased-constructor-unwind','historical',['--fased-constructor-only'],1,'fased_constructor_unwind_context_leak')]:
        command=[str(out/kind),*args];commands.append(command)
        with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:r=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=60)
        text=(out/(name+'.stdout')).read_text()+(out/(name+'.stderr')).read_text();cases.append({'name':name,'argv':command,'exit_status':r.returncode,'expected':expected,'passed':r.returncode==expected and(message is None or message in text),'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
    inputs=[Path(__file__),R/'timing/serial_memory_context_check.cpp',der/'report.json',Path('/usr/bin/g++'),V/'verilated.cpp']+[der/name/'sdk'/lib for name,lib in [('serial','libiris_serial_memory.a'),('fased','libiris_fased_service.a')]]+[R/'build/serial-memory-native-v4/sdk/libiris_serial_memory.a',R/'build/fased-service-native-v3/sdk/libiris_fased_service.a',R/'build/serial-memory-native-v4/sdk/serial_memory.hpp',R/'build/fased-service-native-v3/sdk/fased_service.hpp']
    report={'schema':'iris.external_memory_host_context_checks.v1','status':'passed'if all(x['passed']for x in cases)else'failed','cases':cases,'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},'unchanged_RTL_objects':{k:len(v['unchanged_object_sha256'])for k,v in meta['components'].items()},'host_seconds':time.monotonic()-start,'hardware_contacted':False,'source_timing_logic_changed':False,'calibration_usable':False}
    if cases[0]['passed']:report['lifecycle']=json.loads((out/'complete-fixed-lifecycle.stdout').read_text())
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in ['status','lifecycle','host_seconds']}));raise SystemExit(report['status']!='passed')
if __name__=='__main__':main()
