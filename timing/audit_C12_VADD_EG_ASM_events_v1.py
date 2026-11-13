#!/usr/bin/env python3
"""Model event ownership proof only; no timing references or data fitting."""
from pathlib import Path
import collections,hashlib,json
R=Path(__file__).resolve().parents[1];P=R/'build/rvv-compute-asm-C12-VADD-EG-ON-v1';O=R/'build/C12-VADD-EG-ASM-event-audit-v1';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();run=json.loads((P/'run.json').read_text());assert run['pass']is True
front={};com={};cancel=set();issue={};writes=collections.Counter();mmcom={};reserved={};kmicro={};kwrite={};kinds=collections.Counter();tail=b'';fences=0;vrfbytes=0
with(P/'async.jsonl').open('rb')as f:
 for raw in f:
  if not raw.endswith(b'\n'):tail=raw;break
  e=json.loads(raw);kind=e['event'];kinds[kind]+=1
  if kind.startswith('vadd_EG_')and kind not in('vadd_EG_counter_read','vadd_EG_fence_admit'):
   key=e['hart'],e['generation']
   if kind=='vadd_EG_front_reservation':assert key not in front;front[key]=e
   elif kind=='vadd_EG_functional_COM':
    assert key in front and key not in com and key not in cancel and e['cycle']==front[key]['COM']and e['geometry_authority']=='checked_architectural_COM'
    assert e['SEW']in(8,16,32,64)and e['LMUL_numerator']in(1,2,4,8)and e['LMUL_denominator']==1 and e['VL']==256//e['SEW']*e['LMUL_numerator'];assert e['raw']==0x02000057|(e['vs2']<<20)|(e['vs1']<<15)|(e['vd']<<7);com[key]=e
   elif kind=='vadd_EG_wrongpath_cancel':assert key in front and key not in com and key not in cancel;cancel.add(key)
   elif kind=='vadd_EG_microissue':
    assert key in com and key not in cancel;ik=(*key,e['index']);assert ik not in issue and e['cycle']>=com[key]['cycle']+4;issue[ik]=e['cycle']
   elif kind=='vadd_EG_physical_write':
    assert key in com and key not in cancel;ik=(*key,e['index']);assert ik in issue and e['cycle']==issue[ik]+1 and e['bytes']==16 and e['index']==writes[key];writes[key]+=1;vrfbytes+=16
  elif kind=='vadd_EG_fence_admit':assert e['pending']==0 and e['controller_empty']is True and(not e['last_preedge_busy']or e['cycle']>e['last_controller_edge']);fences+=1
  key=e.get('hart'),e.get('instruction')
  if kind=='opu_functional_COM':
   assert key not in mmcom and e['geometry_authority']=='checked_architectural_COM'and e['kind']=='matrix_multiply';assert(e['TM'],e['TN'],e['TK'])==(e['controller_TM'],e['controller_TN'],e['controller_TK']);assert(e['raw']&0x7f)==0x77 and e['destination_encoding']==(e['raw']>>7)&31 and e['vs1']==(e['raw']>>15)&31 and e['vs2']==(e['raw']>>20)&31;mmcom[key]=e
  elif kind=='opu_microissue_reserved':
   k=key,e['entry'],e['seq'];assert k not in reserved;reserved[k]=e
  elif kind=='opu_K_microissue':
   k=key,e['entry'],e['cycle'];assert k not in kmicro;kmicro[k]=e
  elif kind=='opu_K_write_owner':
   k=key,e['entry'],e['k'];assert k not in kwrite and key in mmcom and type(e['last_k'])is bool and type(e['projected_MRF_published'])is bool and e['projected_MRF_published']==e['last_k'];kwrite[k]=e
assert set(front)==set(com)|cancel and not(set(com)&cancel)and set(writes)==set(com)
for key,c in com.items():assert writes[key]==2*c['LMUL_numerator']
for(key,entry,seq),r in reserved.items():
 k=kmicro[key,entry,seq];w=kwrite[key,entry,k['k']];assert w['cycle']==r['write']and w['macs']==r['macs']==k['macs']and w['last_k']==bool(k['last_k'])and w['cells']==w['macs'];assert w['last_k']==(w['k']+1==mmcom[key]['TK'])and mmcom[key]['cycle']<seq
assert len(kwrite)==len(reserved)==len(kmicro)and mmcom
for key,c in mmcom.items():assert sum(w['macs']for(owner,entry,k),w in kwrite.items()if owner==key)==c['TM']*c['TN']*c['TK']
assert tail and b'vadd_EG'not in tail and b'opu_'not in tail,'Partial authoritative source-unit event would withhold complete journal claim'
base=R/'build/rvv-compute-asm-C12-source-composite-ownzero-ON-v2';old=[json.loads(l)for l in(base/'regions.jsonl').read_text().splitlines()];new=[json.loads(l)for l in(P/'regions.jsonl').read_text().splitlines()];assert len(old)==len(new)==1320
mismatch={k:sum(a[k]!=b[k]for a,b in zip(old,new))for k in('instret_delta','issue_instret_delta','drain_instret_delta','checksum','expected_checksum','checked_words','mismatch_or')};assert not any(mismatch.values())
r=dict(schema='iris.C12_integer_VADD_EG_ASM_event_audit.v1',**{'pass':True},source_VADD_front_reservations=len(front),architectural_VADD_COM=len(com),preCOM_annulled=len(cancel),source_VADD_microissues=len(issue),source_VADD_16B_writes=sum(writes.values()),source_VADD_internal_VRF_bytes=vrfbytes,source_microissue_to_write_edges=1,VADD_all_owner_COM_geometry_and_write_joins_complete=True,VADD_lastwrite_preedge_FENCE_guard_admissions=fences,OPU_actual_COM_commands=len(mmcom),OPU_entry_K_write_completions=len(kwrite),OPU_actual_logical_MAC_completions=sum(e['macs']for e in kwrite.values()),OPU_all_COM_entry_K_geometry_joins_complete=True,OPU_intermediate_K_projected_MRF_published=False,TMOVE_authoritative_journal_qualified=False,full1320_all_numeric_and_phase_instret_mismatches=mismatch,partial_global_tail_bytes=len(tail),partial_global_tail_sha256=hashlib.sha256(tail).hexdigest(),partial_global_tail_description=tail.decode(errors='replace'),global_transcript_complete=False,source_VADD_and_OPU_authoritative_event_journals_complete=True,normal_guest_exit_verified=False,intentional_postmeasurement_debugger_stop=True,CPU_COMplus1_bridge_qualified=False,physical_hardware_utilization_or_memory_traffic_claim=False,hardware_or_protected_labels_consumed=False,parameters_fitted=False,event_counts=dict(kinds),input_sha256={str(p):sha(p)for p in(Path(__file__),P/'run.json',P/'async.jsonl',P/'regions.jsonl',base/'regions.jsonl',R/'build/C12-VADD-EG-frozen-35a80496-v2/manifest.json')});(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in('pass','architectural_VADD_COM','source_VADD_microissues','OPU_actual_COM_commands','OPU_entry_K_write_completions','partial_global_tail_bytes')}))
