#!/usr/bin/env python3
"""Verify an immutable FASED capsule and rebuild its independent consumer only."""
import argparse,hashlib,json,stat,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--capsule',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();cap=a.capsule.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh verification output required')
    report=json.loads((cap/'report.json').read_text());before=sha(cap/'report.json');count=0
    for item in report['artifacts']:
        path=cap/item['snapshot'];assert path.is_file()and sha(path)==item['sha256'],item['original'];assert stat.S_IMODE(path.stat().st_mode)==item['mode'];count+=1
    out.mkdir();start=time.monotonic();commands=[];tests=[]
    def snap(path):return cap/'snapshot'/str(Path(path).absolute()).lstrip('/')
    def run(argv,name,expected=0):
        commands.append(argv)
        with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:r=subprocess.run(argv,stdout=stdout,stderr=stderr)
        tests.append({'name':name,'argv':argv,'exit_status':r.returncode,'expected':expected,'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))});assert r.returncode==expected,(name,r.returncode)
    sdk=snap(report['SDK_path']);runtime=next(Path(q)for q in report['checked_input_sha256']if q.endswith('/verilator/include/verilated.h')).parent
    cpp=snap(R/'timing/fased_service_test.cpp');compiler=Path('/usr/bin/g++');assert report['checked_input_sha256'][str(compiler)]==sha(compiler)
    run([str(compiler),'-O3','-std=c++20','-I'+str(sdk),'-I'+str(snap(runtime)),str(cpp),str(sdk/'libiris_fased_service.a'),'-pthread','-latomic','-o',str(out/'fased-service-test')],'compile')
    run([str(out/'fased-service-test')],'transaction-ledger');positive=json.loads((out/'transaction-ledger.stdout').read_text());assert positive==report['independent_transaction_ledger']
    run([str(out/'fased-service-test'),'--wrong-latency'],'wrong-latency',1)
    original_clock=R/'build/fased-service-clock-check-v1/clock-test';run([str(snap(original_clock))],'clock-calendar');clock=json.loads((out/'clock-calendar.stdout').read_text());assert clock==report['independent_clock_calendar']
    run([str(snap(original_clock)),'--wrong-period'],'wrong-period',1)
    assert sha(cap/'report.json')==before
    result={'schema':'iris.fased_capsule_independent_verify.v1','status':'passed','capsule_sha256':before,'artifacts_verified':count,'commands':commands,'tests':tests,'rebuilt_consumer_from_archived_source_and_SDK':True,'transaction_ledger':positive,'clock_calendar':clock,'capsule_unchanged':True,'input_sha256':{str(q):sha(q)for q in [Path(__file__),cap/'report.json',compiler]},'host_seconds':time.monotonic()-start,'hardware_contacted':False,'default_full_service_available':False,'timing_certified':False,'calibration_usable':False}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'passed','report_sha256':sha(out/'report.json'),'artifacts_verified':count,'checks':positive['checks']}))
if __name__=='__main__':main()
