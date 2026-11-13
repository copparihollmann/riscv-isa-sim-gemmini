#!/usr/bin/env python3
"""Select only explicitly mapped positive costs for the corrected131c pilot.
The immutable raw fit is retained; unsupported mappings remain unapplied.
"""
import hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,x):pathlib.Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def main():
 out=ROOT/'calibration/empirical-131c-runtime-v2';out.mkdir(parents=True,exist_ok=True);base=ROOT/'build/empirical-training-corrected-pilot-v1/fast.fixture';rawp=ROOT/'calibration/empirical-corrected-shared-v1/parameters.json';raw=json.load(rawp.open());identity='iris-empirical-131c-pilot-v2';lines=base.read_text().splitlines();lines=['purpose uncalibrated-integration-fixture' if x.startswith('purpose ') else 'source actual-FPGA6750-training-prefix-positive-fit-no-full-certificate' if x.startswith('source ') else 'empirical_profile experimental-effective-services '+identity+' bounded' if x.startswith('empirical_profile ') else x for x in lines];applied=[];unapplied=[];paramsha=sha(rawp)
 for h in range(3):
  c='shuttle' if h<2 else 'rocket';m=raw['models'][c];v=m['coefficients'];read=v.get('cache.DRAM.reads',0);write=v.get('cache.DRAM.writes',0);l1=v.get('cache.DRAM.l1misses',0);outer=v.get('cache.DRAM.l2misses',0);dirty=v.get('cache.DRAM.dirtywritebacks',0)
  lines.append('empirical_cache_service %d %.12g %.12g %.12g %.12g 448 %.12g PARTIAL_LIVE_PILOT %s core_cycles'%(h,read,write,l1,outer,dirty,paramsha));applied.append({'hart':h,'kind':'shared_instruction_data_cache_service','read_base':read,'write_base':write,'l1miss':l1,'outermiss':outer,'dirty_extra':dirty,'outer_interval':448,'outer_interval_status':'separate_training_aggregate_candidate_not_latency_identified','writeback_reservation_policy':'extra_latency_only_no_additional448reservation','scope':'Sourcegeometry/LRUapproximation; vectorrouteunqualifiedin131c.'})
  tcm=v.get('memory.LOCAL_TCM.accesses')
  if tcm is not None and m['individually_identifiable'].get('memory.LOCAL_TCM.accesses'):
   resource='empirical.tcm'+str(h);lines.append('resource '+resource+' 1')
   for direction in ('load','store'):
    lines.append('empirical_family %d memory.LOCAL_TCM.%s %s %.12g 0 1 PARTIAL_LIVE_PILOT %s core_cycles'%(h,direction,resource,tcm,paramsha));applied.append({'hart':h,'family':'memory.LOCAL_TCM.'+direction,'setup':tcm,'work':0,'resource':resource,'issue_interval_status':'explicit1fallback_not_independently_fitted','scope':'Read/store tied per-access aggregate; calibrated4-byteordinaryscalar accesses.'})
  for name,value in v.items():
   if name.startswith(('rvv.','vme.','branch.','scalar.fp')):
    why='Notapplied: unavailable131cbranch-serviceknob' if name.startswith('branch.') else 'Notapplied: asyncceilwouldturnsmallfractionintoonecycle/operation' if name.startswith('rvv.') else 'Notapplied: per-operation/workcoefficientsconfoundedordrain/coldsetupnotidentified'
    unapplied.append({'hart':h,'feature':name,'fit_value':value,'reason':why})
 fixture=out/'runtime.fixture';fixture.write_text('\n'.join(lines)+'\n');packet={'schema':'iris.empirical_selected_runtime_parameters.v1','status':'fitted_partial_candidate_requires_actual_native_validation','calibration_identity':identity,'units':'core_cycles_at_500MHz','raw_parameters_sha256':paramsha,'raw_fit_report_sha256':sha(ROOT/'calibration/empirical-corrected-shared-v1/report.json'),'fixture_sha256':sha(fixture),'feature_implementation_sha256':sha(ROOT/'timing/empirical_live_features.py'),'fitter_sha256':sha(ROOT/'timing/empirical_live_fit.py'),'selector_sha256':sha(__file__),'actual_parameter_fit_performed':True,'global_heldout_timings_consumed':False,'applied':applied,'unapplied':unapplied,'unsupported_or_unqualified':['FP8matrixlatencyunfitted;functionalsupportunchanged','RVV/VMEcomputebackendworkheuristicunfitted','Vector-memoryprivate-L1routeunqualified;nextsourcebypassfixrequired','RemoteTCM/scratchpadserviceunfittedforcurrentnative','ScalarFP/VectorFPserviceconservativefallback','IRQ/synchronization/atomics/LRSCtimingunqualified','Cold-cache/replacement/branch-historyapproximationhaslargeobservederrors'],'full_2pct_certified':False,'source_image_association_verified':False,'rtl_certified':False,'live_quality_accepted':False};save(out/'parameters.json',packet);(out/'selector-source.py').write_bytes(pathlib.Path(__file__).read_bytes());print(json.dumps({'fixture':str(fixture),'fixture_sha256':sha(fixture),'parameters_sha256':sha(out/'parameters.json')},indent=2))
if __name__=='__main__':main()
