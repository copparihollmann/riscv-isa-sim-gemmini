#!/usr/bin/env python3
import argparse,hashlib,json,pathlib,shutil,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',default='build/empirical-cache-v1');args=a.parse_args();out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
 inputs=['timing/empirical_cache.hpp','timing/empirical_cache.cpp','timing/empirical_cache_test.cpp','timing/empirical_cache_check.py','timing/empirical_cache_README.md','hardware/manifest.json','hardware/evidence/firesim-l2.json'];runs=[]
 for name,flags in [('optimized',['-O2']),('debug_bounds',['-O0','-g','-D_GLIBCXX_DEBUG','-D_GLIBCXX_ASSERTIONS'])]:
  binary=out/('test-'+name);argv=['c++','-std=c++20',*flags,'-Wall','-Wextra','-Werror',str(ROOT/'timing/empirical_cache.cpp'),str(ROOT/'timing/empirical_cache_test.cpp'),'-o',str(binary)];start=time.monotonic();compile=subprocess.run(argv,text=True,capture_output=True);(out/(name+'-compile.stdout')).write_text(compile.stdout);(out/(name+'-compile.stderr')).write_text(compile.stderr)
  if compile.returncode:raise SystemExit(compile.stderr)
  r=subprocess.run([str(binary)],text=True,capture_output=True);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
  if r.returncode:raise SystemExit(r.stderr)
  payload=json.loads(r.stdout);assert payload['status']=='passed';runs.append({'name':name,'compile_argv':argv,'exit_status':r.returncode,'host_seconds':time.monotonic()-start,'result':payload,'binary_sha256':sha(binary),'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
 report={'schema':'iris.empirical_cache_component.v1','status':'passed','input_sha256':{p:sha(ROOT/p) for p in inputs},'compiler':subprocess.check_output(['c++','--version'],text=True).splitlines()[0],'runs':runs,'strict_owner_dependencies':True,'actual_hardware_or_rtl_state_inputs':False,'hardware_contacted':False,'full_2pct_certified':False,'source_image_association_verified':False,'unavailable_checks':[{'kind':'address_undefined_sanitizer','reason':'Hostlinker libasan.so.6.0.0 unavailable; preserved sanitized-compile.stderr; no sanitizer pass claim.'}],'replacement_policy':'LRU_approximation','tag_update_phase':'accepted_intent_only_pending_owners_retained'};(out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'report':str(out/'report.json'),'sha256':sha(out/'report.json'),'checks_per_build':runs[0]['result']['checks']},indent=2))
if __name__=='__main__':main()
