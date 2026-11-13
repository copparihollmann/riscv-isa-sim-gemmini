#!/usr/bin/env python3
"""Independent model-only FADD profile/event/edge audit; no hardware inputs."""
import argparse,bisect,collections,copy,hashlib,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'timing')]
from iris_model.guest_regions import Instructions

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def need(b,s):
 if not b:raise ValueError(s)
def main(a):
 run,profile,out=[p.resolve()for p in(a.run,a.profile,a.output)];need(not out.exists(),'Fresh output')
 receipt=json.loads((run/'run.json').read_text());rp=json.loads((profile/'report.json').read_text());need(receipt['pass']and rp['pass']and receipt['hardware_contacted']is False and receipt['reserved_timing_labels_consumed']is False,'Model-only complete input')
 inputs={}
 for x in(receipt,rp):
  for p,h in x['input_sha256'].items():need(sha(Path(p))==h,'Bound input changed '+p);inputs[p]=h
 for p,h in receipt['output_sha256'].items():need(sha(Path(p))==h,'Bound model output changed '+p);inputs[p]=h
 for p,h in rp['output_sha256'].items():need(sha(profile/p)==h,'Bound profile output changed '+p)
 build=ROOT/'build/rvv-compute-heldout-asm-v1';corpus=json.loads((build/'corpus.json').read_text())['cases'];regions=[json.loads(l)for l in(run/'regions.jsonl').read_text().splitlines()];reported={r['case_id']:r for r in json.loads((profile/'regions.json').read_text())};need(len(reported)==432,'All432 measured FP rows')
 commands={};front={};killed=set();issue=collections.defaultdict(dict);write=collections.defaultdict(dict);tail=b''
 for line in(run/'async.jsonl').open('rb'):
  if not line.endswith(b'\n'):tail=line;break
  e=json.loads(line);k=e['event']
  if k not in('fadd_EG_front_reservation','fadd_EG_wrongpath_cancel','fadd_EG_functional_COM','fadd_EG_microissue','fadd_EG_physical_write'):continue
  need(type(e['hart'])is int and e['hart']in(0,1)and type(e['generation'])is int and e['generation']>0,'Typed source owner');key=e['hart'],e['generation']
  if k=='fadd_EG_front_reservation':need(key not in front,'Unique reservation');front[key]=e
  if k=='fadd_EG_wrongpath_cancel':need(key not in killed,'Unique cancellation');killed.add(key)
  if k=='fadd_EG_functional_COM':need(key not in commands,'Unique COM');commands[key]=e
  if k in('fadd_EG_microissue','fadd_EG_physical_write'):
   b=issue if k=='fadd_EG_microissue'else write;need(e['index']not in b[key],'Unique perEG event');b[key][e['index']]=e
 need(set(commands)==set(issue)==set(write)and not(set(commands)&killed),'Complete owned work; no wrongpath credit')
 all_issues=collections.defaultdict(list);code=Instructions(build/'guest.elf',ROOT/'board/evidence/bootrom.rv64.img')
 for key,c in commands.items():
  need(c['geometry_authority']=='checked_architectural_COM'and c['new_flags']==0 and c['physical_VRF_restored']is True,'COM authority')
  need(c['raw']==code.read(c['pc'])and c['SEW']in(16,32,64)and c['LMUL_denominator']==1 and c['LMUL_numerator']in(1,2,4,8),'ELF/finite geometry')
  need(c['VL']==256//c['SEW']*c['LMUL_numerator']and front[key]['COM']==c['cycle'],'FullVL and actual COM')
  expected=set(range(c['VL']*c['SEW']//128));need(set(issue[key])==set(write[key])==expected,'All EGs')
  for i in expected:
   x,y=issue[key][i],write[key][i];need(type(x['cycle'])is int and type(y['cycle'])is int and x['cycle']>=c['cycle']+4 and y['cycle']==x['cycle']+4 and y['bytes']==16,'Source write phase')
   need(x['pc']==y['pc']==c['pc']and x['destination_EG']==2*c['vd']+i,'Exact source EG destination')
   all_issues[key[0]].append((x['cycle'],key,i))
 for h in all_issues:all_issues[h].sort()
 times={h:[x[0]for x in rows]for h,rows in all_issues.items()};credited=set();checks=[];totalissue=totalbusy=0
 for c,r in zip(corpus,regions):
  need(c['case_id']==r['case_id'],'Exact order')
  if c['kind']!='fp':continue
  h=c['hart'];lo,mid,hi=[r[n+'_global_read_cycle']for n in('begin','issue','drain')];need(lo<mid<=hi,'Counter order')
  keys={key for key,v in commands.items()if key[0]==h and lo<=v['cycle']<hi};need(len(keys)==c['n']*c['streams']and not(keys&credited),'Only measured commands');credited|=keys
  occupied=set();inflight=set();issued=set();elements=0
  for key in keys:
   v=commands[key];need(v['SEW']==c['sew']and v['VL']==c['vl']and v['cycle']<mid,'Measured geometry and issue boundary');elements+=v['VL'];last=max(x['cycle']for x in write[key].values());need(last<hi,'Tail fully inside region')
   inflight.update(range(v['cycle'],last+1))
   for i,x in issue[key].items():
    e=x['cycle'];need(lo<=e<e+4<hi and e not in issued,'One sourceEG per edge');issued.add(e)
    # Independently enumerate preedge valid0..3; no interval-union helper reused.
    occupied.update(range(e+1,e+5))
  loidx=bisect.bisect_right(times[h],lo-5);hiidx=bisect.bisect_left(times[h],hi-1)
  outside=[(e,key,i)for e,key,i in all_issues[h][loidx:hiidx]if key not in keys and e+1<hi and e+5>lo]
  need(not outside,'No warmup/carry-in/uncredited pipeline valid samples inside measured row')
  span=hi-lo;p=reported[c['case_id']];values=dict(measured_commands=len(keys),logical_add_elements=elements,source_global_CSR_span_cycles=span,program_mcycle_delta=r['end_cycle']-r['start_cycle'],source_pipeline_valid_cycles=len(occupied),source_pipeline_valid_fraction=len(occupied)/span,command_pending_union_cycles=len(inflight),source_EG_issue_slots=len(issued),achieved_elements_per_source_cycle=elements/span,conditional_peak_elements_per_source_cycle=128//c['sew'],fraction_of_conditional_element_peak=elements/(span*(128//c['sew'])),internal_VRF_numeric_write_bytes=len(issued)*16,logical_vector_source_operand_bytes=len(issued)*32)
  need(all(p[k]==v for k,v in values.items()),'Every independently recomputed profile metric matches '+c['case_id']);need(p['physical_memory_bytes']is None and p['physical_memory_bandwidth']is None,'No physical traffic inference')
  checks.append(dict(case_id=c['case_id'],commands=len(keys),source_pipeline_valid_cycles=len(occupied),carry_in_credits=0));totalissue+=len(issued);totalbusy+=len(occupied)
 need(len(checks)==432 and len(credited)==57600 and totalissue==432000,'Exact all432 measured workload')
 # Invoke the unmodified root decoder only for tiny isolated join controls.
 spec=importlib.util.spec_from_file_location('root_fadd_profile',ROOT/'timing/profile_fadd_eg_regions_v1.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);key=next(iter(commands));cmd=commands[key];f=front[key];iss=issue[key];wr=write[key];mod.qualify(key,cmd,f,iss,wr,code);controls=[]
 def refuses(name,fn):
  try:fn()
  except(ValueError,KeyError,AssertionError,TypeError,json.JSONDecodeError):controls.append(name);return
  raise ValueError('Control accepted: '+name)
 for field,value in [('geometry_authority','provisional_RRD'),('VL',cmd['VL']-1),('new_flags',1),('physical_VRF_restored',False),('raw',cmd['raw']^128)]:
  bad=copy.deepcopy(cmd);bad[field]=value;refuses('command_'+field,lambda bad=bad:mod.qualify(key,bad,f,iss,wr,code))
 bad=copy.deepcopy(f);bad['COM']+=1;refuses('wrong_COM_join',lambda:mod.qualify(key,cmd,bad,iss,wr,code))
 for label,mode in [('missing_EG','missing'),('wrong_write_bytes','bytes'),('late_write','late')]:
  bad=copy.deepcopy(wr);i=min(bad)
  if mode=='missing':bad.pop(i)
  elif mode=='bytes':bad[i]['bytes']=8
  else:bad[i]['cycle']+=1
  refuses(label,lambda bad=bad:mod.qualify(key,cmd,f,iss,bad,code))
 out.mkdir(parents=True,exist_ok=False)
 eventrows=[f,cmd]+list(iss.values())+list(wr.values())
 for name,rows in [('duplicate_reservation',eventrows+[f]),('duplicate_COM',eventrows+[cmd]),('duplicate_write',eventrows+[next(iter(wr.values()))]),('canceled_COM',eventrows+[dict(event='fadd_EG_wrongpath_cancel',hart=key[0],generation=key[1])]),('missing_COM',[e for e in eventrows if e['event']!='fadd_EG_functional_COM'])]:
  p=out/(name+'.jsonl');p.write_text(''.join(json.dumps(e)+'\n'for e in rows));refuses(name,lambda p=p:mod.events(p))
 rtl=ROOT/'build/saturn-timing-component-v1-final/build/saturn-timing-source-v1/compute/rtl';ex=(rtl/'ExecutionUnitfp.sv').read_text();fp=(rtl/'FPFMAPipe.sv').read_text()
 need(all(x in ex for x in ['pipe_valids_0 <= pipe_iss','pipe_valids_1 <= pipe_valids_0','pipe_valids_2 <= pipe_valids_1','pipe_valids_3 <= pipe_valids_2']),'Four actual source valid stages')
 need(fp.count('SegmentedFMAPipe pipe_out_fma_pipe')==2 and 'assign io_write_valid = io_pipe_3_valid' in fp,'Two64-bit segmented FP lanes and stage3 write')
 inputs.update({str(p):sha(p)for p in [Path(__file__).resolve(),profile/'report.json',profile/'regions.json',rtl/'ExecutionUnitfp.sv',rtl/'FPFMAPipe.sv',ROOT/'timing/rvv_fadd_eg_source_v1.hpp']})
 report=dict(schema='iris.independent_model_FADD_EG_profile_review.v1',**{'pass':True},actual_FP_regions=432,measured_COM_commands=len(credited),all_guest_COM_commands=len(commands),excluded_unmeasured_COM_commands=len(commands)-len(credited),measured_EG_issues=totalissue,measured_EG_writes=totalissue,independently_enumerated_pipeline_valid_samples=totalbusy,interval_formula='[issue_cycle+1, write_cycle+1) = [E+1,E+5), write_cycle=E+4; exactly4 preedge valid samples per issued EG',pipeline_scope='Union of actual valid entries in the source four-stage pipeline; not physical switching, FMA utilization or FPGA utilization',conditional_peak_scope='Actual1EG/edge and two64-bit segmented FMA lanes; 128/SEW full unmasked IEEE16/32/64 only; independent issue and no backpressure needed',command_inflight_scope='Separate COM-to-final-write inclusive union; includes unqualified CPU COM+1 bridge/queue wait',actual_warmup_or_carryin_credits=0,wrongpath_commands_credited=0,all_metrics_recomputed_exact=True,negative_join_controls=controls,negative_control_count=len(controls),unterminated_observer_tail_bytes=len(tail),whole_journal_complete=not bool(tail),selected_FP_regions_complete=True,VRF_bytes_are_not_memory_traffic=True,hardware_labels_opened=False,source_image_attested=False,source_or_runtime_edits=False,input_sha256=inputs)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'region-checks.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(dict(pass_=True,report_sha256=sha(out/'report.json'),regions=len(checks),controls=len(controls))))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__)
 for n in('run','profile','output'):p.add_argument('--'+n,type=Path,required=True)
 main(p.parse_args())
