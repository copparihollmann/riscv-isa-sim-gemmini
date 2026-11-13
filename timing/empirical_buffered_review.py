#!/usr/bin/env python3
"""Freeze the new buffered split and independently audit canonical case goldens.
No old timing labels are imported; no workload/source files are changed.
"""
import argparse,collections,copy,hashlib,importlib.util,json,pathlib,re,struct
ROOT=pathlib.Path(__file__).resolve().parents[1]
POLICY_SHA='40b8643818a11e51d45b74b971d4aa11a2d98d7a9039d3a117cfa4ee55c71379'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def module(name,p):
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def elf_symbols(blob):
 h=struct.unpack_from('<16sHHIQQQIHHHHHH',blob)
 if h[0][:6]!=b'\x7fELF\x02\x01':raise ValueError('Requires ELF64 little endian')
 sections=[struct.unpack_from('<IIQQQQIIQQ',blob,h[6]+i*h[11]) for i in range(h[12])];symbols={}
 for sec in sections:
  if sec[1]!=2:continue
  strings=sections[sec[6]];names=blob[strings[4]:strings[4]+strings[5]]
  for off in range(sec[4],sec[4]+sec[5],sec[9]):
   name,info,other,shndx,value,size=struct.unpack_from('<IBBHQQ',blob,off)
   text=names[name:].split(b'\0',1)[0].decode()
   if text and shndx:symbols[text]=(value,size)
 return h,symbols

def audit(corpus,canonical,oldsplit):
 if corpus['schema']!='iris.buffered_fitting_corpus.v1':raise ValueError('Unknown buffered schema')
 if corpus['trials']!=3 or corpus['expected_region_count']!=4050 or corpus['physical_harts']!=3:raise ValueError('Counts')
 rows=corpus['cases'];expected=[]
 for suite in ('baseline','distribution','memory'):
  for trial in range(3):
   expected.extend((suite,trial,c) for c in canonical[suite])
 if len(rows)!=len(expected) or len(rows)!=2208:raise ValueError('Cases incomplete')
 split={};aliases=collections.defaultdict(set);counts=collections.Counter();checks=0;seen=set()
 for c,(suite,t,original) in zip(rows,expected):
  parent=original['case_id'];newparent='buffered.v1.'+parent;ident=newparent+'.trial.'+str(t)
  if(c['suite'],c['trial_id'],c['semantic_parent_case_id'],c['parent_case_id'],c['case_id'])!=(suite,t,parent,newparent,ident):raise ValueError('Case order/identity')
  if ident in seen:raise ValueError('Duplicate case')
  seen.add(ident)
  for key,value in original.items():
   if key=='case_id':continue
   if key in c and c[key]!=value:raise ValueError('Semantic field changed: '+parent+'.'+key)
  if type(c['mask']) is not int or not 0<c['mask']<8:raise ValueError('Mask')
  goldens=original.get('expected_checksums',original.get('expected_checksums_by_hart'))
  if c['expected_checksums']!=goldens or len(goldens)!=3 or any(type(x) is not int or not 0<=x<2**64 for x in goldens):raise ValueError('Independent golden mismatch')
  old=oldsplit['split'][parent];ent=copy.deepcopy(old);ent['semantic_parent_case_id']=parent
  if newparent in split and split[newparent]!=ent:raise ValueError('Parent changes between trials')
  split[newparent]=ent;aliases[old['semantic_group']].add(old['partition']);counts[old['partition']]+=bin(c['mask']).count('1');checks+=len(original)+8
 if any(len(x)!=1 for x in aliases.values()):raise ValueError('Semantic alias leakage')
 if len(split)!=736 or len(aliases)!=728 or dict(counts)!={'train':3189,'internal_validation':861}:raise ValueError('Partition counts')
 return split,dict(counts),checks

