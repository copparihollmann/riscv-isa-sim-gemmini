#!/usr/bin/env python3
"""Independent reader of actual native events, checked against frozen source proof.
No timing labels, source-state injection, or fitted offsets are used.
"""
import argparse,copy,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(v,s):
 if not v:raise ValueError(s)
def check(trace,prefix,sites,source):
 require(source['pass']is True and source['core_actual_runs']==48,'source proof unavailable')
 require(source['both_fences_have_identical_source_predicate_and_phase']is True,'source FENCE equivalence missing')
 fronts={};queues={0:[],1:[]};writes={};pub={};admit=[]
 for t in trace:
  event=t['event'];h=t.get('hart')
  if event=='opu_front_accept':
   key=(h,t['instruction']);require(key not in fronts,'duplicate command identity');fronts[key]=t
  elif event=='opu_queue_edge':queues[h].append(t)
  elif event=='opu_microissue_reserved':writes.setdefault((h,t['instruction']),[]).append(t)
  elif event=='opu_entry_publish':pub.setdefault((h,t['instruction']),[]).append(t)
  elif event=='opu_fence_admit':admit.append(t)
 for key,ps in pub.items():
  require(key in fronts,'publication without accepted command')
  require(all(t['cycle']>=fronts[key]['com']for t in ps),'numeric write before architectural COM')
 for key,ws in writes.items():
  require(key in fronts,'unowned physical microissue')
  require(all(t['seq']>=fronts[key]['backend_available']for t in ws),'microissue before accepted backend input')
 result=[]
 for a in admit:
  h=a['hart'];edge=a['cycle'];require(h in(0,1),'wrong hart')
  require(type(a['all_source_queues_front_busy_clear'])is bool and a['all_source_queues_front_busy_clear'],'unqualified busy control')
  require(type(a['pending_numeric_commands'])is int and a['pending_numeric_commands']>0,'numeric ownership must remain')
  require(a['raw']in(0x0330000f,0x0ff0000f),'excluded barrier admitted')
  require(a['pc']in sites and sites[a['pc']]==a['raw'],'ELF barrier mismatch')
  q=[v for v in queues[h]if v['cycle']<=edge];require(q,'missing source queue history');last=q[-1]
  require(last['cycle']<edge,'used post-edge empty state before next source edge')
  # In this finite stream the last source edge drains SEQ; no later command may
  # have entered the queue between that drain and FENCE admission.
  require(last['vdq_before']==0 and last['iq_before']==0 and last['seq_before']==1 and last['microissue']==1,'not the proved last-microissue boundary')
  owners=[]
  for key,ps in pub.items():
   if key[0]==h and any(v['cycle']>edge for v in ps)and fronts[key]['rrd']<=edge:
    require(fronts[key]['com']<=edge,'unretired front owner crossed fence')
    require(fronts[key]['backend_available']<=last['cycle'],'front command not handed off')
    owners.append(key)
  require(len(owners)==a['pending_numeric_commands'],'live numeric owners mismatch')
  future=[v for key in owners for v in pub[key]if v['cycle']>edge]
  require(future,'tail was erased at FENCE')
  require(all(v['cycle']in[w['write']for w in writes[(h,v['instruction'])]]for v in future),'publication not tied to a real physical write')
  nextcsr=[v for v in prefix if v['hart']==h and v.get('pc')==a['pc']+4 and edge<=v['read_cycle']<=edge+12]
  require(len(nextcsr)==1,'ambiguous or missing immediate source CSR read')
  require(nextcsr[0]['read_cycle']-edge==source['Core_next_CSR_COM_after_FENCE_RRD'],'FENCE to immediateCSR source phase mismatch')
  result.append({'hart':h,'barrier_raw':a['raw'],'barrier_PC':a['pc'],'last_source_busy_edge':last['cycle'],'FENCE_admission':edge,'future_MRF_write_edges':[v['cycle']for v in future],'following_CSR_read':nextcsr[0]['read_cycle'],'preserved_numeric_owners':len(owners)})
 require({(x['hart'],x['barrier_raw'])for x in result}=={(h,w)for h in(0,1)for w in(0x0330000f,0x0ff0000f)},'both source FENCE words/harts must activate')
 require(len(result)==4,'unexpected finite activation count')
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False)
 sourcefile=ROOT/'build/opu-fence-source-v1/report.json';source=json.load(open(sourcefile));build=ROOT/'build/opu-fence-finite-guest-v2/build.json';j=json.load(open(build));sites={v['pc']:v['raw']for v in j['barrier_sites'].values()};ins={str(p):sha(p)for p in(Path(__file__).resolve(),sourcefile,build)};runs=[];material=[]
 for seed in(0,17):
  p=ROOT/f'build/opu-fence-finite-ON-seed{seed}-v2';receipt=json.load(open(p/'report.json'));require(receipt['pass']is True and receipt['normal_HTIF_guest_exit']is True,'actual normal guest required')
  for n in('report.json','async.jsonl','features.jsonl'):ins[str(p/n)]=sha(p/n)
  tr=[json.loads(l)for l in(p/'async.jsonl').open()];pr=[json.loads(l)for l in(p/'features.jsonl').open()];result=check(tr,pr,sites,source);runs.append({'seed':seed,'witnesses':result});material.append((tr,pr))
 tr,pr=material[0];mutants=[]
 def rejected(name,t,p,s=source):
  try:check(t,p,sites,s)
  except ValueError as e:mutants.append({'name':name,'rejected':True,'reason':str(e)});return
  raise RuntimeError('corruption accepted: '+name)
 a0=next(t for t in tr if t['event']=='opu_fence_admit');idx=tr.index(a0)
 t=copy.deepcopy(tr);t[idx]['cycle']-=1;rejected('postedge-queue-empty-used-too-early',t,pr)
 t=copy.deepcopy(tr);t[idx]['raw']=0x0000100f;rejected('FENCE-I-illegally-relaxed',t,pr)
 t=copy.deepcopy(tr);t[idx]['pending_numeric_commands']=0;rejected('numeric-tail-erased',t,pr)
 t=copy.deepcopy(tr);t[idx]['all_source_queues_front_busy_clear']=1;rejected('busy-qualified-bool-replaced-by-int',t,pr)
 p=copy.deepcopy(pr);v=next(v for v in p if v['hart']==a0['hart']and v.get('pc')==a0['pc']+4 and a0['cycle']<=v['read_cycle']<=a0['cycle']+12);v['read_cycle']-=1;rejected('next-CSR-one-edge-early',tr,p)
 t=copy.deepcopy(tr);v=next(v for v in t if v['event']=='opu_entry_publish');key=(v['hart'],v['instruction']);front=next(x for x in t if x['event']=='opu_front_accept'and(x['hart'],x['instruction'])==key);v['cycle']=front['com']-1;rejected('physical-write-before-COM',t,pr)
 s=copy.deepcopy(source);s['both_fences_have_identical_source_predicate_and_phase']=False;rejected('missing-source-equivalence',tr,pr,s)
 # Actual OFF traces must match the frozen C12 parent exactly, including timing
 # prefixes/known values, rather than only the final arithmetic values.
 parity=[]
 for version in('v1','v2'):
  x=ROOT/f'build/opu-fence-finite-OFF-seed0-{version}';y=ROOT/f'build/opu-fence-finite-reference-OFF-seed0-{version}'
  for n in('stdout','stderr','features.jsonl','async.jsonl'):
   require((x/n).read_bytes()==(y/n).read_bytes(),'defaultOFF changed '+version+'/'+n);parity.append({'epoch':version,'artifact':n,'byte_identical':True,'sha256':sha(x/n)});ins[str(x/n)]=sha(x/n);ins[str(y/n)]=sha(y/n)
 report={'schema':'iris.opu_FM0_fence_native_phase_proof.v1','pass':True,'source_proof_sha256':sha(sourcefile),'actual_native_runs':runs,'corruption_controls':mutants,'default_OFF_parity':parity,'input_sha256':ins,'hardware_contacted':False,'full_CPU_VU_memory_timing_certified':False,'scope':'Finite M-mode h0/1 MM-only command bridge; all actual source queue/front controls cleared, conservative CPU/FADD/memory/IRQ quiescence. FENCE admission may precede numeric tail; immediate CSR retains sourceR+6 phase. No whole-SoC/loaded-image/2% claim.'};(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'actual_witnesses':sum(len(x['witnesses'])for x in runs),'rejected_corruptions':len(mutants),'OFF_byte_parity_artifacts':len(parity)}))
if __name__=='__main__':main()
