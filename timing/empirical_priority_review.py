#!/usr/bin/env python3
"""Order-aware canonical source/golden/split review for the NEW priority ELF."""
import copy,json,pathlib,re,struct
import empirical_buffered_review as base
import empirical_buffered_strict_review as typed
ROOT=base.ROOT
POLICY_SHA='aafcd41fe165be8567a37e31e89fe5c3df8c63abe6ef7f2be324491848af2f44' # set to the frozen policy digest by the invocation below

def canonical_cases():
 b=json.load((ROOT/'benchmarks/calibration-corpus.json').open());g=base.module('priority_golden',ROOT/'benchmarks/golden.py');g.verify(b)
 for c in b['cases']:
  c['mask']={'all':7,'compute':3,'1':1,'4':4}[c['active_hart_mask_expression']];c['expected_checksums']=[g.checksum(c,h) for h in range(3)]
 return {'baseline':b['cases'],'distribution':base.module('priority_dist',ROOT/'benchmarks/v2/cases.py').cases(),'memory':base.module('priority_mem',ROOT/'benchmarks/memory_routes/cases.py').cases()}

def expected_order(canonical):
 rows={s:[dict(copy.deepcopy(c),suite=s,trial_id=t,parent_case_id=c['case_id']) for t in range(3) for c in cs] for s,cs in canonical.items()}
 names=['dependent','independent','branch','scalar_fp','vector_int','vector_fp','vme_int','vme_fp8','row_read','row_write','tile_zero','shared_fpu','vme_memory','vme_refusal','pipeline','pipeline_vme','atomic','frontend','memory'];ranks=dict(zip(names,range(len(names))))
 def rank(c):
  k=c['kind'];n=ranks[k]
  if k=='memory':
   if c['protocol']==1 and c['mode']==0 and c['bytes']==131072 and c['mask'] in(1,3):n=17
   elif c['protocol']==1 and c['mode']==0 and c['bytes']==1048576 and c['mask'] in(1,3,4) and c['parent_case_id'].startswith('v2.contention.private-read.'):n=18
   else:n=20
  elif k=='frontend':n=19
  return n,c['bytes'] if k in('memory','frontend') else 0,c['parent_case_id'],c['trial_id']
 dist=sorted(rows['distribution'],key=rank);prefix=len(rows['memory'])+sum(rank(c)[0]<20 for c in dist)
 return rows['memory']+dist+rows['baseline'],prefix

def audit(corpus,canonical,oldsplit):
 if corpus.get('schema')!='iris.buffered_fitting_corpus.v2' or corpus.get('ordering_uses_measured_cycles')is not False:raise ValueError('Wrong priority corpus/ordering scope')
 order,prefix=expected_order(canonical)
 if corpus.get('priority_prefix_cases')!=prefix or prefix!=1989:raise ValueError('Priority prefix')
 for c,o in zip(corpus['cases'],order):
  if(c['suite'],c['semantic_parent_case_id'],c['trial_id'])!=(o['suite'],o['case_id'],o['trial_id']):raise ValueError('Static execution order mismatch')
 # Canonical membership/golden review is order-independent. Normalize only an
 # in-memory review copy into the old canonical order; never modify source,
 # reference labels, actual IDs or the executable's order.
 normalized=copy.deepcopy(corpus);normalized['schema']='iris.buffered_fitting_corpus.v1'
 idx={(s,c['case_id']):i for s,cs in canonical.items() for i,c in enumerate(cs)};suiteorder={'baseline':0,'distribution':1,'memory':2}
 for c in normalized['cases']:
  if not c['case_id'].startswith('buffered.v2.') or not c['parent_case_id'].startswith('buffered.v2.'):raise ValueError('Wrong dataset identity')
  c['case_id']='buffered.v1.'+c['case_id'][len('buffered.v2.'):];c['parent_case_id']='buffered.v1.'+c['parent_case_id'][len('buffered.v2.'):]
 normalized['cases'].sort(key=lambda c:(suiteorder[c['suite']],c['trial_id'],idx[(c['suite'],c['semantic_parent_case_id'])]))
 s,counts,checks=typed.strict(normalized,canonical,oldsplit)
 split={'buffered.v2.'+p[len('buffered.v1.'):]:e for p,e in s.items()}
 pref=corpus['cases'][:prefix]
 if sum(bin(c['mask']).count('1') for c in pref)!=3633 or corpus['priority_prefix_regions']!=3633:raise ValueError('Priority region coverage')
 return split,counts,checks

