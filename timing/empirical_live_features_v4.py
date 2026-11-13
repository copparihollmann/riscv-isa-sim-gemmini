#!/usr/bin/env python3
"""Join real program cycle-boundary values to actual generic prefix counters.
IDs join evidence only; no benchmark identity is admitted as a model feature.
"""
import argparse,collections,hashlib,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def read_complete(path):
 raw=pathlib.Path(path).read_bytes();complete=raw[:raw.rfind(b'\n')+1] if b'\n' in raw else b''
 return raw,complete.decode().splitlines()
def difference(before,after):
 out={}
 for family in sorted(set(before)|set(after)):
  a=before.get(family,{});b=after.get(family,{});vals={}
  for key in sorted(set(a)|set(b)):
   av=a.get(key,0);bv=b.get(key,0)
   if type(av) is not int or type(bv) is not int or av<0 or bv<0:raise ValueError('Unsigned integer counter required')
   x=bv-av
   if x<0:raise ValueError('Prefix counter moved backwards: '+family+'.'+key)
   vals[key]=x
  if any(vals.values()):out[family]=vals
 return out

def join(observations,native_stdout,prefixes,allow_partial=False):
 ref={}
 for r in observations:
  key=(r['case_id'],r['hart'])
  if key in ref:raise ValueError('Duplicate reference key')
  ref[key]=r
 index=collections.defaultdict(list);sequence=collections.defaultdict(lambda:-1)
 for p in prefixes:
  if p['schema']!='iris.empirical.prefix.v1' or p['endpoint']!='get_csr_before_current_instruction_retirement':raise ValueError('Unqualified feature endpoint')
  h=p['hart']
  for name in ('hart','sequence','value','read_cycle','retired'):
   if type(p[name]) is not int or p[name]<0:raise ValueError('Unsigned prefix field required: '+name)
  for family,metrics in p['features'].items():
   required={'instructions','work','bytes','macs'};optional={'dlen_beats','atl_beats'}
   if not required<=set(metrics) or not set(metrics)<=required|optional:raise ValueError('Unqualified feature counter keys')
   if any(type(value) is not int or value<0 for value in metrics.values()):raise ValueError('Unsigned feature counters required')
   if not re.fullmatch(r'(scalar\.(integer|branch|csr_system|fence|fp(16|32|64|128)|fadd\.fp(16|32|64))|vector\.config|rvv\.(integer|fp(8|16|32|64)|fadd\.(bf16|fp(8|16|32|64)))|vme\.(int8|fp8|zero|row_move|discard)|memory\.(DRAM|LOCAL_TCM|REMOTE_TCM|SCRATCHPAD|UNCACHED|MMIO)\.(load|store|atomic|lr|sc)|memory\.vector\.(load|store)(\.address_pattern_uncalibrated)?)',family):raise ValueError('Unqualified runtime feature family: '+family)
  if p['sequence']<=sequence[h]:raise ValueError('Feature sequence not increasing')
  sequence[h]=p['sequence'];index[(h,p['value'])].append(p)
 regions=[];seen=set();missing=[];native_failed=[]
 for r in native_stdout:
  key=(r['case_id'],r['hart'])
  if key in seen:raise ValueError('Duplicate native region key')
  seen.add(key)
  if key not in ref:raise ValueError('Unknown native region identity')
  if r.get('pass') is not True:native_failed.append(key);continue
  target=ref[key];start=index[(r['hart'],r['start_cycle'])];end=index[(r['hart'],r['end_cycle'])]
  if len(start)!=1 or len(end)!=1:
   missing.append({'key':key,'start_matches':len(start),'end_matches':len(end)})
   if not allow_partial:raise ValueError('Missing or ambiguous CSR boundary '+str(key))
   continue
  a,b=start[0],end[0]
  if b['sequence']<=a['sequence'] or b['read_cycle']<a['read_cycle'] or r['end_cycle']<=r['start_cycle']:raise ValueError('Invalid region boundary order')
  if r['checksum']!=int(target['checksum']):raise ValueError('Native checksum differs from independent FPGA/reference checksum')
  features=difference(a['features'],b['features']);busy={}
  for name in sorted(set(a['completed_resource_busy_cycles'])|set(b['completed_resource_busy_cycles'])):
   value=b['completed_resource_busy_cycles'].get(name,0)-a['completed_resource_busy_cycles'].get(name,0)
   if value<0:raise ValueError('Busy prefix moved backwards')
   if value:busy[name]=value
  regions.append({'schema':'iris.empirical.runtime_region_features.v1','case_id':key[0],'parent_case_id':target['parent_case_id'],
   'hart':key[1],'partition':target['partition'],'family_for_reporting_only':target['family'],
   'reference_cycles':target['cycles'],'reference_instret_delta':target['instret_delta'],
   'native_cycles':r['end_cycle']-r['start_cycle'],'native_instret_delta':r['instret_delta'],
   'baseline_cycles':b['baseline_cycles']-a['baseline_cycles'] if a.get('baseline_cycles') is not None and b.get('baseline_cycles') is not None else None,'read_cycle_span':b['read_cycle']-a['read_cycle'],'retired_delta':b['retired']-a['retired'],
   'features':features,'completed_resource_busy_cycle_deltas':busy,'resource_occupancy_prefix_deltas':difference(a.get('resource_occupancy_prefix',{}),b.get('resource_occupancy_prefix',{})),'branch_history':difference({'branch':a.get('branch_history',{})},{'branch':b.get('branch_history',{})}).get('branch',{}),'memory':difference(a.get('memory',{}),b.get('memory',{})),
   'start_sequence':a['sequence'],'end_sequence':b['sequence'],'checksum_validated':True,
   'identity_or_pc_in_runtime_features':False})
 if native_failed:raise ValueError('Native guest reported failed checksums: '+str(native_failed[:3]))
 if not allow_partial and len(regions)!=len(ref):raise ValueError('Incomplete native coverage')
 return regions,{'reference_regions':len(ref),'joined_regions':len(regions),'missing_or_ambiguous_boundaries':missing,'partial':len(regions)!=len(ref)}

