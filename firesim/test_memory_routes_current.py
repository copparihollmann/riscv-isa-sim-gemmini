"""Real-corpus admission controls; no hardware operations."""
import copy,json,unittest
from prepare_memory_routes_current import ROOT,admit,corpus_cases,check_readback,validator
BUILD=ROOT/'build/memory-routes-current-v1'
READY='9fd265b7abe38e0d0bc2b2020730f9e07a7f524e1ca475c89590b439bb034b2c'
class MemoryAdmissionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.corpus=json.loads((BUILD/'corpus.json').read_text());cls.layout=json.loads((BUILD/'readback-layout.json').read_text());cls.console=(BUILD/'seed0/run.stdout').read_text()
 def test_exact_source_kernel_ELF_and_both_schedules(self):
  _,_,cases,elf,inputs=admit(BUILD,READY);self.assertEqual(len(cases),1512);self.assertEqual(sum(len(c['active_harts'])for c in cases),2592);self.assertIn(str(elf),inputs)
 def test_changed_ready_hash_refuses(self):
  with self.assertRaises(ValueError):admit(BUILD,'0'*64)
 def test_address_stride_bank_or_payload_forgery_refuses(self):
  for field,value in [('base',0x88000000),('stride',32),('kernel_read_bytes_per_hart',1),('addresses_by_hart',[1,2,3])]:
   c=copy.deepcopy(self.corpus);c['cases'][0][field]=value
   with self.subTest(field=field),self.assertRaises((ValueError,AssertionError)):corpus_cases(c)
 def test_reordered_case_or_repeat_identity_refuses(self):
  c=copy.deepcopy(self.corpus);c['cases'][0],c['cases'][1]=c['cases'][1],c['cases'][0]
  with self.assertRaises(ValueError):corpus_cases(c)
  c=copy.deepcopy(self.corpus);c['cases'][0]['trial_id']=2
  with self.assertRaises(ValueError):corpus_cases(c)
 def test_wrong_numeric_goldens_refuse(self):
  c=copy.deepcopy(self.corpus);c['cases'][0]['expected_checksums']=[0,0,0]
  with self.assertRaises(ValueError):corpus_cases(c)
 def test_ELF_readback_geometry_or_identity_refuses(self):
  check_readback(BUILD/'memory-routes.elf',self.layout,self.corpus)
  for field,value in [('elf_sha256','0'*64),('records',864)]:
   c=copy.deepcopy(self.layout);c[field]=value
   with self.assertRaises(ValueError):check_readback(BUILD/'memory-routes.elf',c,self.corpus)
 def test_missing_hart2_or_terminal_refuses(self):
  self.assertEqual(validator().validate(self.console,self.corpus)['regions'],2592)
  for changed in ['\n'.join(x for x in self.console.splitlines()if not x.startswith('IRIS_BATCH_DONE ')), '\n'.join(x for x in self.console.splitlines()if not(x.startswith('IRIS_REGION ')and json.loads(x.split(' ',1)[1])['hart']==2))]:
   with self.assertRaises(ValueError):validator().validate(changed,self.corpus)
 def test_old_singletrial_corpus_cannot_claim_new_role(self):
  old=json.loads((ROOT/'build/memory-routes-fit-v1-final/corpus.json').read_text())
  with self.assertRaises(ValueError):corpus_cases(old)
if __name__=='__main__':unittest.main()
