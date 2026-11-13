#!/usr/bin/env python3
"""Verify every frozen artifact and rebuild the independent transport consumer."""
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
    if out.exists():raise ValueError('fresh independent output required')
    source=cap/'report.json';j=json.loads(source.read_text());before=sha(source);count=0
    for item in j['artifacts']:
        q=cap/item['snapshot'];assert q.is_file()and sha(q)==item['sha256'],item['original'];assert stat.S_IMODE(q.stat().st_mode)==item['mode'];count+=1
    out.mkdir();start=time.monotonic();commands=[];tests=[]
    def snap(path):return cap/'snapshot'/str(Path(path).absolute()).lstrip('/')
    def run(argv,name,expected=0):
        commands.append(argv)
        with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:r=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=60)
        tests.append({'name':name,'exit_status':r.returncode,'expected':expected,'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))});assert r.returncode==expected,(name,r.returncode)
    serial=snap(j['SDK_path']);fased=snap(j['FASED_SDK_path']);runtime=next(Path(q).parent for q in j['checked_input_sha256']if q.endswith('/verilator/include/verilated.h'));compiler=Path('/usr/bin/g++');assert j['checked_input_sha256'][str(compiler)]==sha(compiler)
    run([str(compiler),'-O3','-std=c++20','-I'+str(serial),'-I'+str(fased),'-I'+str(snap(runtime)),str(snap(R/'timing/serial_memory_check.cpp')),str(serial/'libiris_serial_memory.a'),str(fased/'libiris_fased_service.a'),'-pthread','-latomic','-o',str(out/'check')],'compile')
    run([str(out/'check')],'four-bank-path');rows=[json.loads(line)for line in(out/'four-bank-path.stdout').read_text().splitlines()];assert rows==j['independent_path_checks']
    run([str(out/'check'),'--typed-guards'],'typed-guards');assert json.loads((out/'typed-guards.stdout').read_text())==j['typed_guard_checks']
    for name,arg in [('wrong-data','--wrong-data'),('active-invalid-opcode','--invalid-opcode'),('strict-first-reset-monitor','--source-always')]:run([str(out/'check'),arg],name,1)
    assert sha(source)==before
    report={'schema':'iris.serial_memory_capsule_independent_verify.v1','status':'passed','capsule_sha256':before,'artifacts_verified':count,'commands':commands,'tests':tests,'rebuilt_consumer_from_archived_source_and_SDKs':True,'source_path_checks':rows[-1],'typed_guards':j['typed_guard_checks'],'capsule_unchanged':True,'input_sha256':{str(q):sha(q)for q in [Path(__file__),source,compiler]},'host_seconds':time.monotonic()-start,'hardware_contacted':False,'source_image_association_verified':False,'calibration_usable':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':'passed','report_sha256':sha(out/'report.json'),'artifacts_verified':count,'checks':rows[-1]['checks']}))
if __name__=='__main__':main()
