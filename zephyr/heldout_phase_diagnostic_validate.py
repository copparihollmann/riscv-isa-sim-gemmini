"""Separate normal completion and bounded diagnostic-timeout evidence."""
import json
from heldout_phase_diagnostic_run import validate

def timeout_evidence(text,forced=False):
 rows=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_DIAG_TIMEOUT ')]
 if len(rows)!=1 or 'IRIS_DIAG_DONE 'in text:raise ValueError('Unique timeout and no normal completion required')
 r=rows[0]
 if set(r)!={'watchdog_hart','main','worker','producer','diagnostic_not_normal_completion'}or r['watchdog_hart']!=1 or r['diagnostic_not_normal_completion']is not True:raise ValueError('Actual CPU1 diagnostic watchdog')
 decoded={}
 for name in ['main','worker','producer']:
  word=r[name]
  if type(word)is not int or not 0<=word<1<<64:raise ValueError('Known64bit progress record required')
  if word==0:
   decoded[name]=dict(not_recorded=True,source='CRT-initialized BSS; no stage store yet')
   continue
  fields=dict(sequence=word>>32,hart=(word>>28)&15,phase=(word>>24)&15,job=(word>>16)&255,stage=word&65535)
  if fields['sequence']==0 or fields['hart']not in(0,1,2)or fields['phase']not in(0,1)or fields['job']>15:raise ValueError('Progress record domain')
  if name=='worker'and fields['hart']!=0 or name=='producer'and fields['hart']!=2:raise ValueError('Physical producer/compute placement')
  decoded[name]=fields
 if forced and (decoded['main'].get('phase')!=1 or decoded['main'].get('stage')!=1):raise ValueError('Forced phase1 entry stall not reached')
 return dict(outcome='bounded_no_stage_progress_observed',normal_completion=False,root_cause_proven=False,mailboxes_raw=r,decoded_progress=decoded,watchdog_hart=1,host_watchdog_remains_authoritative=True)
