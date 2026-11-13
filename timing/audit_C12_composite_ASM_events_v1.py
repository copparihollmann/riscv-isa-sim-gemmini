#!/usr/bin/env python3
"""Join model source-EG events only; no hardware labels or traffic inference."""
from pathlib import Path
import json,hashlib,collections
R=Path(__file__).resolve().parents[1];P=R/'build/rvv-compute-asm-C12-source-composite-ownzero-ON-v2';O=R/'build/C12-source-composite-ASM-event-audit-v1';O.mkdir();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();run=json.loads((P/'run.json').read_text());assert run['pass']is True
front={};committed={};killed=set();issued={};writes=collections.Counter();kinds=collections.Counter();fences=0;counter=0;partial=b''
with(P/'async.jsonl').open('rb')as f:
 for raw in f:
  if not raw.endswith(b'\n'):partial=raw;break
  e=json.loads(raw);kind=e['event'];kinds[kind]+=1
  if kind.startswith('fadd_EG_')and kind not in('fadd_EG_counter_read','fadd_EG_fence_admit'):
   key=e['hart'],e['generation']
   if kind=='fadd_EG_front_reservation':assert key not in front;front[key]=e
   elif kind=='fadd_EG_functional_COM':
    assert key in front and key not in committed and key not in killed
    assert e['cycle']==front[key]['COM']and e['geometry_authority']=='checked_architectural_COM'
    assert e['LMUL_numerator']in(1,2,4,8)and e['LMUL_denominator']==1 and e['VL']==256//e['SEW']*e['LMUL_numerator']
    assert e['raw']==(0x02001057|(e['vs2']<<20)|(e['vs1']<<15)|(e['vd']<<7))
    committed[key]=e
   elif kind=='fadd_EG_wrongpath_cancel':assert key in front and key not in committed and key not in killed;killed.add(key)
   elif kind=='fadd_EG_microissue':
    assert key in committed and key not in killed
    ikey=(*key,e['index']);assert ikey not in issued;assert e['cycle']>=committed[key]['cycle']+4;issued[ikey]=e['cycle']
   elif kind=='fadd_EG_physical_write':
    assert key in committed and key not in killed
    ikey=(*key,e['index']);assert ikey in issued and e['cycle']==issued[ikey]+4 and e['bytes']==16
    assert e['index']==writes[key];writes[key]+=1
  elif kind=='fadd_EG_fence_admit':
   assert e['pending']==0 and e['controller_empty']is True
   assert not e['last_preedge_busy']or e['cycle']>e['last_controller_edge'];fences+=1
  elif kind=='fadd_EG_counter_read':assert e['architecturally_retired']is True;counter+=1
assert set(front)==set(committed)|killed and not(set(committed)&killed)
assert set(writes)==set(committed)
for key,c in committed.items():assert writes[key]==2*c['LMUL_numerator']
assert partial and b'fadd_EG'not in partial,'Incomplete sourceFADD event would withhold full sourceFADD transcript claim'
base=R/'build/rvv-compute-asm-C12-ownzero-v1';old=[json.loads(x)for x in(base/'regions.jsonl').read_text().splitlines()];new=[json.loads(x)for x in(P/'regions.jsonl').read_text().splitlines()];assert len(old)==len(new)==1320
mismatches={k:sum(a[k]!=b[k]for a,b in zip(old,new))for k in('instret_delta','issue_instret_delta','drain_instret_delta','checksum','expected_checksum','checked_words','mismatch_or')};assert not any(mismatches.values())
r=dict(schema='iris.C12_source_composite_ASM_event_audit.v1',**{'pass':True},native_binary_sha256=run['input_sha256'][str(R/'build/C12-source-composite-frozen-02b4a9ab-v2/spike')],source_FADD_front_reservations=len(front),architectural_COM_commands=len(committed),preCOM_cancelled=len(killed),source_EG_microissues=len(issued),physical_internal_16B_VRF_writes=sum(writes.values()),all_FADD_COM_geometry_and_issue_write_joins_complete=True,all_FADD_accepted_owners_complete_or_annulled=True,source_issue_to_write_edges=4,successful_counter_records=counter,FADD_FENCE_admission_records=fences,final_write_edge_FENCE_busy=True,full_global_trace_claim=False,partial_final_tail_bytes=len(partial),partial_final_tail_sha256=hashlib.sha256(partial).hexdigest(),partial_tail_description=partial.decode(errors='replace'),event_counts=dict(kinds),all1320_numeric_and_phase_instret_mismatches=mismatches,normal_guest_exit_verified=False,intentional_postmeasurement_debugger_stop=True,hardware_or_reserved_labels_consumed=False,physical_hardware_utilization_or_memory_bandwidth_claim=False,input_sha256={str(p):sha(p)for p in(Path(__file__),P/'run.json',P/'async.jsonl',P/'regions.jsonl',base/'regions.jsonl',R/'build/C12-source-composite-frozen-02b4a9ab-v2/manifest.json')});(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in('pass','architectural_COM_commands','source_EG_microissues','physical_internal_16B_VRF_writes','partial_final_tail_bytes')}))
