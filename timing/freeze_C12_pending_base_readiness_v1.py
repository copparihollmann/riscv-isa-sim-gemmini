#!/usr/bin/env python3
"""Freeze scoped source/functional/mechanism evidence. Never selects a model."""
from pathlib import Path
import hashlib,json,collections
R=Path(__file__).resolve().parents[1];O=R/'build/C12-pending-base-readiness-v1';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();paths={
 'OFF_first59':R/'build/C12-pending-base-OFF-first59-v2/run.json',
 'ON_first59':R/'build/C12-pending-base-ON-first59-v1/run.json',
 'ON_first59_instrumented':R/'build/C12-pending-base-ON-first59-traced-v1/run.json',
 'all1320_ON':R/'build/rvv-compute1320-C12-pending-base-ON-v1/run.json',
 'all1320_same_ELF_numeric_and_instret':R/'build/C12-pending-base-model-comparison-v1/report.json',
 'source_reconstruction':R/'build/C12-pending-base-source-closure-v2/report.json',
 'direct_C12_companion':R/'build/C12-pending-base-on-C12-companion-v1/report.json',
 'actual_hot_miss_fault_timer':R/'build/C12-pending-base-direct-ON-v2/run.json',
 'direct_OFF':R/'build/C12-pending-base-direct-OFF-v1/run.json',
 'actual_h0_IPI':R/'build/C12-pending-base-IPI-ON-v2/run.json',
 'actual_h1_IPI':R/'build/C12-pending-base-IPI-h1-ON-v1/run.json',
 'accepted_producer_fault_IRQ_unknown_event_proof':R/'build/C12-pending-base-event-proof-v3/report.json',
 'typed_parser_refusals':R/'build/C12-pending-base-parser-controls-v1/report.json'}
inputs={};reports={}
for name,p in paths.items():
 r=json.loads(p.read_text());assert r.get('pass')is True,name;reports[name]={'path':str(p),'sha256':sha(p)};inputs[str(p)]=sha(p)
 for n,h in r.get('input_sha256',{}).items():
  assert sha(n)==h,(name,n);inputs[n]=h
C=R/'build/C12-pending-base-frozen-2c40dca7-v1';manifest=json.loads((C/'manifest.json').read_text());inputs[str(C/'manifest.json')]=sha(C/'manifest.json')
for n,h in manifest['artifact_sha256'].items():assert sha(C/n)==h,n;inputs[str(C/n)]=h
for n in('C12-pending-base-guest-v1','C12-pending-base-IPI-guest-v2','C12-pending-base-IPI-h1-guest-v1','C12-pending-base-unknown-h0-guest-v2','C12-pending-base-unknown-h1-guest-v2'):
 p=R/'build'/n/'build.json';r=json.loads(p.read_text());assert r['exit_status']==0;inputs[str(p)]=sha(p)
 for k,h in r['input_sha256'].items():assert sha(k)==h,k;inputs[k]=h
# Bind exact per-PC mechanism, using actual global CSR joins rather than mcycle.
d=R/'build/C12-pending-base-ON-first59-traced-v1';events=[json.loads(x)for x in(d/'cpu.jsonl').read_text().splitlines()];rrd=[x['cycle']for x in events if x['event']=='rrd_accept'and x['pc']==0x80000cac];gaps=collections.Counter(b-a for a,b in zip(rrd,rrd[1:]));assert gaps=={23:63},gaps
retries=[x for x in events if x['event']=='pending_base_retry'and x['pc']==0x8000074a];split=[x for x in events if x['event']=='lane1_WB_split'and x['pc']==0x8000074c];assert len(retries)==len(split)==64
source=R/'pipeline/riscv-isa-sim-C12-pending-base-v1';inventory=json.loads((C/'native-inventory.json').read_text());assert all(sha(source/n)==h for n,h in inventory.items())
rows=json.loads((R/'build/C12-pending-base-ON-first59-v1/rows.json').read_text());representatives=[rows[i]for i in(1,4,19,22,55,58)]
r={'schema':'iris.C12_pending_base_readiness.v1','pass':True,'status':'experimental_default_OFF_source_mechanism_candidate_qualified_in_stated_scope','native_binary_sha256':manifest['binary_sha256'],'UART_sha256':manifest['uart_sha256'],'source_capsule_manifest':str(C/'manifest.json'),'source_capsule_manifest_sha256':sha(C/'manifest.json'),'selector':'empirical_pending_base_retry h0h1-live-XPR-base-RRD-retry-v1','default_OFF':True,'source_inventory_bytes_reverified':len(inventory),'gate_receipts':reports,
 'evidence_scope':{'OFF':'same first59 complete records/debuggerPC bytes,180 CSR prefix bytes,full async stream exactly equal to frozen C12; not a full1320 OFF replay','ON':'all1320 exact same-ELF records,184128 per-element golden checks,3960 returning CSR/ELF joins; zero per-case total/issue/drain instret or numeric mismatches','direct_normal_exit':'both compute harts hot loads, resolved cold miss, precise expected load faults and timer delivery;64 real guest MSIP IRQs per compute hart','source_ordering':'578 exact pending older producer admission/result/consumer joins;17 precise held-frontier IRQs;two partial-unknown producer normal refusals;four adversarial event mutants and five parser refusals','full_replay_end':'controlled intentional postmeasurement debuggerquit; no normal full1320 HTIF or end-to-end timing claim'},
 'concrete_causal_change':{'actual_consumer_PC_example':0x8000074a,'all_PC_values_are_trace_metadata_not_prediction_keys':True,'parent_hot_loop_RRD_interval':25,'retry_hot_loop_RRD_interval':23,'actual_63_hot_gaps_verified':63,'pending_base_retries_in_N64_window':64,'unchanged_lane1_WB_splits_in_window':64,'representative_same_ELF_model_windows':representatives,'source_rule':'pending RXS1 is a retryable source RRD hazard; do not replace it by an unconditional cohort/WB drain','EA_cache_PMA_privilege_definedness_checks':'original unchanged load candidate and original functional handler after producer response'},
 'limitations':['existing lane1-WB split remains','source-inspired local ingress repair; wholeCPU/physical timing not certified','wholeVRF/two-owner RVV abstraction and finite OPU COMplus1/FENCE bridge unchanged','no calibrated runtime/provider binding for this native epoch','canonical32/Zephyr package gates not rerun on this epoch; old C12 results not transferred','future independent heldout timing qualification required'],
 'scope_flags':{'parameter_fit_performed':False,'hardware_contacted':False,'reserved_timing_labels_consumed':False,'global_holdout_timings_consumed':False,'model_selected_or_promoted':False,'calibrated_provider_available':False,'physical_profile_qualified':False,'source_image_association':False,'full_CPU_RTL_timing_certified':False,'timing_2pct_certified':False},'input_sha256':inputs}
(O/'readiness.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'readiness_sha256':sha(O/'readiness.json'),'bound_inputs':len(inputs)}))
