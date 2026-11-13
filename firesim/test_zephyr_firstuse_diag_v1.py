#!/usr/bin/env python3
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from firstuse_diag_validate_v1 import validate,cases
from firstuse_diag_qualify_v1 import codeproof
from prepare_zephyr_firstuse_diag_v1 import admit
from batch_runner import digest,collect_guest_results
NORMAL=(ROOT/'build/zephyr-mixed9-firstuse-normal-seed0-v2/stdout').read_text();NEGATIVE=(ROOT/'build/zephyr-mixed9-firstuse-forced-seed0-v2/stdout').read_text();Q=ROOT/'build/zephyr-mixed9-firstuse-qualified-v2'
class Checks(unittest.TestCase):
 def changed(self,prefix,key,value,negative=False):
  lines=(NEGATIVE if negative else NORMAL).splitlines();i=next(i for i,x in enumerate(lines)if x.startswith(prefix+' '));r=json.loads(lines[i].split(' ',1)[1]);r[key]=value;lines[i]=prefix+' '+json.dumps(r)
  with self.assertRaises(ValueError):validate('\n'.join(lines),negative)
 def test_normal(self):self.assertEqual(validate(NORMAL)['regions'],9)
 def test_actual_failure(self):self.assertIs(validate(NEGATIVE,True)['forced_stall_diagnostic_capture'],True)
 def test_negative_not_normal(self):
  with self.assertRaises(ValueError):validate(NEGATIVE)
 def test_normal_not_negative(self):
  with self.assertRaises(ValueError):validate(NORMAL,True)
 def test_checksum(self):self.changed('IRIS_REGION','checksum',9)
 def test_counter_bool(self):self.changed('IRIS_REGION','instret_delta',True)
 def test_mask(self):self.changed('IRIS_REGION','hart_mask',3)
 def test_physicalID(self):self.changed('IRIS_FIRSTUSE_READY','physical_hart',0)
 def test_logicalID(self):self.changed('IRIS_FIRSTUSE_READY','logical_cpu',0)
 def test_pin(self):self.changed('IRIS_FIRSTUSE_READY','pin',1)
 def test_pinbool(self):self.changed('IRIS_FIRSTUSE_READY','pin',True)
 def test_scalar_policy(self):self.changed('IRIS_FIRSTUSE_READY','hart2_scalar_only',False)
 def test_deadline(self):self.changed('IRIS_FIRSTUSE_READY','timeout_ms',10)
 def test_stablebool(self):self.changed('IRIS_FIRSTUSE_SNAPSHOT','stable_sequence_observed',1)
 def test_torn(self):self.changed('IRIS_FIRSTUSE_SNAPSHOT','end',0)
 def test_false_PC_claim(self):self.changed('IRIS_FIRSTUSE_SNAPSHOT','current_PC_or_state_claimed',True)
 def test_race_scope(self):self.changed('IRIS_FIRSTUSE_SNAPSHOT','metadata_race_possible',False)
 def test_stage(self):self.changed('IRIS_FIRSTUSE_SNAPSHOT','stage',100)
 def test_footerbool(self):self.changed('IRIS_BATCH_DONE','failed',False)
 def test_failed_exit_request(self):self.changed('IRIS_FIRSTUSE_TIMEOUT','exit_code_requested',0,True)
 def test_false_complete_negative(self):self.changed('IRIS_FIRSTUSE_TIMEOUT','normal_completion',True,True)
 def test_missing_or_duplicate(self):
  for prefix in ['IRIS_FIRSTUSE_READY','IRIS_FIRSTUSE_SNAPSHOT','IRIS_FIRSTUSE_OBSERVER_DONE','IRIS_BATCH_DONE']:
   row=next(x for x in NORMAL.splitlines()if x.startswith(prefix+' '))
   for text in [NORMAL.replace(row+'\n','',1),NORMAL+row+'\n']:
    with self.assertRaises(ValueError):validate(text)
 def test_unchanged_runner(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);u=p/'results-workload/test/iris-batch0';u.mkdir(parents=True);(u/'uartlog').write_text(NORMAL+'\nScript done on 2026-11-07 14:00:00+00:00 [COMMAND_EXIT_CODE="0"]\n');m=dict(cases=cases(),elf_sha256='a'*64,image=dict(sha256='b'*64),require_regions=True,require_goldens=True);collect_guest_results(p,m);self.assertEqual(len(m['regions']),9);self.assertIs(m['region_checksums_independently_validated'],True)
 def test_admission(self):self.assertEqual(admit(Q,digest(Q/'ready.json'))[3],cases())
 def test_wrong_ready(self):
  with self.assertRaises(ValueError):admit(Q,'0'*64)
 def test_scalar_body(self):self.assertEqual(codeproof(ROOT/'build/zephyr-mixed9-firstuse-normal-v2/zephyr/zephyr.elf')['scalar_observer_and_progress']['iris_probe_stamp']['hot_fence_or_atomic_instructions'],0)
if __name__=='__main__':unittest.main()