def main(a):
 output=a.output;output.mkdir(parents=True,exist_ok=True)
 if (output/'split.json').exists() or (output/'review.json').exists():raise ValueError('Refuse frozen review overwrite')
 policy=output/'policy.json'
 if sha(policy)!=POLICY_SHA:raise ValueError('Prelaunch policy changed')
 oldsplit_path=ROOT/'calibration/empirical-v1/split.json';oldsplit=json.load(oldsplit_path.open());policydata=json.load(policy.open())
 if sha(oldsplit_path)!=policydata['source_parent_split_sha256']:raise ValueError('Parent split changed')
 base_path=ROOT/'benchmarks/calibration-corpus.json';base=json.load(base_path.open());golden=module('buffered_independent_baseline_golden',ROOT/'benchmarks/golden.py');golden.verify(base)
 baseline=[]
 for c in base['cases']:
  c=copy.deepcopy(c);c['mask']={'all':7,'compute':3,'1':1,'4':4}[c['active_hart_mask_expression']];c['expected_checksums']=[golden.checksum(c,h) for h in range(3)];baseline.append(c)
 dist_path=ROOT/'benchmarks/v2/cases.py';mem_path=ROOT/'benchmarks/memory_routes/cases.py'
 canonical={'baseline':baseline,'distribution':module('buffered_independent_dist',dist_path).cases(),'memory':module('buffered_independent_mem',mem_path).cases()}
 corpus_path=a.build/'corpus.json';corpus=json.load(corpus_path.open());build_path=a.build/'build.json';build=json.load(build_path.open());layout_path=a.build/'readback-layout.json';layout=json.load(layout_path.open())
 split,counts,checks=audit(corpus,canonical,oldsplit)
 # Independently compare source prefixes; do not trust builder's booleans.
 preserved=[]
 for suite in canonical:
  new=(a.build/(suite+'.c')).read_text();old=(a.build/'parent-derived'/(suite+'.c')).read_text()
  newprefix=new[:new.index('static void run(')].replace('#include "buffered.h"\n','');oldprefix=old[:old.index('static void run(')]
  if newprefix!=oldprefix:raise ValueError('Kernel/preparation prefix changed')
  runnew=new[new.index('static void run('):];runold=old[old.index('static void run('):]
  # Measurement source up to all per-hart results publication must stay exact.
  stop=runnew.index('  barrier();\n  if(h==0)') if suite!='baseline' else runnew.index('  barrier();\n  if(h==0)')
  # Last pre-console barrier after the measured interval, not the first reset barrier.
  marker='    results[h]='
  endnew=runnew.index(';',runnew.index(marker))+1;endold=runold.index(';',runold.index(marker))+1
  if runnew[:endnew]!=runold[:endold]:raise ValueError('Measured run window changed')
  preserved.append({'suite':suite,'kernel_preparation_prefix_normalized_byte_equal':True,'measured_run_window_source_byte_equal':True,'prefix_sha256':hashlib.sha256(newprefix.encode()).hexdigest()});checks+=2
 # Every actual compiler/source input must still have the recorded identity.
 for path,digest in build['input_sha256'].items():
  if sha(path)!=digest:raise ValueError('Build input changed '+path)
  checks+=1
 elf_path=a.build/'campaign.elf';blob=elf_path.read_bytes()
 if sha(elf_path)!=build['elf_sha256'] or sha(elf_path)!=layout['elf_sha256']:raise ValueError('ELF identity')
 h,symbols=elf_symbols(blob)
 for name,obj in layout['objects'].items():
  if symbols.get(name)!=(obj['address'],obj['size']):raise ValueError('ELF symbol/size mismatch '+name)
  checks+=1
 if layout['record_bytes']!=64 or layout['records']!=4050 or layout['objects']['buffered_records']['size']!=4050*64:raise ValueError('Record stride/array capacity')
 sentinel=layout['objects']['buffered_measurements_done']['address'];matches=[]
 for i in range(h[10]):
  ph=struct.unpack_from('<IIQQQQQQ',blob,h[5]+i*h[9])
  if ph[0]==1 and ph[3]<=sentinel and sentinel+8<=ph[3]+ph[5]:matches.append(blob[ph[2]+sentinel-ph[3]:ph[2]+sentinel-ph[3]+8])
 if matches!=[b'\xff'*8]:raise ValueError('Sentinel not file-backed UINT64_MAX')
 # Source control contract was manually reviewed as well as these exact guards.
 mainpath=ROOT/'benchmarks/campaign_buffered/main.c';m=mainpath.read_text();body=m[m.index('void benchmark_main'):]
 if body.index('buffered_case_count!=CAMPAIGN_CASES')>body.index('buffered_measurements_done=0'):raise ValueError('Sentinel before count checks')
 if body.index('buffered_measurements_done=0')>body.index('print_records();'):raise ValueError('Output before completion sentinel')
 if body[:body.index('buffered_measurements_done=0')].count('putstr('):raise ValueError('Pre-completion main UART')
 # Negative controls exercise reviewed semantics before any hardware labels.
 negatives=[]
 for field in ('expected_checksums','mask','semantic_parent_case_id','trial_id','parent_case_id'):
  bad=copy.deepcopy(corpus)
  if field=='expected_checksums':bad['cases'][0][field][0]+=1
  elif field=='mask':bad['cases'][0][field]=True
  elif field=='trial_id':bad['cases'][0][field]=1
  else:bad['cases'][0][field]='wrong'
  try:audit(bad,canonical,oldsplit)
  except(ValueError,KeyError):negatives.append({'field':field,'rejected':True})
  else:raise ValueError('Bad corpus accepted '+field)
 record={'schema':'iris.empirical_buffered_parent_split.v1','policy_sha256':sha(policy),'split':split,'parent_counts':dict(collections.Counter(e['partition'] for e in split.values())),
    'region_counts':counts,'semantic_groups':728,'trials':3,'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [oldsplit_path,corpus_path,build_path,elf_path]},'new_reference_timings_opened':False,'global_heldout_timings_consumed':False,'internal_validation_scope':'development_only_previous_errors_viewed','full_2pct_certified':False}
 (output/'split.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
 paths=[pathlib.Path(__file__).resolve(),policy,oldsplit_path,base_path,ROOT/'benchmarks/golden.py',dist_path,mem_path,corpus_path,build_path,layout_path,elf_path,mainpath]
 report={'schema':'iris.empirical_buffered_independent_review.v1','status':'source_golden_split_review_passed_functional_and_reference_pending','checks':checks,'negative_controls':negatives,
   'canonical_source_cases':{k:len(v) for k,v in canonical.items()},'case_count':2208,'region_count':4050,'golden_values_by_active_hart_independently_checked':4050,
   'source_prefix_and_window_preservation':preserved,'ELF_symbols_record_stride_and_initial_sentinel_independently_checked':True,'partition_region_counts':counts,
   'old_ELF_reference_timings_imported':False,'numeric_functional_execution_claimed':False,'hardware_reference_available':False,'global_heldout_timings_consumed':False,'full_2pct_certified':False,
   'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in paths},'split_sha256':sha(output/'split.json')}
 (output/'review.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2));print('SHA',sha(output/'review.json'))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',type=pathlib.Path,default=ROOT/'build/campaign-buffered-fit-v1');p.add_argument('--output',type=pathlib.Path,default=ROOT/'calibration/empirical-buffered-v1');main(p.parse_args())
