#!/usr/bin/env python3
"""Independent raw journal arithmetic/ROI/source-phase audit; no HW labels."""
import argparse,bisect,collections,hashlib,json,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(v,s):
 if not v:raise ValueError(s)
def union(rows):
 points=[]
 for a,b in rows:points.extend([(a,1),(b,-1)])
 points.sort();active=0;last=0;total=0
 for t,d in points:
  if active:total+=t-last
  active+=d;last=t
 return total
class Code:
 def __init__(self,path,rom):
  raw=Path(path).read_bytes();need(raw[:7]==b'\x7fELF\x02\x01\x01','Actual RV64 ELF');self.spans=[];off=struct.unpack_from('<Q',raw,32)[0];size,n=struct.unpack_from('<HH',raw,54)
  for i in range(n):
   typ,flags,o,a,_,length,_,_=struct.unpack_from('<IIQQQQQQ',raw,off+i*size)
   if typ==1 and flags&1:self.spans.append((a,raw[o:o+length]))
  self.spans.append((0x10000,Path(rom).read_bytes()))
 def read(self,pc):
  for base,data in self.spans:
   i=pc-base
   if 0<=i and i+2<=len(data):
    lo=int.from_bytes(data[i:i+2],'little');n=4 if lo&3==3 else 2;need(i+n<=len(data),'Truncated code');return int.from_bytes(data[i:i+n],'little')
  raise ValueError('PC outside actual code')
