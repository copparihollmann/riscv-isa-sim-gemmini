#!/usr/bin/env python3
"""Export effective residual coefficients; NEVER export nuisance ROI intercepts.
This draft is for explicit experimental resource residual integration only.
"""
import argparse,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main(args):
 p=pathlib.Path(args.parameters);par=json.loads(p.read_text());lines=[];mapping=[];source=sha(p)
 def add(h,f,resource,setup,slope,status,model,work,notes=()):
  lines.append('empirical_family %d %s %s %.12g %.12g 1 %s %s core_cycles'%(h,f,resource,setup,slope,status,source))
  mapping.append({'hart':h,'family':f,'resource':resource,'setup_cycles':setup,'cycles_per_work':slope,
   'issue_interval_cycles':1,'issue_interval_status':'explicit_source_fallback_not_fitted','parameter_model':model,
   'work_definition':work,'status':status,'unknowns':list(notes)})
 for h in range(3):
  c='shuttle' if h<2 else 'rocket'
  for kind in ('integer','fp16','fp32','fp64'):
   key='vector/'+c+'/'+kind
   if key not in par['region_models']:continue
   m=par['region_models'][key];co=m['coefficients']
   # The chain residual is only exposed in separate mapping metadata; this
   # baseline export adds it conservatively to every operation, not by ID.
   setup=co['operations']+co['dependent_operations'];slope=co['dlen_beats']
   add(h,'rvv.'+kind,'vector'+str(h),setup,slope,'PROXY_RESIDUAL',key,'ceil(VL*SEW/DLEN)',
     ['Adds residual to scalar scheduling; does not replace scalar pipeline.',
      'Dependent residual conservatively charged to each op; raw dependency-aware refinement pending.',
      'Rank %d/%d; drain_bytes and ROI intercept not charged per op.'%(m['feature_rank'],m['feature_columns'])])
  for bits in (16,32,64):
   key='scalar_fp/'+c+'/e'+str(bits)
   if key not in par['region_models']:continue
   m=par['region_models'][key]
   if not m['individual_coefficients_identifiable']:continue
   add(h,'scalar.fp'+str(bits),'scalar_fp'+str(h),m['coefficients']['operations'],0.,'PROXY_RESIDUAL',key,'one FP operation',
     ['FADD dependent-chain only; does not qualify multiply/divide/sqrt.'])
  if h<2:
   for kind in ('int8','fp8'):
    key='vme/'+kind;co=par['region_models'][key]['coefficients']
    add(h,'vme.'+kind,'vme'+str(h),co['operations'],co['k_steps']/4.,'PROXY_RESIDUAL',key,'ceil(tm/16)*ceil(tn/16)*tk',
      ['32x32 calibration shape only; other shapes uncalibrated.','Physical MAC pipeline interval not identified.'])
   for src,dest in [('tile_zero','zero'),('row_read','move_read'),('row_write','move_write')]:
    key='vme/'+src;co=par['region_models'][key]['coefficients']
    if not par['region_models'][key]['individual_coefficients_identifiable'] or co['operations']==0:continue
    add(h,'vme.'+dest,'vme'+str(h),co['operations'],0.,'PROXY_RESIDUAL',key,'one tile operation',['Zero/move residual only; full tile semantics remain functional.'])
  for path in ('local_tcm','remote_tcm','scratchpad','dram'):
   # Separate load/store families are required to avoid treating bytes as
   # identical requests. No arbitrary scaling of a per-access cost by width.
   for direction,op in [('load','chase'),('store','write')]:
    key='memory/'+c+'/'+path+'/'+op
    if key not in par['region_models']:continue
    co=par['region_models'][key]['coefficients']
    add(h,'memory.'+path.upper()+'.'+direction,'memory_'+path,co['accesses'],0.,'WARM_PROXY_RESIDUAL',key,'bytes (slope0; setup per actual request)',
      ['64-bit scalar accesses only.','Contention coefficients remain explicit in parameter JSON, not charged by active mask here.',
       'DRAM is warm effective cached path; separate runtime-tag miss service required.'])
 out=pathlib.Path(args.output);out.mkdir(parents=True,exist_ok=True)
 fixture=out/'residual.fixture'
 if fixture.exists():raise SystemExit('Refuse overwriting fixture epoch')
 fixture.write_text('# EXPERIMENTAL RESIDUALS, add to source scalar schedule; no ROI intercepts.\n'+'\n'.join(lines)+'\n')
 receipt={'schema':'iris.empirical_fixture_mapping.v1','parameters_sha256':source,'fixture_sha256':sha(fixture),'source_sha256':sha(__file__),
  'lines':len(lines),'mapping':mapping,'native_binding_qualified':False,'full_2pct_certified':False,
  'source_image_association_verified':False,'unsupported':['scalar FP16 latency rankdeficient','scalarFP32 no trainingexamples','branchmiss penalty','VME rowmovesunidentified','atomic/LRSC/IRQ/sync','coldcachemiss service','independent contention scheduler'],
  'application_contract':'Residual costs only, plus scalar source scheduler; setup is per instruction, not per region; issue interval1 is explicit source fallback, not fitted.'}
 (out/'mapping.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n');print(json.dumps({'fixture':str(fixture),'sha256':sha(fixture),'lines':len(lines)}))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--parameters',default='calibration/empirical-v1/parameters.json');a.add_argument('--output',default='calibration/empirical-v1/fixture-draft-v1');main(a.parse_args())
