#!/usr/bin/env python3
"""Audit actual source-Icache CSR observations without inventing receiver phases."""
import argparse,collections,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions
SOURCE='source-Icache-acceptedA-until-sampled-eighthD;line-owner-not-current-PC-owner'
PRIVATE='empirical-private-Icache-refill-owner'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def integer(x):return isinstance(x,int)and not isinstance(x,bool)and x>=0
def require(ok,reason):
 if not ok:raise ValueError(reason)
def row_check(r,insns,periods):
 h=r['hart'];t=r['read_cycle'];require(integer(h)and h<3 and integer(t),'hart/read clock');require(insns.read(r['pc'])==r['raw'],'ELF CSR word');require(r['csr']==r['raw']>>20 and r['csr']in(0xb00,0xc00),'counter identity');require(r['destination']==((r['raw']>>7)&31)and r['result_discarded']==(r['destination']==0),'counter destination');require(r['endpoint']=='get_csr_before_current_instruction_retirement','read endpoint');require(r['instruction_fetch_observation_scope']==(SOURCE if h<2 else PRIVATE),'physical frontend scope')
 f=r['pending_instruction_fetch'];sample=r['source_fetch_sampled_beats'];phase=r['source_fetch_clock_phase'];final=r['source_fetch_final_D_input_present'];require(isinstance(final,bool),'input presence type')
 if not f:
  require(sample is None and phase is None and not final,'absent accepted owner has receiver phase');return
 require(isinstance(f,dict)and integer(f['owner'])and f['owner']>0 and integer(f['node']),'owner identity');require(integer(f['address'])and integer(f['bytes'])and f['bytes']>0 and integer(f['submitted'])and f['submitted']<=t,'accepted timing');require(isinstance(f['issued'],bool),'issued type')
 if f['issued']:require(all(integer(f[k])for k in('start','end'))and f['submitted']<=f['start']<=t and f['start']<f['end'],'issued timing')
 else:require(f['start']is None and f['end']is None,'unissued node has timing')
 if h==2:
  require(sample is None and phase is None and not final,'private proxy has source receiver phase');require(not f['issued']or t<=f['end'],'private refill completed before uncleared owner');return
 require(f['address']%64==0 and f['bytes']==64 and f['l1misses']==1 and f['l2misses']in(0,1),'source line geometry');require(integer(sample)and sample<8 and isinstance(phase,dict),'source sampled count');require(set(phase)=={'next_source_edge','source_period','last_source_commit_edge','final_graph_completed'},'source phase schema');n,p,last,completed=phase['next_source_edge'],phase['source_period'],phase['last_source_commit_edge'],phase['final_graph_completed'];require(all(integer(x)for x in(n,p,last))and p==periods[h]and p>0 and last+p==n and last<=t<=n and n%p==0,'source clock phase');require(isinstance(completed,bool),'graph completion type');require(not final or sample==7,'final input sampled prefix');require(not completed or f['issued']and f['end']<=t and final and sample==7,'completed final callback/receiver identity')
 if not f['issued']:require(not completed and not final,'unissued final callback is present')
 elif f['end']>t:require(not completed and not final,'future final D already present')
 elif f['end']==t:require(completed==final,'same-edge final callback/input disagreement')
 else:require(completed and final and sample==7 and last<=f['end']<=t<=n,'older final D lacks bounded source receive phase')
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);run=a.run.resolve();receipt=json.loads((run/'run.json').read_text());require(receipt['status']=='completed_measured_regions_with_intentional_debugger_stop','incomplete native gate');argv=receipt['argv'];binary=Path(argv[0]);capsule=binary.parent;manifest=json.loads((capsule/'manifest.json').read_text());fixture=Path(next(x.split('=',1)[1]for x in argv if x.startswith('--iris-timing-fixture=')));elf=Path(argv[-1]);periods={int(x.split()[1]):int(x.split()[2])for x in fixture.read_text().splitlines()if x.startswith('hart ')};source=capsule/'src'/manifest['native_source_relative'];inputs=[Path(__file__).resolve(),run/'run.json',run/'features.jsonl',fixture,elf,binary,capsule/'libsifive_uart.so',capsule/'manifest.json',capsule/'verification.json',ROOT/'iris_model/guest_regions.py',source/'riscv/iris_counter_observations.cc',source/'riscv/iris_frontend.cc',source/'riscv/iris_empirical_features.inc',capsule/'src/pipeline/empirical_history.hpp',capsule/'src/pipeline/empirical_engine.cpp'];before={str(x):sha(x)for x in inputs};raw=(run/'features.jsonl').read_bytes();require(raw.endswith(b'\n'),'unterminated prefix');rows=[json.loads(x)for x in raw.splitlines()];insns=Instructions(elf);stats=collections.Counter();byhart={str(h):collections.Counter()for h in range(3)};samples=collections.Counter();phases=collections.Counter();witnesses={};lastseq={};owners={}
 for r in rows:
  row_check(r,insns,periods);h=r['hart'];require(h not in lastseq or r['sequence']>lastseq[h],'counter sequence reversed');lastseq[h]=r['sequence'];stats['prefixes']+=1;byhart[str(h)]['prefixes']+=1
  if h>=2:continue
  stats['source_scoped_prefixes']+=1;f=r['pending_instruction_fetch']
  if not f:stats['source_without_accepted_refill_owner']+=1;continue
  stats['source_active_refill']+=1;byhart[str(h)]['source_active_refill']+=1;s=r['source_fetch_sampled_beats'];phase=r['source_fetch_clock_phase'];samples[str(s)]+=1;key='source_issued'if f['issued']else'source_unissued';stats[key]+=1;stats['source_final_graph_completed']+=phase['final_graph_completed'];stats['source_final_D_input_present']+=r['source_fetch_final_D_input_present'];phases[str((r['read_cycle']-phase['last_source_commit_edge'],phase['next_source_edge']-r['read_cycle']))]+=1
  if f['issued']:key='end_before_read'if f['end']<r['read_cycle']else'end_at_read'if f['end']==r['read_cycle']else'end_after_read';stats[key]+=1
  if f['issued']and f['end']==0:stats['zero_end_sentinel']+=1
  if not(f['address']<=r['pc']<f['address']+64):stats['source_active_line_does_not_contain_CSR_PC']+=1
  owner=(h,f['owner']);identity=(f['node'],f['address'],f['bytes'],f['submitted'])
  if owner in owners:require(owners[owner][0]==identity and owners[owner][1]<=s,'source owner changed/reversed sample')
  owners[owner]=(identity,s)
  wkey=('unissued'if not f['issued']else'issued')+'-sample'+str(s);witnesses.setdefault(wkey,{k:r[k]for k in['hart','sequence','pc','read_cycle','pending_instruction_fetch','source_fetch_sampled_beats','source_fetch_final_D_input_present','source_fetch_clock_phase']})
 require(len(rows)==receipt['actual_CSR_ELF_boundary_joins'],'actual boundary count');require(stats['source_active_refill']>0,'no actual source refill witnesses');controls=[];valid=next(r for r in rows if r['hart']<2 and r['pending_instruction_fetch']and not r['pending_instruction_fetch']['issued'])
 mutations={'zero-owner':lambda x:x['pending_instruction_fetch'].update(owner=0),'unissued-zero-end':lambda x:x['pending_instruction_fetch'].update(end=0),'sample-eight':lambda x:x.update(source_fetch_sampled_beats=8),'next-before-read':lambda x:x['source_fetch_clock_phase'].update(next_source_edge=x['read_cycle']-1),'input-before-final':lambda x:x.update(source_fetch_final_D_input_present=True,source_fetch_sampled_beats=0),'unissued-completed':lambda x:x['source_fetch_clock_phase'].update(final_graph_completed=True),'absent-owner-with-phase':lambda x:x.update(pending_instruction_fetch=None),'wrong-raw':lambda x:x.update(raw=x['raw']^128)}
 for name,mutate in mutations.items():
  x=copy.deepcopy(valid);mutate(x)
  try:row_check(x,insns,periods)
  except ValueError as e:controls.append({'name':name,'rejected':True,'reason':str(e)})
  else:raise ValueError('corruption accepted: '+name)
 require(all(sha(x)==digest for x,digest in before.items()),'audit input changed');(out/'witnesses.json').write_text(json.dumps(witnesses,indent=2)+'\n');report={'schema':'iris.source_Icache.actual_prefix_phase_audit.v1','pass':True,'native_sha256':manifest['binary_sha256'],'input_sha256':before,'counts':dict(stats),'per_hart':{k:dict(v)for k,v in byhart.items()},'sampled_D_histogram':dict(samples),'phase_read_minus_last_and_next_minus_read':dict(phases),'unique_observed_source_owners':len(owners),'corruptions_rejected':controls,'witness_sha256':sha(out/'witnesses.json'),'retained_completed_final_graph_qualified':stats['source_final_graph_completed']>0,'older_held_D_phase_qualified':stats['end_before_read']>0,'zero_history_sentinel_seen':stats['zero_end_sentinel']>0,'source_scope':'accepted source IcacheA through receiving eighthD; line owner, not currentPC attribution; noacceptedowner is not proof of a drainedfrontend','temporal_bound_relaxation_required_by_this_run':stats['end_before_read']>0,'unobserved_receiver_phases_remain_unqualified':True,'timing_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json'),'counts':dict(stats)}))
if __name__=='__main__':main()
