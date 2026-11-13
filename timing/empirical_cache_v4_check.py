#!/usr/bin/env python3
import argparse,hashlib,json,pathlib,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',default='build/empirical-cache-v4');args=a.parse_args();out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
 sources=['timing/empirical_cache.hpp','timing/empirical_cache_test.cpp','timing/empirical_cache_v2.hpp','timing/empirical_cache_v2_test.cpp','timing/empirical_cache_v3.hpp','timing/empirical_cache_v3_test.cpp','timing/empirical_cache_v4.hpp','timing/empirical_cache_v4.cpp','timing/empirical_cache_v4_test.cpp','timing/empirical_cache_v4_check.py','timing/empirical_cache_v4_README.md','hardware/manifest.json'];derived=[]
 for v,label,src in [('', 'data','timing/empirical_cache_test.cpp'),('_v2','instruction','timing/empirical_cache_v2_test.cpp'),('_v3','query','timing/empirical_cache_v3_test.cpp')]:
  text=(ROOT/src).read_text().replace('empirical_cache'+v+'.hpp','empirical_cache_v4.hpp').replace('CacheHistory'+('V'+v[-1] if v else ''),'CacheHistoryV4').replace('iris_geometry'+v+'()','iris_geometry_v4()');p=out/(label+'-regression.cpp');p.write_text(text);derived.append((label,p))
 runs=[]
 for mode,flags in [('optimized',['-O2']),('debug_bounds',['-O0','-g','-D_GLIBCXX_DEBUG','-D_GLIBCXX_ASSERTIONS'])]:
  for label,test in [*derived,('vector',ROOT/'timing/empirical_cache_v4_test.cpp')]:
   tag=mode+'-'+label;binary=out/tag;argv=['c++','-std=c++20',*flags,'-Wall','-Wextra','-Werror','-I'+str(ROOT/'timing'),str(ROOT/'timing/empirical_cache_v4.cpp'),str(test),'-o',str(binary)];started=time.monotonic();r=subprocess.run(argv,text=True,capture_output=True);(out/(tag+'-compile.stdout')).write_text(r.stdout);(out/(tag+'-compile.stderr')).write_text(r.stderr)
   if r.returncode:raise SystemExit(r.stderr)
   r=subprocess.run([str(binary)],text=True,capture_output=True);(out/(tag+'.stdout')).write_text(r.stdout);(out/(tag+'.stderr')).write_text(r.stderr)
   if r.returncode:raise SystemExit(r.stderr)
   result=json.loads(r.stdout);assert result['status']=='passed';runs.append({'name':tag,'compile_argv':argv,'exit_status':0,'result':result,'host_seconds':time.monotonic()-started,'binary_sha256':sha(binary),'stdout_sha256':sha(out/(tag+'.stdout')),'stderr_sha256':sha(out/(tag+'.stderr'))})
 report={'schema':'iris.empirical_vector_cache_bypass_component.v1','status':'passed','inputs_sha256':{s:sha(ROOT/s) for s in sources},'derived_sources_sha256':{p.name:sha(p) for _,p in derived},'runs':runs,'vector_l1d_bypass':True,'scalar_and_vector_pending_owners_shared':True,'get_only_icache_unchanged':True,'timing_parameters_supplied':False,'functional_bytes_or_definedness_supplied':False,'actual_hardware_state_inputs':False,'source_image_association_verified':False,'full_2pct_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'report':str(out/'report.json'),'sha256':sha(out/'report.json'),'checks_per_variant':200118,'build_variants':2},indent=2))
if __name__=='__main__':main()
