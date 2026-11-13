"""New1908 admission/scope/phase refusal checks, no hardware."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_rvv_identify_1908 import admit
from rvv_identify_1908_review import validator,inspect,inspect_clint_window
from analyze_rvv_identify_1908 import training_rows
from batch_runner import digest
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build/rvv-identify-1908-v1'
class Admission(unittest.TestCase):
 def setUp(self):self.c=json.loads((BUILD/'corpus.json').read_text());self.ready=digest(BUILD/'ready.json')
 def test_actual_admit(self):self.assertEqual(len(admit(BUILD,self.ready)[2]),1908)
 def test_wrong_ready(self):
  with self.assertRaises(ValueError):admit(BUILD,'0'*64)
 def test_changed_ELF(self):
  with tempfile.TemporaryDirectory()as td:
   b=Path(td)
   for name in ['ready.json']+list(json.loads((BUILD/'ready.json').read_text())['artifact_sha256']):(b/name).write_bytes((BUILD/name).read_bytes())
   x=bytearray((b/'guest.elf').read_bytes());x[-1]^=1;(b/'guest.elf').write_bytes(x)
   with self.assertRaises(ValueError):admit(b,digest(b/'ready.json'))
 def test_excluded_reinsertion(self):
  old=json.loads((ROOT/'build/rvv-identify-TK-v4/corpus.json').read_text())['cases']
  for kind in('load','store'):
   c=copy.deepcopy(self.c);c['cases'][0]=next(r for r in old if r['hart']==2 and r['kind']==kind and r['bytes']==256)
   with self.assertRaises(ValueError):validator().validate_corpus(c)
 def test_exact_retained_scope(self):
  old=json.loads((ROOT/'build/rvv-identify-TK-v4/corpus.json').read_text())['cases'];want=[r for r in old if not(r['hart']==2 and r['kind']in('load','store')and r['bytes']==256)]
  self.assertEqual(self.c['cases'],want);self.assertEqual(sum(r['internal_split']=='train'for r in want),1410)
  self.assertEqual([r['case_id']for r in old if r['internal_split']=='reserved_holdout'],[r['case_id']for r in want if r['internal_split']=='reserved_holdout'])
 def test_phase_export_keeps_deltas_hides_absolutes(self):
  rows=[dict(c,start_cycle=1000+i*10,issue_cycle=1003+i*10,end_cycle=1005+i*10,mtime_before=1,mtime_after=2)for i,c in enumerate(self.c['cases'])];out=training_rows(rows);self.assertEqual(len(out),1410)
  for r in out:
   self.assertEqual((r['issue_cycles'],r['drain_cycles']),(3,2));self.assertFalse({'start_cycle','issue_cycle','end_cycle','mtime_before','mtime_after'}&set(r))
if __name__=='__main__':unittest.main()
