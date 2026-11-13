import importlib.util
from pathlib import Path
import unittest
from iris_model.graph_run import derive_history
from spike.empirical_launch_v2 import fatal_addresses

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('own_VME_profile',ROOT/'timing/profile_vme_full_graph_v1.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class GraphRunControls(unittest.TestCase):
 def test_exact_history_only(self):
  parent=b'base_hz 500000000\nempirical_profile experimental-effective-services arbitrary-id bounded\nrule 0 0 0 scalar0 3 1 status core_cycles\n'
  child,proof=derive_history(parent,'full');self.assertEqual(child.replace(b'arbitrary-id full',b'arbitrary-id bounded'),parent);self.assertTrue(proof['all_other_bytes_identical'])
 def test_bounded_copy(self):
  p=b'empirical_profile mode identity bounded\n';self.assertEqual(derive_history(p,'bounded')[0],p)
 def test_duplicate_history_refused(self):
  with self.assertRaises(ValueError):derive_history(b'empirical_profile mode id bounded\n'*2,'full')
 def test_unsupported_history_refused(self):
  with self.assertRaises(ValueError):derive_history(b'empirical_profile mode id bounded\n','fast-forward')
 def test_existing_full_parent_refused(self):
  with self.assertRaises(ValueError):derive_history(b'empirical_profile mode id full\n','full')
 def test_missing_profile_refused(self):
  with self.assertRaises(ValueError):derive_history(b'base_hz 500000000\n','full')
 @classmethod
 def setUpClass(cls):cls.raw=(ROOT/'build/full-graph-VME-buffered-full-v4/stderr').read_text()
 def changed(self,index,value):
  lines=self.raw.splitlines();words=[i for i,l in enumerate(lines)if l!=':'];lines[words[index]]=value;return '\n'.join(lines)+'\n'
 def test_real_words_and_counters(self):
  rows,words=module.decode(self.raw);self.assertEqual((len(rows),words),(6,144))
 def test_wrong_output_word_refused(self):
  with self.assertRaises(ValueError):module.decode(self.changed(25,'0x0000000000000000'))
 def test_unstable_footer_refused(self):
  with self.assertRaises(ValueError):module.decode(self.changed(121,'0x0000000000000001'))
 def test_zero_instret_refused(self):
  with self.assertRaises(ValueError):module.decode(self.changed(3,'0x0000000000000000'))
 def test_reversed_counter_refused(self):
  with self.assertRaises(ValueError):module.decode(self.changed(2,'0x0000000000000000'))
 def test_partial_readback_refused(self):
  with self.assertRaises(ValueError):module.decode('\n'.join(self.raw.splitlines()[:-3])+'\n')
 def test_actual_abort_is_executable_fatal_symbol(self):self.assertIn('abort',fatal_addresses(ROOT/'build/full-graph-VME-guest-buffered-v4/profile-vme.elf'))

if __name__=='__main__':unittest.main()
