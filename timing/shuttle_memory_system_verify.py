#!/usr/bin/env python3
"""Independently compile archived sources against archived three-hart SDKs."""
import argparse,hashlib,json,stat,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--capsule',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();cap=a.capsule.resolve();out=a.output.resolve()
 if out.exists():raise ValueError('fresh verification required')
 manifest=cap/'report.json';before=sha(manifest);j=json.loads(manifest.read_text());assert j['status']=='passed_source_physical_component';mapping={x['original']:cap/x['snapshot']for x in j['artifacts']}
 for x in j['artifacts']:
  q=cap/x['snapshot'];assert sha(q)==x['sha256']and stat.S_IMODE(q.stat().st_mode)==x['mode'],x['original']
 for x in j['parent_closures']:assert sha(Path(x['capsule'])/'report.json')==x['report_sha256']
 def snap(x):return mapping[str(Path(x).absolute())]
 out.mkdir();start=time.monotonic();commands=[];cases=[]
 def run(cmd,label,expected=0,error=None):
  commands.append(cmd)
  with(out/(label+'.stdout')).open('w')as stdout,(out/(label+'.stderr')).open('w')as stderr:rc=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=180).returncode
  assert rc==expected,(label,rc)
  if error:assert error in(out/(label+'.stderr')).read_text(),label
  cases.append({'name':label,'exit_status':rc,'stdout_sha256':sha(out/(label+'.stdout')),'stderr_sha256':sha(out/(label+'.stderr'))})
 runtime=next(Path(x).parent for x in j['checked_input_sha256']if x.endswith('/verilator/include/verilated.h'));includes=[*[cap/'snapshot'/str(Path(x).absolute()).lstrip('/')for x in j['required_include_directories']],cap/'snapshot'/str(runtime).lstrip('/'),cap/'snapshot'/str(Path(j['FASED_SDK_path'])).lstrip('/')];libs=[snap(x)for x in j['required_static_libraries_in_link_order']]+[snap(Path(j['FASED_SDK_path'])/'libiris_fased_service.a')]
 for mode,suffix in [('functional','check'),('context','context_check'),('guards','guards')]:
  source=snap(R/('timing/shuttle_memory_system_'+suffix+'.cpp'));exe=out/mode
  run(['/usr/bin/g++','-O2','-std=c++20',*['-I'+str(x)for x in includes],str(source),'-Wl,--start-group',*map(str,libs),'-Wl,--end-group','-pthread','-o',str(exe)],'compile-'+mode)
  run([str(exe)],mode);rows=[json.loads(x)for x in(out/(mode+'.stdout')).read_text().splitlines()];assert rows==j['source_checks'][mode],mode
  if mode=='functional':
   for item in j['negative_controls']:run([str(exe),item['mode']],item['mode'][2:],1,item['required_error'])
 assert sha(manifest)==before
 report={'schema':'iris.three_hart_source_memory_system_independent_verify.v1','status':'passed','capsule_sha256':before,'artifacts_verified':len(mapping),'parent_manifests_verified':len(j['parent_closures']),'archived_sources_headers_and_libraries_recompiled':True,'source_checks':j['source_checks'],'argv':commands,'cases':cases,'input_sha256':{str(x):sha(x)for x in [Path(__file__),manifest,Path('/usr/bin/g++')]},'host_seconds':time.monotonic()-start,'capsule_unchanged':True,'hardware_contacted':False,'timing_certified':False,'calibration_usable':False}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'artifacts_verified':len(mapping),'status':'passed'}))
if __name__=='__main__':main()
