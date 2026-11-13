#!/usr/bin/env python3
"""Stdlib-only raw/canonical/CSR/metric review; never fits or changes inputs."""
import argparse,collections,hashlib,json,math,struct
from pathlib import Path
R=Path(__file__).resolve().parents[1]
ELF='6de1157eea2aeffa801e93edb4d85c60ee5a6b13b9ef3df9d527472711de7de9'
EXPECTED='e767646bf7bcdf7e6c491a10488bc80387b8fdc850362c01ac46388e980eccf5'
def need(x,why):
 if not x:raise ValueError(why)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def unique(pairs):
 d={}
 for k,v in pairs:need(k not in d,'Duplicate JSON key');d[k]=v
 return d
def js(raw):return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in()).throw(ValueError('Nonfinite JSON')))
def read(p):return js(Path(p).read_bytes())
def uint(x):return type(x)is int and 0<=x<1<<64
def same(a,b):return type(a)is type(b)and a==b
def equivalent(a,b):
 if isinstance(a,dict)and isinstance(b,dict):return set(a)==set(b)and all(equivalent(a[k],b[k])for k in a)
 if isinstance(a,list)and isinstance(b,list):return len(a)==len(b)and all(equivalent(x,y)for x,y in zip(a,b))
 if type(a)is float or type(b)is float:return type(a)in(int,float)and type(b)in(int,float)and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-10)
 return same(a,b)
