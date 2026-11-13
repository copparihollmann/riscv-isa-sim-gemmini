"""Local packet admission, ordinary runner, scope and TRAIN-only guards."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_rvv_hart2_only import admit,merge,WATCHDOG,PHASE_TIMEOUT
from rvv_hart2_only_review import validator,inspect,inspect_clint_window,scalar_wire_proof,flatten
from analyze_rvv_hart2_only import training_rows
from batch_runner import digest,parse_regions
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build/rvv-hart2-only-v1'
class Admission(unittest.TestCase):
 def setUp(self):self.c=json.loads((BUILD/'corpus.json').read_text());self.ready=digest(BUILD/'ready.json')
 def test_actual_admission(self):self.assertEqual(len(admit(BUILD,self.ready)[2]),588)
 def test_wrong_ready(self):
  with self.assertRaises(ValueError):admit(BUILD,'0'*64)
 def test_corrupt_ELF(self):
  with tempfile.TemporaryDirectory()as td:
   b=Path(td)
   for name in ['ready.json']+list(json.loads((BUILD/'ready.json').read_text())['artifact_sha256']):(b/name).write_bytes((BUILD/name).read_bytes())
   raw=bytearray((b/'guest.elf').read_bytes());raw[-1]^=1;(b/'guest.elf').write_bytes(raw)
   with self.assertRaises(ValueError):admit(b,digest(b/'ready.json'))
 def test_ready_bool_count(self):
  with tempfile.TemporaryDirectory()as td:
   b=Path(td)
   for name in ['ready.json']+list(json.loads((BUILD/'ready.json').read_text())['artifact_sha256']):(b/name).write_bytes((BUILD/name).read_bytes())
   r=json.loads((b/'ready.json').read_text());r['required_regions']=True;(b/'ready.json').write_text(json.dumps(r))
   with self.assertRaises(ValueError):admit(b,digest(b/'ready.json'))
 def test_exact_parent_subset(self):
  old=json.loads((ROOT/'build/rvv-identify-compact-v1/corpus.json').read_text())['cases'];self.assertEqual(self.c['cases'],[r for r in old if r['hart']==2]);self.assertEqual(sum(r['internal_split']=='reserved_holdout'for r in self.c['cases']),156)
 def test_excluded_256B(self):
  c=copy.deepcopy(self.c);c['cases'][0].update(kind='load',kind_id=2,bytes=256,vl=64,lmul=8,sew=32,mode=0,streams=1)
  with self.assertRaises(ValueError):validator().validate_corpus(c)
 def test_no_peer_cases(self):
  c=copy.deepcopy(self.c);c['cases'][0]['hart']=1
  with self.assertRaises(ValueError):validator().validate_corpus(c)
 def test_runner_ordinary_JSON(self):
  text=(ROOT/'build/rvv-hart2-only-functional-seed0-v1/stdout').read_text();rows=parse_regions(text,flatten(self.c),json.loads((BUILD/'ready.json').read_text())['ELF_sha256'],'0'*64,require_regions=True,require_goldens=True);self.assertEqual(len(rows),588);self.assertTrue(all(r['hart']==2 for r in rows))
 def test_scalar_wire_and_sentinel(self):
  proof=scalar_wire_proof((BUILD/'guest.elf').read_bytes());self.assertEqual(proof['emit_vector_instructions'],0);self.assertEqual([r['offset']for r in proof['scalar_record_stores']],list(range(0,136,8)))
  self.assertEqual(len(proof['permanent_park']),1)
 def test_TRAIN_no_timestamps(self):
  rows=[dict(c,start_cycle=1000+i*10,issue_cycle=1003+i*10,end_cycle=1005+i*10,mtime_before=1,mtime_after=2)for i,c in enumerate(self.c['cases'])];rows=training_rows(rows);self.assertEqual(len(rows),432)
  self.assertTrue(all(r['internal_split']=='train'and r['issue_cycles']==3 and r['drain_cycles']==2 and not {'start_cycle','issue_cycle','end_cycle','mtime_before','mtime_after'}&set(r)for r in rows))
 def test_bound_sources_absolute_collision(self):
  d={str(BUILD/'guest.elf'):'a'*64}
  with self.assertRaises(ValueError):merge(d,{str(BUILD/'guest.elf'):'b'*64})
  d={};merge(d,{'benchmarks/rvv_hart2_only_v1/guest.c':'a'*64});self.assertTrue(all(Path(k).is_absolute()for k in d))
 def test_requested_bounds(self):self.assertEqual((WATCHDOG,PHASE_TIMEOUT),(180,360))
if __name__=='__main__':unittest.main()
