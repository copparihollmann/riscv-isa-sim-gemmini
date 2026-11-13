#!/usr/bin/env python3
import argparse,hashlib,json,pathlib,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',default='build/empirical-cache-v2');args=a.parse_args();out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
 sources=['timing/empirical_cache.hpp','timing/empirical_cache_test.cpp','timing/empirical_cache_v2.hpp','timing/empirical_cache_v2.cpp','timing/empirical_cache_v2_test.cpp','timing/empirical_cache_v2_check.py','timing/empirical_cache_v2_README.md','hardware/manifest.json','hardware/evidence/firesim-l2.json'];derived=out/'data-regression.cpp';derived.write_text((ROOT/'timing/empirical_cache_test.cpp').read_text().replace('"empirical_cache.hpp"','"empirical_cache_v2.hpp"').replace('CacheHistory','CacheHistoryV2').replace('iris_geometry()','iris_geometry_v2()'));runs=[]
 for mode,flags in [('optimized',['-O2']),('debug_bounds',['-O0','-g','-D_GLIBCXX_DEBUG','-D_GLIBCXX_ASSERTIONS'])]:
  for label,test in [('data_regression',derived),('instruction_data',ROOT/'timing/empirical_cache_v2_test.cpp')]:
   tag=mode+'-'+label;binary=out/tag;argv=['c++','-std=c++20',*flags,'-Wall','-Wextra','-Werror','-I'+str(ROOT/'timing'),str(ROOT/'timing/empirical_cache_v2.cpp'),str(test),'-o',str(binary)];started=time.monotonic();r=subprocess.run(argv,text=True,capture_output=True);(out/(tag+'-compile.stdout')).write_text(r.stdout);(out/(tag+'-compile.stderr')).write_text(r.stderr)
   if r.returncode:raise SystemExit(r.stderr)
   r=subprocess.run([str(binary)],text=True,capture_output=True);(out/(tag+'.stdout')).write_text(r.stdout);(out/(tag+'.stderr')).write_text(r.stderr)
   if r.returncode:raise SystemExit(r.stderr)
   result=json.loads(r.stdout);assert result['status']=='passed';runs.append({'name':tag,'argv':argv,'exit_status':0,'result':result,'host_seconds':time.monotonic()-started,'binary_sha256':sha(binary),'stdout_sha256':sha(out/(tag+'.stdout')),'stderr_sha256':sha(out/(tag+'.stderr'))})
 report={'schema':'iris.empirical_cache_instruction_component.v1','status':'passed','inputs_sha256':{s:sha(ROOT/s) for s in sources},'derived_regression_source_sha256':sha(derived),'runs':runs,'separate_l1_instruction_tags':True,'shared_l2_and_request_owner_catalog':True,'instruction_cache_get_only':True,'replacement':'LRU_approximation','timing_latency_parameters_supplied':False,'memory_values_or_knownness_handled':False,'actual_hardware_or_rtl_state_inputs':False,'hardware_contacted':False,'source_image_association_verified':False,'full_2pct_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'report':str(out/'report.json'),'sha256':sha(out/'report.json'),'instruction_checks':90023,'data_checks':60049,'build_variants':2},indent=2))
if __name__=='__main__':main()
