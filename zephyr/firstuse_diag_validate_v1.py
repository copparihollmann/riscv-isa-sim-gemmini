"""Exact new functional probe protocol; never accepts old mixed9 partial rows."""
import json
PROFILE={'requested_baud':3676470,'clock_hz':500000000,'divisor':135}
def need(ok,message):
 if not ok:raise ValueError(message)
def objects(text,prefix):return[json.loads(x[len(prefix)+1:])for x in text.splitlines()if x.startswith(prefix+' ')]
def cases():
 return [dict(id='zephyr.gemm16',active_harts=[0,1,2],expected_checksums_by_hart=[1536,1280,1280],region='kernel'),dict(id='zephyr.conv2d8',active_harts=[0,1,2],expected_checksums_by_hart=[108]*3,region='kernel'),dict(id='zephyr.vme.scalar-control',active_harts=[0,1,2],expected_checksums_by_hart=[1024]*3,region='kernel')]
def validate(text,negative=False):
 need('IRIS_FATAL'not in text and 'ASSERTION FAIL'not in text,'No unexpected application/kernel fatal')
 need(objects(text,'IRIS_UART_PROFILE')==[PROFILE],'Actual Ethan UART profile')
 rows=objects(text,'IRIS_REGION');want=[(c,h,c['expected_checksums_by_hart'][h])for c in cases()[:2 if negative else 3]for h in c['active_harts']];need(len(rows)==len(want),'Exact real functional region count')
 for row,(case,h,total)in zip(rows,want):
  need(all(type(row.get(k))is int for k in ['hart','hart_mask','checksum','start_cycle','end_cycle','instret_delta']),'Typed counter/placement fields')
  role='scalar.compute'if case['id']!='zephyr.vme.scalar-control'else'vme.compute'if h<2 else'scalar.control'
  need(row['case_id']==case['id']and row['hart']==h and row['role']==role and row['hart_mask']==7 and row['region']=='kernel'and row['checksum']==total,'Independent new-case numerical/role proof')
  need(0<=row['start_cycle']<row['end_cycle']<2**64 and 0<row['instret_delta']<2**64,'Actual valid counters')
 ready=objects(text,'IRIS_FIRSTUSE_READY');need(len(ready)==1,'Actual observer readiness')
 for k,v in [('physical_hart',2),('logical_cpu',2),('worker',2),('pin',2),('timeout_ms',10 if negative else 5000)]:need(type(ready[0].get(k))is int and ready[0][k]==v,'Typed observer placement/deadline '+k)
 need(ready[0].get('hart2_scalar_only')is True,'Explicit scalar observer')
 snapshots=objects(text,'IRIS_FIRSTUSE_SNAPSHOT');need(len(snapshots)==3,'Three actual last-recorded slots')
 for h,row in enumerate(snapshots):
  need(all(type(row.get(k))is int for k in ['slot','begin','end','stage','iteration','physical_hart','logical_cpu','worker','pin','last_recorded_mstatus','last_recorded_mie','last_recorded_mip','last_recorded_mcycle']),'Typed raw snapshot')
  need(all(row[k]==h for k in ['slot','physical_hart','logical_cpu','worker','pin']),'Actual physical/logical/pin source identities')
  need(row['begin']==row['end']and row['begin']>0 and not row['begin']&1 and row['stable_sequence_observed']is True and row['metadata_race_possible']is True and row['current_PC_or_state_claimed']is False,'Explicit last-point consistency/scope')
 timeouts=objects(text,'IRIS_FIRSTUSE_TIMEOUT');done=objects(text,'IRIS_BATCH_DONE');observer_done=objects(text,'IRIS_FIRSTUSE_OBSERVER_DONE')
 if negative:
  need(not done and not observer_done and len(timeouts)==1,'Negative capture is not normal completion')
  t=timeouts[0];need(all(type(t.get(k))is int for k in ['observer_hart','timeout_ms','done0','done1','exit_code_requested']),'Typed target timeout')
  need(t['observer_hart']==2 and t['timeout_ms']==10 and t['done0']==0 and t['done1']in[0,1]and t['exit_code_requested']==1 and t['normal_completion']is False,'Real forced-stall timeout envelope')
  need(snapshots[0]['stage']==100 and snapshots[0]['iteration']==0 and snapshots[2]['stage']==1000,'Forced stop before first VME API, scalar observer active')
 else:
  need(not timeouts and done==[{'failed':0}]and type(done[0]['failed'])is int,'Normal exact completion')
  need(observer_done==[dict(physical_hart=2,done0=1,done1=1)]and all(type(v)is int for v in observer_done[0].values()),'Actual observer completion')
  need([s['stage']for s in snapshots]==[281,281,1001],'Completed app source-point witnesses')
 return dict(regions=len(rows),independent_region_checksums=True,normal_completion=not negative,forced_stall_diagnostic_capture=negative,actual_observer_hart=2,compute_harts=[0,1],no_hart2_application_vector=True,snapshot_scope='Last recorded source points and CSRs only; stable sequence does not prove current/coherent state or physical vector completion',cause_or_current_PC_proven=False)
