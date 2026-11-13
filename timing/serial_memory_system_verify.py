#!/usr/bin/env python3
"""Verify the composed closure and rebuild/run its public API from archived files."""
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
    j=json.loads((cap/'report.json').read_text());before=sha(cap/'report.json');count=0
    for item in j['artifacts']:
        q=cap/item['snapshot'];assert q.is_file()and sha(q)==item['sha256'],item['original'];assert stat.S_IMODE(q.stat().st_mode)==item['mode'];count+=1
    for parent in j['hash_bound_child_source_closures']:assert sha(Path(parent['capsule'])/'report.json')==parent['report_sha256']
    out.mkdir();start=time.monotonic();commands=[];tests=[]
    def snap(path):return cap/'snapshot'/str(Path(path).absolute()).lstrip('/')
    def run(argv,name,expected=0):
        commands.append(argv)
        with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:r=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=60)
        tests.append({'name':name,'exit_status':r.returncode,'expected':expected,'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))});assert r.returncode==expected,(name,r.returncode)
    sys=snap(j['System_SDK_path']);fased=snap(j['FASED_SDK_path']);includes=[sys,*[snap(q)for q in j['required_include_directories']],fased];runtime=next(Path(q).parent for q in j['checked_input_sha256']if q.endswith('/verilator/include/verilated.h'));compiler=Path('/usr/bin/g++');assert sha(compiler)==j['checked_input_sha256'][str(compiler)]
    libs=[sys/'libiris_serial_memory_system.a',*[snap(q)for q in j['child_library_link_order']],fased/'libiris_fased_service.a']
    run([str(compiler),'-O3','-std=c++20',*['-I'+str(q)for q in includes],'-I'+str(snap(runtime)),str(snap(R/'timing/serial_memory_system_check.cpp')),*map(str,libs),'-pthread','-latomic','-o',str(out/'check')],'compile-public')
    run([str(out/'check')],'public-system');rows=[json.loads(line)for line in(out/'public-system.stdout').read_text().splitlines()];assert rows==j['public_system_checks']
    run([str(out/'check'),'--wrong-data'],'wrong-data',1);assert 'warm source data mismatch'in(out/'wrong-data.stderr').read_text()
    run([str(out/'check'),'--schema'],'schema');assert sha(out/'schema.stdout')==j['physical_schema_sha256']
    run([str(snap(R/'build/serial-memory-context-check-v4/fixed'))],'constructor-cleanup');assert json.loads((out/'constructor-cleanup.stdout').read_text())==j['context_failure_cleanup']
    run([str(snap(R/'build/serial-memory-context-check-v4/historical'))],'historical-cleanup',1)
    assert sha(cap/'report.json')==before
    report={'schema':'iris.composed_source_memory_system_independent_verify.v1','status':'passed','capsule_sha256':before,'artifacts_verified':count,'bound_parent_manifests_verified':len(j['hash_bound_child_source_closures']),'commands':commands,'tests':tests,'rebuilt_public_consumer_from_archived_headers_source_libraries':True,'public_checks':rows[-1],'context_cleanup':j['context_failure_cleanup'],'capsule_unchanged':True,'input_sha256':{str(q):sha(q)for q in [Path(__file__),cap/'report.json',compiler]},'host_seconds':time.monotonic()-start,'hardware_contacted':False,'source_image_association_verified':False,'calibration_usable':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':'passed','report_sha256':sha(out/'report.json'),'artifacts_verified':count,'checks':rows[-1]['checks']}))
if __name__=='__main__':main()
