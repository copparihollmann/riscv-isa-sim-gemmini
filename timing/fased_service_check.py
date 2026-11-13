#!/usr/bin/env python3
"""Independent accepted-transaction ledger vs exact archived LatencyPipe RTL."""
import argparse,hashlib,json,shlex,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build=a.build.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh output required')
    out.mkdir();receipt=json.loads((build/'build.json').read_text());assert receipt['exit_status']==0
    lib=build/'sdk/libiris_fased_service.a';assert sha(lib)==receipt['library_sha256']
    command=['/usr/bin/g++','-O3','-std=c++20','-MD','-MF',str(out/'test.d'),'-I'+str(build/'sdk'),'-I'+str(TOOL.parent.parent/'share/verilator/include'),str(R/'timing/fased_service_test.cpp'),str(lib),'-pthread','-latomic','-o',str(out/'fased-service-test')]
    start=time.monotonic();c=subprocess.run(command,text=True,capture_output=True);(out/'compile.stdout').write_text(c.stdout);(out/'compile.stderr').write_text(c.stderr)
    report={'schema':'iris.fased_latency_pipe_independent_checks.v1','source_identity':receipt['source_identity'],'input_sha256':{str(p):sha(p)for p in [Path(__file__),R/'timing/fased_service_test.cpp',build/'build.json',build/'sdk/fased_service.hpp',lib,Path('/usr/bin/g++')]},'compile_argv':command,'compile_exit_status':c.returncode,'hardware_contacted':False,'calibration_usable':False,'source_image_association_verified':False}
    if c.returncode==0:
        dependencies={Path(q)for q in shlex.split((out/'test.d').read_text().replace('\\\n',' ').split(':',1)[1])}
        report['compiled_dependency_sha256']={str(q):sha(q)for q in sorted(dependencies)if q.is_file()}
        linked=subprocess.check_output(['/usr/bin/ldd',str(out/'fased-service-test')],text=True);(out/'linked-runtime.txt').write_text(linked)
        report['host_runtime_sha256']={q:sha(q)for q in set(linked.split())if q.startswith('/')and Path(q).is_file()}
        cases=[]
        for name,args,expected in [('transaction-ledger',[],0),('wrong-latency-oracle',['--wrong-latency'],1)]:
            argv=[str(out/'fased-service-test'),*args];r=subprocess.run(argv,text=True,capture_output=True);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
            cases.append({'name':name,'argv':argv,'returncode':r.returncode,'expected_returncode':expected,'passed':r.returncode==expected,'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
        report.update(cases=cases,binary_sha256=sha(out/'fased-service-test'),status='passed'if all(x['passed']for x in cases)else'failed')
        if cases[0]['passed']:report['independent_ledger']=json.loads((out/'transaction-ledger.stdout').read_text())
    else:report['status']='compile_failed'
    report['host_seconds']=time.monotonic()-start;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in ['status','source_identity','independent_ledger','host_seconds']}));raise SystemExit(report['status']!='passed')
if __name__=='__main__':main()
