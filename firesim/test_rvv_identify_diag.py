"""Finite diagnostic admission and partial-progress parser controls; no hardware."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_rvv_identify_diag import admit
from rvv_identify_diag_review import progress_prefix,validator,ELF
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build/rvv-identify-diagnostic-v2'
class Diagnostic(unittest.TestCase):
 def setUp(self):
  self.c=json.loads((BUILD/'corpus.json').read_text());self.text=(BUILD/'seed0/stdout').read_text();self.lines=self.text.splitlines();self.markers=[x for x in self.lines if x.startswith('IRIS_RVV_DIAG ')]
 def test_normal(self):
  r=validator().validate(self.text,self.c);self.assertEqual(r['checked_words'],226656);p=progress_prefix(self.text,self.c);self.assertEqual(p['markers'],3891);self.assertEqual(p['active_cases_done'],1920);self.assertEqual(p['incomplete_cases'],[])
 def test_admission(self):
  from batch_runner import digest
  r=admit(BUILD,digest(BUILD/'ready.json'));self.assertEqual(r[3].name,'guest.elf');self.assertFalse(r[0]['calibration_usable']);self.assertFalse(r[0]['fitting_only'])
 def test_wrong_ready(self):
  with self.assertRaises(ValueError):admit(BUILD,'0'*64)
 def test_changed_ELF(self):
  from batch_runner import digest
  with tempfile.TemporaryDirectory()as td:
   b=Path(td)
   for name in ['ready.json']+list(json.loads((BUILD/'ready.json').read_text())['artifact_sha256']): (b/name).write_bytes((BUILD/name).read_bytes())
   raw=bytearray((b/'guest.elf').read_bytes());raw[-1]^=1;(b/'guest.elf').write_bytes(raw)
   with self.assertRaises(ValueError):admit(b,digest(b/'ready.json'))
 def test_partial_start(self):
  at=next(i for i,l in enumerate(self.lines)if '"stage":"START"'in l);p=progress_prefix('\n'.join(self.lines[:at+1]),self.c);self.assertEqual(len(p['incomplete_cases']),1);self.assertEqual(p['incomplete_cases'][0]['last_stage'],'START')
 def test_wrong_role(self):
  r=json.loads(next(x.split(' ',1)[1]for x in self.markers if '"stage":"START"'in x));r['hart']=(r['hart']+1)%3
  boots='\n'.join(x for x in self.markers if '"stage":"BOOT"'in x)
  with self.assertRaises(ValueError):progress_prefix(boots+'\nIRIS_RVV_DIAG '+json.dumps(r),self.c)
 def test_duplicate(self):
  with self.assertRaises(ValueError):progress_prefix(self.text+'\n'+self.markers[0],self.c)
 def test_stage_reorder(self):
  changed=self.text.replace('"stage":"ACK"','"stage":"SETUP"',1)
  with self.assertRaises(ValueError):progress_prefix(changed,self.c)
 def test_unknown_stage(self):
  changed=self.text.replace('"stage":"START"','"stage":"MADE_UP"',1)
  with self.assertRaises(ValueError):progress_prefix(changed,self.c)
 def test_marker_removed(self):
  changed=self.text.replace(next(x+'\n'for x in self.markers if '"stage":"DONE"'in x),'',1)
  with self.assertRaises(ValueError):validator().validate(changed,self.c)
 def test_truncated_marker(self):
  with self.assertRaises(ValueError):progress_prefix('IRIS_RVV_DIAG {"hart":0',self.c)
 def test_typed_hart(self):
  changed=self.text.replace('"hart":0,"case_index":1920','"hart":false,"case_index":1920',1)
  with self.assertRaises(ValueError):progress_prefix(changed,self.c)
if __name__=='__main__':unittest.main()
