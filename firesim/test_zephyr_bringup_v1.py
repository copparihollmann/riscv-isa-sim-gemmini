#!/usr/bin/env python3
"""Finite adversarial parser/lifecycle/admission checks; no remote operations."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from fpga_bringup_v1 import validate
from analyze_zephyr_bringup_v1 import lifecycle
from prepare_zephyr_bringup_v1 import admit,merge
from batch_runner import digest,collect_guest_results
from fpga_bringup_v1 import host_cases
QUAL=ROOT/'build/zephyr-fpga-scalar6-bringup-qualification-v1'
TEXT=(ROOT/'build/zephyr-fpga-scalar6-bringup-seed0-v1/stdout').read_text()+'\n*** PASSED ***\nCOMMAND_EXIT_CODE="0"\n'

class Checks(unittest.TestCase):
 def test_positive(self):self.assertEqual(validate(TEXT,True)['regions'],6)
 def mutate(self,kind,fn):
  lines=TEXT.splitlines();n=next(i for i,x in enumerate(lines)if x.startswith(kind+' '));r=json.loads(lines[n].split(' ',1)[1]);fn(r);lines[n]=kind+' '+json.dumps(r)
  with self.assertRaises(ValueError):validate('\n'.join(lines),True)
 def test_bool_hart(self):self.mutate('IRIS_REGION',lambda r:r.update(hart=False))
 def test_wrong_golden(self):self.mutate('IRIS_REGION',lambda r:r.update(checksum=r['checksum']+1))
 def test_wrong_role(self):self.mutate('IRIS_REGION',lambda r:r.update(role='vector'))
 def test_wrong_mask(self):self.mutate('IRIS_REGION',lambda r:r.update(hart_mask=3))
 def test_counter_bool(self):self.mutate('IRIS_REGION',lambda r:r.update(instret_delta=True))
 def test_counter_reverse(self):self.mutate('IRIS_REGION',lambda r:r.update(end_cycle=r['start_cycle']))
 def test_divisor(self):self.mutate('IRIS_UART_PROFILE',lambda r:r.update(divisor=4339))
 def test_done_bool(self):self.mutate('IRIS_BATCH_DONE',lambda r:r.update(failed=False))
 def test_partial_and_duplicate(self):
  row=next(x for x in TEXT.splitlines()if x.startswith('IRIS_REGION '))
  for s in [TEXT.replace(row+'\n','',1),TEXT+row+'\n',TEXT.replace('IRIS_BATCH_DONE','PARTIAL',1)]:
   with self.assertRaises(ValueError):validate(s,True)
 def test_false_driver_pass(self):
  for s in [TEXT.replace('COMMAND_EXIT_CODE="0"','COMMAND_EXIT_CODE="124"'),TEXT.replace('COMMAND_EXIT_CODE="0"',''),TEXT+'COMMAND_EXIT_CODE="0"\n',TEXT.replace('*** PASSED ***','')]:
   with self.assertRaises(ValueError):validate(s,True)
 def test_fatal_after_done(self):
  with self.assertRaises(ValueError):validate(TEXT+'\nIRIS_FATAL\n',True)
 def test_unchanged_runner_collects_actual_scalar_protocol(self):
  with tempfile.TemporaryDirectory()as d:
   manager=Path(d);logs=manager/'results-workload/test/iris-batch0';logs.mkdir(parents=True);(logs/'uartlog').write_text(TEXT)
   m=dict(cases=host_cases(),elf_sha256='a'*64,image=dict(sha256='b'*64),require_regions=True,require_goldens=True)
   collect_guest_results(manager,m)
   self.assertIs(m['regions_validated'],True);self.assertIs(m['region_checksums_independently_validated'],True);self.assertEqual(len(m['regions']),6)
 def test_lifecycle(self):
  m=dict(status='completed_uncertified',cleanup_status='passed',commands=[dict(task=t,status='passed',returncode=0,timed_out=False)for t in ['kill','infrasetup','runworkload','kill']]);self.assertEqual(len(lifecycle(m,m)),4)
  for field,value in [('returncode',True),('returncode',124),('timed_out',True),('status','failed')]:
   n=copy.deepcopy(m);n['commands'][2][field]=value
   with self.assertRaises(ValueError):lifecycle(n,n)
  n=copy.deepcopy(m);n['commands'].pop()
  with self.assertRaises(ValueError):lifecycle(n,n)
 def test_admission(self):self.assertEqual(admit(QUAL,digest(QUAL/'ready.json'))[3][1]['expected_checksums_by_hart'],[108]*3)
 def test_wrong_ready(self):
  with self.assertRaises(ValueError):admit(QUAL,'0'*64)
 def test_collision_and_absolute(self):
  p=ROOT/'zephyr/fpga_bringup_v1.py';ids={};merge(ids,{'zephyr/fpga_bringup_v1.py':digest(p)});self.assertEqual(list(ids),[str(p)])
  with self.assertRaises(ValueError):merge(ids,{str(p):'0'*64})

if __name__=='__main__':unittest.main()
