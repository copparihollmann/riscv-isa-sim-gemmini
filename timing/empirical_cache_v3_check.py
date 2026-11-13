#!/usr/bin/env python3
import argparse,hashlib,json,pathlib,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',default='build/empirical-cache-v3');args=a.parse_args();out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
 sources=['timing/empirical_cache.hpp','timing/empirical_cache_test.cpp','timing/empirical_cache_v2.hpp','timing/empirical_cache_v2_test.cpp','timing/empirical_cache_v3.hpp','timing/empirical_cache_v3.cpp','timing/empirical_cache_v3_test.cpp','timing/empirical_cache_v3_check.py','timing/empirical_cache_v3_README.md','hardware/manifest.json'];data=out/'data-regression.cpp';data.write_text((ROOT/'timing/empirical_cache_test.cpp').read_text().replace('"empirical_cache.hpp"','"empirical_cache_v3.hpp"').replace('CacheHistory','CacheHistoryV3').replace('iris_geometry()','iris_geometry_v3()'));inst=out/'instruction-regression.cpp';inst.write_text((ROOT/'timing/empirical_cache_v2_test.cpp').read_text().replace('empirical_cache_v2.hpp','empirical_cache_v3.hpp').replace('CacheHistoryV2','CacheHistoryV3').replace('iris_geometry_v2','iris_geometry_v3'));runs=[]
 for mode,flags in [('optimized',['-O2']),('debug_bounds',['-O0','-g','-D_GLIBCXX_DEBUG','-D_GLIBCXX_ASSERTIONS'])]:
  for label,test in [('data',data),('instruction',inst),('query',ROOT/'timing/empirical_cache_v3_test.cpp')]:
   tag=mode+'-'+label;binary=out/tag;argv=['c++','-std=c++20',*flags,'-Wall','-Wextra','-Werror','-I'+str(ROOT/'timing'),str(ROOT/'timing/empirical_cache_v3.cpp'),str(test),'-o',str(binary)];t=time.monotonic();r=subprocess.run(argv,text=True,capture_output=True);(out/(tag+'-compile.stdout')).write_text(r.stdout);(out/(tag+'-compile.stderr')).write_text(r.stderr)
   if r.returncode:raise SystemExit(r.stderr)
   r=subprocess.run([str(binary)],text=True,capture_output=True);(out/(tag+'.stdout')).write_text(r.stdout);(out/(tag+'.stderr')).write_text(r.stderr)
   if r.returncode:raise SystemExit(r.stderr)
   result=json.loads(r.stdout);assert result['status']=='passed';runs.append({'name':tag,'compile_argv':argv,'exit_status':0,'result':result,'host_seconds':time.monotonic()-t,'binary_sha256':sha(binary),'stdout_sha256':sha(out/(tag+'.stdout')),'stderr_sha256':sha(out/(tag+'.stderr'))})
 report={'schema':'iris.empirical_cache_query_component.v1','status':'passed','inputs_sha256':{s:sha(ROOT/s) for s in sources},'derived_sources_sha256':{p.name:sha(p) for p in [data,inst]},'runs':runs,'query_nonmutating':True,'query_is_prediction_not_reservation':True,'functional_data_or_knownness_supplied':False,'actual_hardware_state_inputs':False,'timing_parameters_supplied':False,'source_image_association_verified':False,'full_2pct_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'report':str(out/'report.json'),'sha256':sha(out/'report.json'),'checks_per_variant':160100,'build_variants':2},indent=2))
if __name__=='__main__':main()
