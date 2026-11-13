"""Additive managed-console contract; preserves the compiled packet/validator."""
import json
from hart2_pow2_validate_v4 import validate,m
PROFILE=dict(requested_baud=3676470,clock_hz=500000000,divisor=135)
def need(test,message):
 if not test:raise ValueError(message)
def cases():
 c=m.generate();result=[]
 for g in c['groups']:
  active=[];gold=[0,0,0]
  for r in c['regions']:
   if r['group']==g['group']:active.append(r['hart']);gold[r['hart']]=m.checksum(m.golden(r))
  result.append(dict(id=g['case_id'],active_harts=active,expected_checksums_by_hart=gold,region='kernel',parent_case_id=g['parent_case_id'],trial_id=g['trial'],group=g['group'],internal_split='protected_validation'if(g['lmul']==4 if not g['kind']else g['shape']==16)else'training_eligible',functional_only=True,calibration_usable=False))
 return result
def validate_console(text):
 def unique(pairs):
  obj={}
  for k,v in pairs:
   need(k not in obj,'Duplicate profile key');obj[k]=v
  return obj
 rows=[json.loads(line.strip().partition(' ')[2],object_pairs_hook=unique)for line in text.splitlines()if line.strip().startswith('IRIS_UART_PROFILE ')]
 need(rows==[PROFILE]and all(type(v)is int for v in rows[0].values()),'Exact typed actual Ethan UART profile')
 need('ASSERTION FAIL'not in text,'No kernel assertion')
 return validate(text,False)
