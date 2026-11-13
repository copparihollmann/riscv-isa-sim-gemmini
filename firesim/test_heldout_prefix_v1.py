"""Refuse incomplete/numerically altered samples without touching hardware."""
import copy,importlib.util,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'firesim'))
import analyze_heldout_prefix_v1 as diagnostic
class PrefixControls(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  batch=ROOT/'build/fast-heldout-zephyr-compact-v6'
  cls.corpus=json.loads((batch/'manifest.json').read_text());cls.cases=json.loads((batch/'cases.json').read_text());cls.goldens=json.loads((batch/'golden.json').read_text())
  full=(ROOT/'build/heldout-v6-prediction-9b2-fadd-shape-store-v1/run/stdout').read_text()
  cls.prefix=full[:full.index('IRIS_HELDOUT_PHASE {"phase":1,')]
 def check_prefix(self,text):return diagnostic.validate_prefix(text,self.corpus,self.cases,self.goldens)
 def change(self,prefix,key,value):
  lines=self.prefix.splitlines()
  for i,line in enumerate(lines):
   if line.startswith(prefix):
    d=json.loads(line[len(prefix):]);d[key]=value;lines[i]=prefix+json.dumps(d);break
  else:raise AssertionError('missing control record')
  return '\n'.join(lines)
 def test_real_model_prefix_is_only_one_phase(self):
  p=self.check_prefix(self.prefix);self.assertEqual((p['complete_leading_phases'],len(p['regions'])),(1,16));self.assertEqual(p['independently_checked_INT32_words'],61440)
 def test_numerical_hash_refused(self):
  with self.assertRaises(ValueError):self.check_prefix(self.change('IRIS_HELDOUT_RESULT ','accumulator_checksum',0))
 def test_region_counter_refused(self):
  with self.assertRaises(ValueError):self.check_prefix(self.change('IRIS_REGION ','end_cycle',0))
 def test_missing_output_refused(self):
  with self.assertRaises(ValueError):self.check_prefix('\n'.join(x for x in self.prefix.splitlines()if not x.startswith('IRIS_HELDOUT_RESULT ')))
 def test_missing_region_refused(self):
  lines=self.prefix.splitlines();i=next(i for i,x in enumerate(lines)if x.startswith('IRIS_REGION '));del lines[i]
  with self.assertRaises(ValueError):self.check_prefix('\n'.join(lines))
 def test_duplicate_phase_refused(self):
  row=next(x for x in self.prefix.splitlines()if x.startswith('IRIS_HELDOUT_PHASE '))
  with self.assertRaises(ValueError):self.check_prefix(self.prefix+'\n'+row)
 def test_global_interval_refused(self):
  with self.assertRaises(ValueError):self.check_prefix(self.change('IRIS_HELDOUT_ELAPSED ','timebase_hz',1))
 def test_producer_refusal_required(self):
  with self.assertRaises(ValueError):self.check_prefix(self.change('IRIS_HELDOUT_PRODUCER ','vme_refused',False))
 def test_completed_run_not_incomplete_diagnostic(self):
  with self.assertRaises(ValueError):self.check_prefix(self.prefix+'\nIRIS_BATCH_DONE {"failed":0}')
 def test_fatal_is_not_partial_validation(self):
  with self.assertRaises(ValueError):self.check_prefix(self.prefix+'\nIRIS_FATAL {}')
 def test_bool_phase_not_integer(self):
  with self.assertRaises(ValueError):self.check_prefix(self.change('IRIS_HELDOUT_PHASE ','phase',False))
if __name__=='__main__':unittest.main()