def main(args):
 out=pathlib.Path(args.output);out.mkdir(parents=True,exist_ok=True)
 raw,lines=read_complete(args.stdout);native=[]
 for line in lines:
  if line.startswith('IRIS_REGION '):native.append(json.loads(line[len('IRIS_REGION '):]))
 fraw,flines=read_complete(args.features);prefixes=[json.loads(s) for s in flines]
 observations=[json.loads(s) for s in pathlib.Path(args.observations).read_text().splitlines()]
 rows,report=join(observations,native,prefixes,args.allow_partial)
 data=''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows);(out/'regions.jsonl').write_text(data)
 (out/'native.stdout.snapshot').write_bytes(raw);(out/'prefix.features.snapshot').write_bytes(fraw);(out/'feature-join-source.py').write_bytes(pathlib.Path(__file__).read_bytes())
 report.update(schema='iris.empirical_runtime_feature_join.v1',status='partial' if report['partial'] else 'passed',
  source_sha256=sha_bytes(pathlib.Path(__file__).read_bytes()),observations_sha256=sha_bytes(pathlib.Path(args.observations).read_bytes()),
  native_stdout_prefix_sha256=sha_bytes(raw),features_prefix_sha256=sha_bytes(fraw),output_sha256=sha_bytes(data.encode()),
  native_stdout_snapshot_bytes=len(raw),features_snapshot_bytes=len(fraw),native_and_reference_ids_are_join_keys_only=True,global_heldout_timings_opened=False,live_quality_accepted=False,full_2pct_certified=False)
 (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({k:report[k] for k in ('status','reference_regions','joined_regions','partial')},indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--observations',default='calibration/empirical-v1/observations.jsonl');a.add_argument('--stdout',required=True);a.add_argument('--features',required=True);a.add_argument('--output',required=True);a.add_argument('--allow-partial',action='store_true');main(a.parse_args())