def strings_array(text,name):
 match=re.search(r'\b'+name+r'\[\]\s*=\s*\{(.*?)\};',text,re.S)
 if not match:raise ValueError('Missing source array '+name)
 return [json.loads(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"',match[1])]

def main():
 out=ROOT/'calibration/empirical-priority-v2';policy=out/'policy.json'
 if base.sha(policy)!=POLICY_SHA or(out/'review.json').exists()or(out/'split.json').exists():raise ValueError('Frozen policy/review identity')
 b=ROOT/'build/campaign-buffered-priority-v2-final';corpus=json.load((b/'corpus.json').open());built=json.load((b/'build.json').open());layout=json.load((b/'readback-layout.json').open());oldpath=ROOT/'calibration/empirical-v1/split.json';old=json.load(oldpath.open());canonical=canonical_cases();split,counts,checks=audit(corpus,canonical,old)
 for p,h in built['input_sha256'].items():
  if base.sha(p)!=h:raise ValueError('Changed build input '+p)
  checks+=1
 elf=b/'campaign.elf';blob=elf.read_bytes();header,syms=base.elf_symbols(blob)
 if base.sha(elf)!=built['elf_sha256'] or base.sha(elf)!=layout['elf_sha256']:raise ValueError('ELF identity')
 for n,v in layout['objects'].items():
  if syms.get(n)!=(v['address'],v['size']):raise ValueError('ELF symbol geometry '+n)
  checks+=1
 if layout['objects']['buffered_records']['size']!=4050*64 or layout['record_bytes']!=64 or layout['records']!=4050:raise ValueError('Record capacity')
 sentinel=syms['buffered_measurements_done'][0];vals=[]
 for i in range(header[10]):
  ph=struct.unpack_from('<IIQQQQQQ',blob,header[5]+i*header[9])
  if ph[0]==1 and ph[3]<=sentinel and sentinel+8<=ph[3]+ph[5]:vals.append(blob[ph[2]+sentinel-ph[3]:ph[2]+sentinel-ph[3]+8])
 if vals!=[b'\xff'*8]:raise ValueError('File-backed initial sentinel')
 table=(b/'buffered_cases.inc').read_text();cases=corpus['cases']
 if strings_array(table,'buffered_ids')!=[c['case_id'] for c in cases]:raise ValueError('Compiled ID source order')
 originalids=[c['semantic_parent_case_id']+'.trial.'+str(c['trial_id']) for c in cases]
 if strings_array(table,'buffered_original_ids')!=originalids:raise ValueError('Compiled original ID source order')
 # Derive actual call-table execution order from each compiled suite input.
 execution=[]
 for suite,filename in [('memory','memory_cases.inc'),('distribution','distribution_cases.inc')]:
  ids=re.findall(r'\{("(?:[^"\\]|\\.)*")\s*,',(b/filename).read_text());execution += [json.loads(x) for x in ids]
 execution += [json.loads(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"',(b/'baseline_ids.inc').read_text())]
 if execution!=originalids:raise ValueError('Actual suite call tables do not execute corpus order')
 preservation=[]
 for suite in canonical:
  new=(b/(suite+'.c')).read_text();parent=(b/'parent-derived'/(suite+'.c')).read_text();prefix=new[:new.index('static void run(')].replace('#include "buffered.h"\n','')
  if prefix!=parent[:parent.index('static void run(')]:raise ValueError('Kernel/preparation changed')
  n=new[new.index('static void run('):];o=parent[parent.index('static void run('):];marker='    results[h]='
  if n[:n.index(';',n.index(marker))+1]!=o[:o.index(';',o.index(marker))+1]:raise ValueError('Measured run window changed')
  preservation.append({'suite':suite,'kernel_preparation_and_measured_window_byte_equal':True});checks+=2
 mainpath=ROOT/'benchmarks/campaign_buffered/main_reordered.c';body=mainpath.read_text().split('void benchmark_main',1)[1]
 if not body.index('campaign_memory_run')<body.index('campaign_distribution_run')<body.index('campaign_baseline_run'):raise ValueError('Actual main suite order')
 if not body.index('buffered_case_count!=CAMPAIGN_CASES')<body.index('buffered_measurements_done=0')<body.index('print_records();'):raise ValueError('Completion/output order')
 negatives=[]
 for control in ('golden','reordered','unknown_field','boolean_trial','wrong_dataset','measured_order'):
  bad=copy.deepcopy(corpus)
  if control=='golden':bad['cases'][0]['expected_checksums'][0]+=1
  elif control=='reordered':bad['cases'][0],bad['cases'][1]=bad['cases'][1],bad['cases'][0]
  elif control=='unknown_field':bad['cases'][0]['golden_latency']=30
  elif control=='boolean_trial':bad['cases'][0]['trial_id']=False
  elif control=='wrong_dataset':bad['cases'][0]['case_id']='buffered.v1.wrong'
  else:bad['ordering_uses_measured_cycles']=True
  try:audit(bad,canonical,old)
  except(ValueError,KeyError):negatives.append({'control':control,'rejected':True})
  else:raise ValueError('Bad priority corpus accepted '+control)
 paths=[pathlib.Path(__file__).resolve(),ROOT/'timing/empirical_buffered_review.py',ROOT/'timing/empirical_buffered_strict_review.py',policy,oldpath,b/'corpus.json',b/'build.json',b/'readback-layout.json',elf,mainpath,ROOT/'benchmarks/golden.py',ROOT/'benchmarks/v2/cases.py',ROOT/'benchmarks/memory_routes/cases.py']
 record={'schema':'iris.empirical_priority_parent_split.v2','policy_sha256':base.sha(policy),'split':split,'parent_counts':{'train':580,'internal_validation':156},'region_counts':counts,'semantic_groups':728,'trials':3,'input_sha256':{str(p.relative_to(ROOT)):base.sha(p) for p in [b/'corpus.json',b/'build.json',elf,oldpath]},'priority_prefix_cases':1989,'priority_prefix_regions':3633,'reference_timings_opened':False,'global_heldout_timings_consumed':False,'internal_validation_scope':'development_only_previous_errors_viewed','full_2pct_certified':False};(out/'split.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
 report={'schema':'iris.empirical_priority_independent_review.v2','status':'source_goldens_static_order_split_passed_functional_reference_pending','checks':checks,'negative_controls':negatives,'cases':2208,'regions':4050,'priority_prefix_cases':1989,'priority_prefix_regions':3633,'typed_canonical_goldens_all_active_harts_verified':True,'compiled_source_ID_and_call_table_order_independently_verified':True,'source_preservation':preservation,'ordering_uses_measured_cycles':False,'old_reference_timings_imported':False,'numeric_functional_execution_claimed':False,'hardware_reference_available':False,'global_heldout_timings_consumed':False,'full_2pct_certified':False,'input_sha256':{str(p.relative_to(ROOT)):base.sha(p) for p in paths},'split_sha256':base.sha(out/'split.json')};(out/'review.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2));print('SHA',base.sha(out/'review.json'))
if __name__=='__main__':main()
