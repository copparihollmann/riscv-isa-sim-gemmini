"""Actual one-shot diagnostic evidence; last-stage metadata is best effort only."""
import json
from heldout_phase_watch_pair_validate import validate as parent_normal

def records(text,tag):return[json.loads(l.split(' ',1)[1])for l in text.splitlines()if l.startswith(tag+' ')]
def require(x,why):
 if not x:raise ValueError(why)
def arm(text,enabled):
 a=records(text,'IRIS_FLUSH_ARM');require(len(a)==1,'Unique common h1 armer execution');a=a[0];require(a.get('hart')==1 and type(a.get('hart'))is int and a.get('enabled')is enabled and type(a.get('enabled'))is bool and a.get('delay_ms')==3000 and type(a['delay_ms'])is int,'Exact armer hart/flag/delay')
 for k in ['armed_mtime','deadline_mtime','last_recorded_mstatus','last_recorded_mie']:require(type(a.get(k))is int and 0<=a[k]<2**64,'Known integer ARM field')
 if enabled:require(a['deadline_mtime']-a['armed_mtime']==1500000 and a['last_recorded_mie']&128 and a['last_recorded_mstatus']&8,'Actual local hart1 comparator+MTIE+MIE setup')
 else:require(a['armed_mtime']==a['deadline_mtime']==0,'Disabled armer did not arm comparator')
 return a

def normal(text,m,cases,goldens,enabled):
 require(not records(text,'IRIS_FLUSH_ONESHOT')and not records(text,'IRIS_FLUSH_SNAPSHOT'),'Normal output must not be diagnostic capture');a=arm(text,enabled);proof=parent_normal(text,m,cases,goldens,False);proof.update(one_shot_enabled=enabled,one_shot_delay_ms=3000,both_variants_execute_same_scalar_armer_thread=True,periodic_watcher=False,arming=a);return proof

def timeout(text,forced=False):
 a=arm(text,True);events=records(text,'IRIS_FLUSH_ONESHOT');snap=records(text,'IRIS_FLUSH_SNAPSHOT');require(len(events)==1 and len(snap)==6 and not records(text,'IRIS_DIAG_DONE')and not records(text,'IRIS_BATCH_DONE'),'Single diagnostic exit, six slots, no normal completion');e=events[0]
 require(e.get('hart')==1 and type(e['hart'])is int and e.get('normal_completion')is False and e.get('exit_code')==1 and type(e['exit_code'])is int and e.get('before_timer_spinlock_and_announce')is True,'Actual first C timer hook scope')
 for k in ['armed_mtime','deadline_mtime','entry_mtime','entry_mstatus','entry_mie','entry_mip']:require(type(e.get(k))is int and 0<=e[k]<2**64,'Typed timer entry field')
 require(e['armed_mtime']==a['armed_mtime']and e['deadline_mtime']==a['deadline_mtime']and e['entry_mtime']>=e['deadline_mtime'],'Actual delayed local comparator reached')
 for i,s in enumerate(snap):
  require(s.get('slot')==i and type(s.get('slot'))is int and type(s.get('stable_sequence_observed'))is bool and s.get('metadata_race_possible')is True and s.get('current_PC_or_state_claimed')is False,'Best-effort last-record scope')
  for k in ['begin','stage','owner_thread_id','current_thread_id','peer','last_recorded_mstatus','last_recorded_mie','last_recorded_mip','last_recorded_mcycle','last_recorded_mtime','end']:require(type(s.get(k))is int and 0<=s[k]<2**64,'Known-width raw last-record word')
  if s['stable_sequence_observed']:require(s['begin']==s['end']and not s['begin']&1,'Stable sequence consistency only')
 if forced:
  stage=snap[3]['stage'];require((stage&65535)==1 and ((stage>>24)&15)==1 and stage>>32>0,'Forced phase1 entry last main stamp reached')
 return dict(normal_completion=False,diagnostic_HTIF_exit_code=1,source_timer_hart=1,one_shot_delay_ms=3000,snapshots=6,forced_phase1_entry_reached=forced,last_recorded_not_current_state=True,metadata_race_possible=True,hardware_root_cause_proven=False,watchdog_fix_proven=False,host_bound_remains_authoritative=True,event=e,last_snapshots=snap)