def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False)
 delivery=ROOT/'build/source-event-profile-v2-delivery-v1';manifest=delivery/'manifest.json';need(sha(manifest)=='dc4a61f29562959e5983e4371cac1792932e6405315cad7258813dfe688a06fe','Frozen v2 delivery');m=json.loads(manifest.read_text())
 for name,h in m['artifact_sha256'].items():need(sha(delivery/name)==h,'Delivery artifact changed')
 for name,h in m['input_sha256'].items():need(sha(name)==h,'Delivery input changed '+name)
 for name,h in m['main_profile_output_sha256'].items():need(sha(name)==h,'Actual profile output changed')
 run=ROOT/'build/rvv-compute-asm-C12-VADD-EG-ON-v1';elf=ROOT/'build/rvv-compute-asm-v5/guest.elf';rom=ROOT/'board/evidence/bootrom.rv64.img';nm=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm');code=Code(elf,rom);observed=json.loads((Path(m['main_profile'])/'summary.json').read_text());commands={};front={};canceled=set();qspans=collections.defaultdict(list);pipes=collections.defaultdict(list);ages=collections.defaultdict(list);micro={};reserves={};callbacks={};projections=set();pubs=collections.defaultdict(list);counts=collections.Counter();tail=b'';horizon=0;depths=collections.Counter()
 symbols=[]
 for line in subprocess.check_output([str(nm),'-S','-n','--defined-only',str(elf)],text=True).splitlines():
  f=line.split(maxsplit=3)
  if len(f)==4 and f[2]in('T','t','W','w')and int(f[1],16):symbols.append((int(f[0],16),int(f[0],16)+int(f[1],16),f[3]))
 symbols.sort();starts=[s[0]for s in symbols]
 def function(pc):
  i=bisect.bisect_right(starts,pc)-1;return symbols[i][2]if i>=0 and pc<symbols[i][1]else None
 with(run/'async.jsonl').open('rb')as stream:
  for line in stream:
   if not line.endswith(b'\n'):tail=line;break
   e=json.loads(line);kind=e['event'];counts[kind]+=1
   for f in('cycle','read_cycle','RRD','rrd','seq'):
    if f in e:horizon=max(horizon,e[f])
   unit='VADD'if kind.startswith('vadd_EG_')else'FADD'if kind.startswith('fadd_EG_')else'OPU'if kind.startswith('opu_')and'instruction'in e else None
   if kind=='opu_queue_edge':
    if e['vdq_before']or e['iq_before']or e['seq_before']:qspans[e['hart']].append((e['cycle'],e['cycle']+1))
   if unit is None:continue
   key=unit,e['hart'],e['instruction']if unit=='OPU'else e.get('generation')
   if kind in('opu_front_accept','vadd_EG_front_reservation','fadd_EG_front_reservation'):need(key not in front,'Duplicate front');front[key]=e
   elif kind.endswith('functional_COM'):
    need(key in front and key not in commands and key not in canceled,'Authoritative actual COM owner');need(code.read(e['pc'])==e['raw']and e['geometry_authority']=='checked_architectural_COM','Actual COM ELF');commands[key]=dict(COM=e,front=front[key],issues={},writes={})
   elif kind in('opu_front_cancel','vadd_EG_wrongpath_cancel','fadd_EG_wrongpath_cancel'):need(key not in commands,'Canceled work cannot commit');canceled.add(key)
   elif kind in('vadd_EG_microissue','fadd_EG_microissue'):
    r=commands[key];need(e['index']not in r['issues'],'Duplicate EG issue');need(e['destination_EG']==2*r['COM']['vd']+e['index'],'Actual EG destination');r['issues'][e['index']]=e['cycle']
   elif kind in('vadd_EG_physical_write','fadd_EG_physical_write'):
    r=commands[key];c=r['COM'];index=e['index'];need(index not in r['writes'],'Duplicate source write');t=r['issues'][index];depth=1 if unit=='VADD'else 4;need(e['cycle']==t+depth and e['bytes']==16 and e['pc']==c['pc'],'Source pipe write edge');r['writes'][index]=(e['cycle'],128//c['SEW'],16,False);pipes[unit,e['hart']].append((t+1,e['cycle']+1))
   elif kind=='opu_K_microissue':micro[key,e['entry'],e['k']]=e
   elif kind=='opu_microissue_reserved':reserves[key,e['entry'],e['seq']]=e
   elif kind=='opu_K_completion':callbacks[key,e['cycle']]=e
   elif kind=='opu_entry_publish':projections.add((key,e['cycle']))
   elif kind=='opu_K_write_owner':
    r=commands[key];c=r['COM'];tag=e['entry'],e['k'];issue=micro[(key,*tag)];reserve=reserves[key,e['entry'],issue['cycle']];fp=c['family']=='vme.fp8';depth=3 if fp else 1;need(e['cycle']==issue['cycle']+depth==reserve['write'],'Actual OPU source response depth');depths[c['family'],depth]+=1
    local=e['entry']-4*c['tile'];row,col=local//2,local%2;cells=max(0,min(16,c['TM']-16*row))*max(0,min(16,c['TN']-16*col));last=e['k']==c['TK']-1
    need(cells>0 and cells==e['cells']==e['macs']==issue['macs']==reserve['macs'],'Independent OPU cells/MAC');need(e['last_k']==e['projected_MRF_published']==issue['last_k']==last,'Only final K projects final MRF');need(((key,e['cycle'])in projections)==last,'Actual MRF projection record');cb=callbacks[key,e['cycle']];need(cb['k']==e['k']and cb['cells']==cells and bool(cb['last_k'])==last,'Actual K callback');need(tag not in r['writes'],'No double K credit');r['writes'][tag]=(e['cycle'],cells,0,last)
 need(set(front)==set(commands)|canceled and not(set(commands)&canceled),'Every front owner closed or canceled')
 totals={};funcs={};owner_index={};bygroup=collections.defaultdict(list)
 def metric():return dict(checked_COM_commands=0,retired_logical_work=0,complete_publication_groups=0,actual_completed_logical_work=0,actual_internal_VRF_write_bytes=0,final_MRF_entry_publications=0)
 for key,r in commands.items():
  unit,h,ident=key;c=r['COM'];f=r['front'];need(c['cycle']==f['com'if unit=='OPU'else'COM'] and c['cycle']==f['rrd'if unit=='OPU'else'RRD']+3,'Actual front/COM phase');family=c['family']if unit=='OPU'else'rvv.integer.vadd'if unit=='VADD'else'rvv.fp.fadd';sew=None if unit=='OPU'else c['SEW'];group=h,family,sew;fn=function(c['pc']);retired=c['TM']*c['TN']*c['TK']if unit=='OPU'else c['VL'];bygroup[group].append((c['cycle'],key));need(len(r['writes'])==(((c['TM']+15)//16)*((c['TN']+15)//16)*c['TK']if unit=='OPU'else 2*c['LMUL_numerator']),'Every source microgroup written');need(sum(w[1]for w in r['writes'].values())==retired,'Retired and actual logical work agree only complete owners');last=max(w[0]for w in r['writes'].values());rrd=f['rrd'if unit=='OPU'else'RRD'];ages[unit,h].append((rrd,last+1));owner_index[key]=dict(COM=c['cycle'],last=last,work=retired)
  delta=dict(checked_COM_commands=1,retired_logical_work=retired,complete_publication_groups=len(r['writes']),actual_completed_logical_work=sum(w[1]for w in r['writes'].values()),actual_internal_VRF_write_bytes=sum(w[2]for w in r['writes'].values()),final_MRF_entry_publications=sum(w[3]for w in r['writes'].values()))
  for bucket in(totals.setdefault(group,metric()),funcs.setdefault((*group,fn),metric())):
   for n,v in delta.items():bucket[n]+=v
  for t,w,b,lastK in r['writes'].values():pubs[group].append((t,w,c['cycle'],b,lastK,key))
 for values in pubs.values():values.sort(key=lambda v:v[0])
 pub_times={g:[v[0]for v in values]for g,values in pubs.items()}
 for values in bygroup.values():values.sort()
 com_times={g:[v[0]for v in values]for g,values in bygroup.items()}
 for r in observed['whole_program']:
  key=r['hart'],r['family'],r['SEW'];need(all(r[n]==v for n,v in totals[key].items()),'Wholeprogram source work/count mismatch');cap=(256 if r['family'].startswith('vme.')else 128//r['SEW']);need(r['conditional_source_capacity_per_core_edge']==cap and r['physical_utilization']is False,'Conditional source capacity units');need(abs(r['fraction_of_conditional_source_ceiling']-totals[key]['actual_completed_logical_work']/horizon/cap)<1e-15,'Observed-clock conditional fraction')
 for r in observed['per_function']:
  need(all(r[n]==v for n,v in funcs[r['hart'],r['family'],r['SEW'],r['function']].items()),'Actual ELF function attribution mismatch')
 need(len(totals)==len(observed['whole_program'])and len(funcs)==len(observed['per_function']),'No dropped source/function groups')
 b=observed['busy_and_age'];need(b['completed_source_pipe_valid_union_global_cycles']=={f'{u}.hart{h}':union(v)for(u,h),v in pipes.items()},'Independent preedge source-valid union');need(b['observed_OPU_controller_preedge_busy_union_global_cycles']=={str(h):union(v)for h,v in qspans.items()},'Independent sampled controller busy union');need(b['bookkeeping_owner_age_union_global_cycles']=={f'{u}.hart{h}':union(v)for(u,h),v in ages.items()},'Independent owner-age union');need(b['OPU_numeric_pipe_valid_union_global_cycles']is None,'Unobserved OPU numeric-pipe occupancy must remain unknown')
 prefix={};lastseq={};prefixcount=0;prefixmax=0
 for line in(run/'features.jsonl').open():
  p=json.loads(line);h=p['hart'];need(p['sequence']>lastseq.get(h,-1),'Actual source CSR sequence');lastseq[h]=p['sequence'];need(code.read(p['pc'])==p['raw']and p['csr']==p['raw']>>20 and p['destination']==(p['raw']>>7)&31,'Independent actual ELF CSR');prefixcount+=1;prefixmax=max(prefixmax,p['read_cycle'])
  if not p['result_discarded']:need((h,p['value'])not in prefix,'Returning MCYCLE endpoints unique');prefix[h,p['value']]=p
 regions=json.loads((ROOT/'build/source-profile-35a-fullASM-inputs-v2/regions.json').read_text())['regions'];need(len(regions)==len(observed['regions'])==1320,'Every explicit ROI retained');regiongroups=0
 for want,got in zip(regions,observed['regions']):
  h=want['hart'];lo=prefix[h,want['start_cycle']]['read_cycle'];hi=prefix[h,want['end_cycle']]['read_cycle'];need(got['case_id']==want['case_id']and(got['global_begin'],got['global_end'])==(lo,hi),'Actual mcycle→global returning endpoints');need(got['program_mcycle_delta']==want['end_cycle']-want['start_cycle']and got['source_global_span_cycles']==hi-lo,'MCYCLE and global spans distinct')
  for row in got['source_completed_work']:
   key=h,row['family'],row['SEW'];values=pubs[key];times=pub_times[key];selected=values[bisect.bisect_left(times,lo):bisect.bisect_left(times,hi)];ct=com_times[key];starts_in=bygroup[key][bisect.bisect_left(ct,lo):bisect.bisect_left(ct,hi)]
   need(row['actual_completed_logical_work']==sum(x[1]for x in selected)and row['complete_publication_groups']==len(selected)and row['actual_internal_VRF_write_bytes']==sum(x[3]for x in selected)and row['final_MRF_entry_publications']==sum(x[4]for x in selected),'Independent region actual-write work');need(row['completed_carry_in_groups']==sum(x[2]<lo for x in selected),'Carry-in stays separate');need(row['checked_COM_commands_started_in_window']==len(starts_in),'Actual region COM starts');regiongroups+=1
 need(observed['actual_ELF_qualified_mcycle_prefixes']==prefixcount==3960 and observed['observed_global_cycle_horizon']==horizon,'Observed clock/prefix count');need(len(tail)==156 and observed['journal_complete']is False and observed['normal_execution_complete']is False,'Debugger partial global transcript honest');need(observed['wrongpath_or_reserved_work_credited']is False and observed['OPU_intermediate_K_MRF_values_materialized']is False,'No reserved or intermediate MRF credit');need(all(observed[n]is None for n in('physical_memory_traffic_bytes','physical_bandwidth','physical_roofline'))and observed['source_image_attested']is False,'Unavailable physical claims remain null/false')
 report=dict(schema='iris.independent_source_event_profiler_v2_audit.v1',**{'pass':True},hardware_or_protected_labels_accessed=False,new_source_or_native_mutations=False,commands=len(commands),whole_program_groups=len(totals),functions=len(funcs),actual_ELF_CSR_prefixes=prefixcount,explicit_total_ROIs=1320,actual_ROI_endpoint_joins=2640,region_source_work_groups=regiongroups,source_pipe_interval='[issue+1,write+1); VADD1/FADD4 preedge samples; dividers1inthisexactjournal',OPU_source_write_depth_counts={str(k):v for k,v in depths.items()},sampled_OPU_controller_busy_not_numeric_pipe=True,owner_age_not_source_busy=True,all_work_and_function_and_ROI_counts_independently_equal=True,whole_program_journal_partial_tail_bytes=len(tail),prefix_max_global_read_cycle=prefixmax,source_journal_observed_horizon=horizon,physical_utilization_traffic_roofline_unavailable=True,input_sha256={str(p):sha(p)for p in(Path(__file__).resolve(),manifest,ROOT/'iris_model/source_event_profile_v2.py',ROOT/'iris_model/source_profile_run_v2.py',run/'async.jsonl',run/'features.jsonl',elf,rom,nm,Path(m['main_profile'])/'summary.json',ROOT/'build/source-profile-35a-fullASM-inputs-v2/regions.json')})
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,commands=len(commands),ROIs=1320,report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()
