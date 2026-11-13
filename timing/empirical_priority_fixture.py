#!/usr/bin/env python3
"""Select only native-chargeable positive services; freeze a real replay candidate."""
import collections,hashlib,json,math,pathlib,statistics
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def main():
 out=ROOT/'calibration/empirical-priority-28a0-runtime-v1';out.mkdir(exist_ok=False)
 rawpath=ROOT/'calibration/empirical-priority-28a0-fit-v2/parameters.json';raw=json.load(rawpath.open());rows=[json.loads(s)for s in open(ROOT/'build/empirical-priority-28a0-features-v1/regions.jsonl')];splitpath=ROOT/'calibration/empirical-priority-v2/split.json';split=json.load(splitpath.open());co={k:v['coefficients']for k,v in raw['models'].items()}
 training=[r for r in rows if r['partition']=='train']
 # Single-hart Rocket training identifies an effective outer return service.
 # Use the shared hierarchy constraint instead of mistaking the two-Shuttle
 # saturated per-hart elapsed time for an independent longer intrinsic latency.
 outer=co['rocket']['cache.DRAM.l2misses']
 parent='buffered.v2.v2.contention.private-read.1048576.mask3';groups=collections.defaultdict(list)
 for r in training:
  if r['parent_case_id']==parent:groups[r['case_id']].append(r)
 samples=[]
 for key,group in sorted(groups.items()):
  if {r['hart']for r in group}!={0,1}:raise ValueError('Incomplete saturated training group')
  # Active read loops have no WFI: compare their elapsed spans, never their
  # independent absolute mcycle origins. CPU work overlaps shared service.
  lines=sum(r['memory']['DRAM']['l2misses']for r in group);span=max(r['reference_cycles']for r in group)
  samples.append({'case_id':key,'max_active_hart_elapsed_cycles':span,'runtime_model_outer_line_misses':lines,'effective_cycles_per_accepted_line':span/lines})
 if len(samples)!=3:raise ValueError('Expected all3 frozen training repetitions')
 interval=int(round(statistics.median(x['effective_cycles_per_accepted_line']for x in samples)))
 selected={'schema':'iris.empirical_selected_priority_parameters.v1','calibration_identity':'iris-empirical-priority-28a0-v1','raw_parameters_sha256':sha(rawpath),
  'native_binary_sha256':'28a0a52ba04ca05aec01b1c1a9ca86becbd47336d4eec112873695cdb7ea6c50',
  'uart_library_sha256':'92f6168dadd84d18628e04281abd83d134efe022a3db2aae331673b0be6c5b03',
  'base_hz':500000000,'rtc_divider':1000,'counter_policy':'source-ungated-stall','shared_outer':{'effective_return_additional_cycles':outer,'effective_launch_interval_core_cycles_per64B':interval,
   'single_hart_service_basis':'train-only Rocket shared-DRAM outer-miss coefficient; common service transfer to compute is an explicit approximation, not a separately identified NoC path',
   'launch_fit_samples':samples,'launch_scope':'train-only saturated two-compute private-read1MiB; traffic history and physical miss counts remain unqualified'},'cache':{},'instruction':{},'branch':{},'families':[],
  'unapplied':['ScalarFP pipeline is structurally overconservative; no negative correction.','DRAM hot-load read-base forced0 because it is not charged by the actual L1-hit front.','Dirty-writeback separate cost not identified in this selected basis; left0.','Icache outer service has no independent fitted ROI miss basis; common service transfer is explicit.','BF16 and FP8 vector-FADD have no training instruction coverage; no timing coefficient applied.','Heavy late417reference regions lack matched native coverage.','TCM/scratch2banks and source ingress/NoC contention are not fully modeled.','Atomic/synchronization timing and hardware vector transport hang are unqualified.'],
  'quantization':'Async extra setup/work projected onto nonnegative integer cycle coefficients over actual training work domains; data/path services retain native per-family fractional carry. Icache/branch services integer-rounded before native ceil.',
  'actual_parameter_fit_performed':True,'actual_calibrated_native_replay_completed':False,'global_heldout_timings_consumed':False,'full_2pct_certified':False,'source_image_association_verified':False}
 for h in range(3):
  cls='shuttle'if h<2 else'rocket';c=co[cls]
  selected['cache'][str(h)]={'read_base':0.,'write_base':c.get('cache.DRAM.writes',0.),'l1_miss':c.get('cache.DRAM.l1misses',0.),'outer_miss':outer,'outer_interval':interval,'dirty_extra':0.}
  selected['instruction'][str(h)]={'l1_miss':int(round(c.get('icache.DRAM.l1misses',0.))),'outer_miss':outer,'outer_interval':interval,'outer_status':'common_outer_transfer_not_independently_fitted'}
  selected['branch'][str(h)]=int(round(c.get('branch.mispredicts',0.)))
  for path in ['LOCAL_TCM','REMOTE_TCM','SCRATCHPAD']:
   for kind,family in [('reads','load'),('writes','store')]:
    value=c.get('memory.'+path+'.'+kind,0.)
    if value>0:selected['families'].append({'hart':h,'family':'memory.'+path+'.'+family,'resource':'empirical.scratchpad'if path=='SCRATCHPAD'else'empirical.tcm.target0','setup':value,'work':0.,'interval':1,'scope':'effective_additional_'+path.lower()+'_'+family})
  for family in ['memory.vector.load','memory.vector.store']:
   a=c.get(family+'.instructions',0.);b=c.get(family+'.work',0.)
   if a or b:selected['families'].append({'hart':h,'family':family,'resource':'empirical.vector-memory'+str(h),'setup':a,'work':b,'interval':1,'scope':'additional_vector_service_preserving_actual_cache_outer_layer'})
  families=sorted({f for r in training if r['hart']==h for f,v in r['features'].items()if f.startswith(('rvv.','vme.'))and v['instructions']})
  for family in families:
   points=[r for r in training if ('shuttle'if r['hart']<2 else'rocket')==cls and r['features'].get(family,{}).get('instructions',0)]
   a=c.get(family+'.instructions',0.);b=c.get(family+'.work',0.)
   # Projection selection is based only on the fitted training mechanism, not
   # heldout labels. The actual nonlinear replay is required for its quality.
   best=None
   for ai in range(9):
    for bi in range(3):
     loss=sum(((ai*r['features'][family]['instructions']+bi*r['features'][family]['work']-(a*r['features'][family]['instructions']+b*r['features'][family]['work']))/max(r['reference_cycles'],1))**2 for r in points)
     candidate=(loss,ai+bi,ai,bi)
     if best is None or candidate<best:best=candidate
   _,_,ai,bi=best
   if not(ai or bi):continue
   resource=('empirical.sharedFPU2'if h==2 else'empirical.vectorFP'+str(h))if family.startswith('rvv.fadd.')else('empirical.vme'+str(h)if family.startswith('vme.')else'empirical.vector'+str(h))
   domain=sorted({r['features'][family]['work']/r['features'][family]['instructions']for r in points})
   selected['families'].append({'hart':h,'family':family,'resource':resource,'setup':ai,'work':bi,'interval':1,'training_work_per_instruction':domain,'scope':'integer_backend_projection; outside_observed_work_domain_unqualified','raw_setup_work':[a,b]})
 save(out/'parameters.json',selected);digest=sha(out/'parameters.json')
 base=(ROOT/'build/empirical-priority-28a0-baseline-input-v1/baseline.fixture').read_text();base=base.replace('priority-v2-28a0-unfitted-v1',selected['calibration_identity']);base=base.replace('source experimental-fast-event-baseline-no-RTL-peer-evaluation-unfitted','source actual-priority-v2-training-positive-effective-services-not-full-certificate')
 resources=sorted({f['resource']for f in selected['families']}|{'empirical.tcm.target0','empirical.tcm.target1'})
 lines=[base.rstrip(),'']+['resource '+r+' 1'for r in resources]
 status='EFFECTIVE_PRIORITY_TRAIN_FIT'
 for h in range(3):
  d=selected['cache'][str(h)];vals=[d[k]for k in ('read_base','write_base','l1_miss','outer_miss','outer_interval','dirty_extra')]
  lines.append('empirical_cache_service '+str(h)+' '+' '.join(format(v,'.12g')for v in vals)+' '+status+' '+digest+' core_cycles')
  d=selected['instruction'][str(h)];lines.append('empirical_instruction_service '+str(h)+' '+' '.join(format(d[k],'.12g')for k in ('l1_miss','outer_miss','outer_interval'))+' '+status+' '+digest+' core_cycles')
  lines.append('empirical_branch_service '+str(h)+' '+str(selected['branch'][str(h)])+' '+status+' '+digest+' core_cycles')
 for f in selected['families']:lines.append('empirical_family '+str(f['hart'])+' '+f['family']+' '+f['resource']+' '+' '.join(format(f[k],'.12g')for k in ('setup','work','interval'))+' '+status+' '+digest+' core_cycles')
 (out/'runtime.fixture').write_text('\n'.join(lines)+'\n');(out/'selection-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
 save(out/'selection-report.json',{'schema':'iris.empirical_priority_parameter_selection.v1','status':'actual_fit_mapped_native_replay_pending','parameters_sha256':digest,'fixture_sha256':sha(out/'runtime.fixture'),'raw_parameters_sha256':sha(rawpath),'integer_projected_families':len([f for f in selected['families']if f['family'].startswith(('rvv.','vme.'))]),'shared_outer_launch_fit_uses_train_only':True,'old_448_unfitted_interval_replaced':True,'shared_return_service_transfer_is_explicit':True,'actual_native_quality_claimed':False,'global_heldout_timings_consumed':False,'full_2pct_certified':False,'input_sha256':{str(p.relative_to(ROOT)):sha(p)for p in [pathlib.Path(__file__).resolve(),rawpath,ROOT/'build/empirical-priority-28a0-features-v1/regions.jsonl',splitpath,ROOT/'calibration/empirical-priority-reference-v2/report.json',ROOT/'build/empirical-vector-layer-proof-v1/report.json']}})
 print(json.dumps({'parameters_sha256':digest,'fixture_sha256':sha(out/'runtime.fixture'),'outer':outer,'interval':interval,'families':selected['families']},indent=2))
if __name__=='__main__':main()