def median(a):
 a=sorted(a);n=len(a);return a[n//2]if n%2 else(a[n//2-1]+a[n//2])/2

def canonical():
 out=[]
 for trial in range(3):
  for size in[2048,16384,131072,1048576,4194304]:
   for mask in range(1,8):
    parent='memory.footprint.%d.mask%d.trial%d'%(size,mask,trial);semantic='memory.footprint.%d.mask%d'%(size,mask)
    for p in range(2):
     for h in range(3):
      if mask&(1<<h):out.append(dict(case_id=parent+'.pass'+str(p),parent_case_id=parent,hart=h,trial_id=trial,pass_index=p,footprint_bytes=size,body_loads=size//64,requested_bytes=size//8,checksum=0x90000000+h*0x02000000+64*((17*trial+7*h)%(size//64)),mask=mask,active_harts=[i for i in range(3)if mask&(1<<i)],semantic_parent_case_id=semantic,internal_split='internal_validation'if int(hashlib.sha256(semantic.encode()).hexdigest()[:8],16)%5==0 else'train'))
 need(len(out)==360,'Canonical360 geometry');return out

def wire(text):
 rows=[];frontiers=[];done=[]
 for line in text.splitlines():
  if line.startswith('IRIS_REGION '):rows.append(js(line.split(' ',1)[1]))
  elif line.startswith('IRIS_FOOTPRINT_GROUP '):
   f=js(line.split(' ',1)[1]);need(f==dict(group=len(frontiers),records=len(rows))and all(type(v)is int for v in f.values())and len(rows)==24*(len(frontiers)+1),'Actual24-row group order');frontiers.append(f)
  elif line.startswith('IRIS_BATCH_DONE '):done.append(js(line.split(' ',1)[1]))
 need(len(rows)==360 and len(frontiers)==15,'All360+15frontiers');need(done==[dict(failed=0,cases=105,regions=360,trials=3)]and all(type(v)is int for v in done[0].values()),'Exact normal DONE')
 prev={};seen=set()
 for row,c in zip(rows,canonical()):
  for key in ['case_id','parent_case_id','hart','trial_id','pass_index','footprint_bytes','body_loads','requested_bytes','checksum']:need(same(row.get(key),c[key]),'Raw canonical identity '+key)
  need(row.get('pass')is True and row.get('expected_checksum')==c['checksum']and type(row.get('expected_checksum'))is int and row.get('suite')=='memory_footprints'and row.get('region')=='chase','Raw independent checksum/role')
  for key in ['start_cycle','end_cycle','instret_delta','mtime_before','mtime_after']:need(uint(row.get(key)),'Unsigned raw counter '+key)
  need(row['end_cycle']>row['start_cycle']>=prev.get(row['hart'],0)and row['instret_delta']>=3*c['body_loads']+1 and row['mtime_after']>=row['mtime_before'],'Raw counter/window progress');prev[row['hart']]=row['end_cycle'];key=(row['case_id'],row['hart']);need(key not in seen,'Raw duplicate');seen.add(key)
  for key,v in [('mtime_hz',500000),('source_core_cycles_per_mtime_tick',1000),('mtime_quantization_error_bound_core_cycles',1000),('mtime_scope','encloses_CSR_ROI_with_sampling_overhead')]:need(same(row.get(key),v),'Raw CLINT source scope '+key)
 return rows

def summaries(rows):
 errors=sorted(r['signed_error_percent']for r in rows);absolute=sorted(abs(e)for e in errors);hw=sum(r['hardware_cycles']for r in rows);sw=sum(r['software_cycles']for r in rows);n=len(rows)
 return dict(regions=n,median_signed_error_percent=median(errors),median_absolute_error_percent=median(absolute),p90_absolute_error_percent=absolute[(9*n+9)//10-1],max_absolute_error_percent=max(absolute),min_signed_error_percent=min(errors),max_signed_error_percent=max(errors),within_2percent=sum(e<=2 for e in absolute),within_2percent_fraction=sum(e<=2 for e in absolute)/n,hardware_cycle_sum=hw,software_cycle_sum=sw,cycle_sum_signed_error_percent=(sw-hw)*100/hw,instret_mismatches=sum(not r['instret_equal']for r in rows),CLINT_enclosing_window_intervals_overlap=sum(r['CLINT_enclosing_intervals_overlap']for r in rows))

def join(sw,prefix,elf):
 # Read the actual instruction bytes rather than importing the published joiner.
 raw=Path(elf).read_bytes();po=struct.unpack_from('<Q',raw,32)[0];ps,pn=struct.unpack_from('<HH',raw,54)
 def word(pc):
  hits=[]
  for i in range(pn):
   typ,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',raw,po+i*ps)
   if typ==1 and flags&1 and va<=pc and pc+4<=va+fs:hits.append(struct.unpack_from('<I',raw,off+pc-va)[0])
  need(len(hits)==1,'Unique executable CSR instruction');return hits[0]
 need(word(0x800006c4)==0xb0002873 and word(0x800006f8)==0xb0002673,'Exact actual ELF CSR opcodes');need(len(prefix)==720,'All720 raw prefixes')
 lookup=collections.defaultdict(list)
 for p in prefix:
  need(p['schema']=='iris.empirical.prefix.v1'and p['endpoint']=='get_csr_before_current_instruction_retirement'and p['csr']==0xb00 and p['result_discarded']is False,'Actual program-owned mcycle prefix');lookup[(p['hart'],p['pc'],p['value'])].append(p)
 used=set();joins=[]
 for r in sw:
  endpoints=[]
  for label,pc,raw,dst in [('start_cycle',0x800006c4,0xb0002873,16),('end_cycle',0x800006f8,0xb0002673,12)]:
   matches=lookup[(r['hart'],pc,r[label])];need(len(matches)==1,'Unique raw hart/PC/value endpoint');p=matches[0];need(p['raw']==raw and p['destination']==dst and uint(p['read_cycle'])and uint(p['sequence']),'Exact CSR raw/dst/time/sequence');key=(p['hart'],p['sequence']);need(key not in used,'Endpoint reused');used.add(key);endpoints.append(p)
  start,end=endpoints;need(start['sequence']<end['sequence']and start['read_cycle']<end['read_cycle'],'Forward source CSR owners');joins.append(dict(hart=r['hart'],case_id=r['case_id'],start_sequence=start['sequence'],end_sequence=end['sequence'],start_global_read_cycle=start['read_cycle'],end_global_read_cycle=end['read_cycle']))
 need(len(used)==720,'No omitted/unowned raw prefix');return joins

def compare(sw,hw,joins):
 rows=[]
 for s,h,j,c in zip(sw,hw,joins,canonical()):
  a=s['end_cycle']-s['start_cycle'];b=h['end_cycle']-h['start_cycle'];qsw=(s['mtime_after']-s['mtime_before'])*1000;qhw=(h['mtime_after']-h['mtime_before'])*1000;ls=max(0,qsw-1000);us=qsw+1000;lh=max(0,qhw-1000);uh=qhw+1000
  rows.append(dict(index=len(rows),case_id=c['case_id'],hart=c['hart'],footprint_bytes=c['footprint_bytes'],mask=c['mask'],pass_index=c['pass_index'],trial_id=c['trial_id'],internal_split=c['internal_split'],software_cycles=a,hardware_cycles=b,signed_error_percent=(a-b)*100/b,absolute_error_percent=abs(a-b)*100/b,cycle_difference=a-b,instret_equal=s['instret_delta']==h['instret_delta'],software_global_CSR_read_span=j['end_global_read_cycle']-j['start_global_read_cycle'],CLINT_enclosing_intervals_overlap=max(ls,lh)<=min(us,uh),CLINT_enclosing_difference_lower_source_core_cycles=ls-uh,CLINT_enclosing_difference_upper_source_core_cycles=us-lh,CLINT_enclosing_signed_error_lower_percent=100*(ls/uh-1),CLINT_enclosing_signed_error_upper_percent=100*(us/lh-1)if lh else None,software_CLINT=dict(mtime_before=s['mtime_before'],mtime_after=s['mtime_after'],mtime_delta=s['mtime_after']-s['mtime_before'],quantized_source_core_cycles=qsw,enclosing_window_lower_source_core_cycles=ls,enclosing_window_upper_source_core_cycles=us,quantized_enclosing_minus_mcycle_ROI=qsw-a,enclosing_minus_mcycle_ROI_lower_source_core_cycles=qsw-a-1000,enclosing_minus_mcycle_ROI_upper_source_core_cycles=qsw-a+1000),hardware_CLINT=dict(mtime_before=h['mtime_before'],mtime_after=h['mtime_after'],mtime_delta=h['mtime_after']-h['mtime_before'],quantized_source_core_cycles=qhw,enclosing_window_lower_source_core_cycles=lh,enclosing_window_upper_source_core_cycles=uh,quantized_enclosing_minus_mcycle_ROI=qhw-b,enclosing_minus_mcycle_ROI_lower_source_core_cycles=qhw-b-1000,enclosing_minus_mcycle_ROI_upper_source_core_cycles=qhw-b+1000)))
 return rows

def audit(output):
 need(not output.exists(),'Fresh independent review output');output.mkdir(parents=True);comparison=R/'build/memory-footprints-WFI-hybrid7bd5-comparison-v2';report_path=comparison/'report.json';need(sha(report_path)==EXPECTED,'Frozenv2 comparison hash');published=read(report_path);need(published['pass']is True and published['regions']==360 and published['parameters_refit']is False and published['global_heldout']is False,'Actual non-fitting360 comparison')
 ids={str(Path(__file__).resolve()):sha(__file__),str(report_path):sha(report_path)}
 for mapping in[published['input_sha256']]:
  for name,h in mapping.items():need(Path(name).is_absolute()and sha(name)==h,'Bound comparison input changed '+name);ids[name]=h
 for name,h in published['output_sha256'].items():need(sha(comparison/name)==h,'Bound comparison output changed');ids[str(comparison/name)]=h
 swdir=R/'build/memory-footprints-WFI-groups-hybrid7bd5-selected-v1';hwdir=R/'build/fpga-memory-footprints-WFI-v1-001-analysis';hwreport=read(hwdir/'report.json');sr=read(swdir/'run.json');csr=read(swdir/'CSR-endpoint-qualification.json');need(sr['pass']is True and sr['exit_status']==0 and sr['timed_out']is False and sr['ELF_sha256']==ELF and sha(hwdir/'observed.elf')==ELF,'Same ELF and actual normal software exit');need(hwreport['pass']is True and hwreport['regions']==360 and hwreport['archive_verified']is True,'Strict hardware full360 analysis')
 for m in[csr['input_sha256'],hwreport['input_sha256'],sr['output_sha256']]:
  for name,h in m.items():need(sha(name)==h,'Actual raw evidence changed '+name);ids[name]=h
 sw=wire((swdir/'stdout').read_text());hw=wire((hwdir/'uartlog').read_text());prefix=[js(l)for l in(swdir/'features.jsonl').read_text().splitlines()];joins=join(sw,prefix,hwdir/'observed.elf');need(joins==csr['joins'],'Independently reconstructed all360 CSR joins');rows=compare(sw,hw,joins);actual=[js(l)for l in(comparison/'regions.jsonl').read_text().splitlines()];need(len(actual)==360,'No output row omission')
 for r,a in zip(rows,actual):
  for key,value in r.items():need(equivalent(value,a.get(key)),'Output row arithmetic mismatch '+key)
 summary=summaries(rows);need(equivalent(summary,published['summary']),'Independent overall metrics differ');v1=read(R/'build/memory-footprints-WFI-hybrid7bd5-comparison-v1/report.json');need(equivalent(summary,v1['summary']),'v1/v2 metric drift')
 groups=read(comparison/'groups.json');fields={'by_hart':['hart'],'by_size':['footprint_bytes'],'by_mask':['mask'],'by_pass':['pass_index'],'by_trial':['trial_id'],'by_internal_split':['internal_split'],'by_hart_size_mask_pass':['hart','footprint_bytes','mask','pass_index']};group_checks=0
 for name,keys in fields.items():
  buckets=collections.defaultdict(list)
  for r in rows:buckets[tuple(r[k]for k in keys)].append(r)
  expected=[dict(zip(keys,key),**summaries(value))for key,value in sorted(buckets.items())];need(equivalent(expected,groups[name]),'Independent group metrics differ '+name);group_checks+=len(expected)
 controls=[]
 def rejected(name,fn):
  try:fn()
  except(ValueError,KeyError,TypeError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Independent review acceptedcorruption '+name)
 rejected('missingrow',lambda:wire('\n'.join(l for i,l in enumerate((swdir/'stdout').read_text().splitlines())if i!=next(i for i,l in enumerate((swdir/'stdout').read_text().splitlines())if l.startswith('IRIS_REGION ')))))
 rejected('missingCSRendpoint',lambda:join(sw,prefix[:-1],hwdir/'observed.elf'))
 import copy
 changed=copy.deepcopy(prefix);changed[0]['pc']+=2;rejected('wrongCSR_PC',lambda:join(sw,changed,hwdir/'observed.elf'))
 changed=copy.deepcopy(prefix);changed[0]['value']+=1;rejected('wrongCSR_value',lambda:join(sw,changed,hwdir/'observed.elf'))
 changed=copy.deepcopy(prefix);changed[0]['result_discarded']=True;rejected('discardedCSR',lambda:join(sw,changed,hwdir/'observed.elf'))
 # A reversed bound/window must be refused by raw checks, never repaired.
 raw=(swdir/'stdout').read_text().splitlines();i=next(i for i,l in enumerate(raw)if l.startswith('IRIS_REGION '));row=js(raw[i].split(' ',1)[1]);row['mtime_after']=row['mtime_before']-1;raw[i]='IRIS_REGION '+json.dumps(row);rejected('reversedCLINT',lambda:wire('\n'.join(raw)))
 spans=collections.defaultdict(collections.Counter)
 for r in rows:spans[r['hart']][r['software_global_CSR_read_span']-r['software_cycles']]+=1
 out=dict(schema='iris.independent_WFI_footprint_comparison_review.v1',**{'pass':True},reviewed_report_sha256=EXPECTED,all360canonical_raw_rows_recomputed=True,all720actual_ELF_CSR_endpoints_independently_joined=True,all_group_summaries_recomputed=group_checks,instret_mismatches=summary['instret_mismatches'],summary=summary,software_global_read_span_minus_program_mcycle_delta_by_hart={str(h):dict(counts)for h,counts in spans.items()},CLINT_raw_gap_ranges={k:[min(r[k+'_CLINT']['quantized_enclosing_minus_mcycle_ROI']for r in rows),max(r[k+'_CLINT']['quantized_enclosing_minus_mcycle_ROI']for r in rows)]for k in['software','hardware']},CLINT_duration_quantization_per_window_source_cycles=1000,CLINT_duration_difference_quantization_source_cycles=2000,CLINT_overlap_scope='Enclosing-duration intervals may agree under quantization; not actualcross-run timealignment/concurrency/2percentproof.',cycle_sum_scope='SUM of360per-hart measuredregions acrossoverlappingharts/differentfootprints/masks/passes/trials; weightedaggregate error ONLY, NOTendtoendelapsedtime or overallaccuracy.',end_to_end_timing_measured=False,whole_model_or_2percent_certified=False,overhead_subtracted=False,physical_cachemiss_DRAMlatency_traffic_claimed=False,source_loaded_image_attested=False,hardware_contacted=False,fitting_performed=False,protected_v6_or_operator_timing_labels_consumed=False,negative_controls=controls,input_sha256=ids)
 (output/'independent-regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in rows));(output/'report.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},regions=360,groups=group_checks,controls=len(controls),report_sha256=sha(output/'report.json'),summary=summary)))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.output.resolve())
