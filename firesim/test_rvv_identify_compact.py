"""New1908 admission/scope/phase refusal checks, no hardware."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_rvv_identify_compact import admit
from rvv_identify_compact_review import validator,inspect,inspect_clint_window
from analyze_rvv_identify_compact import training_rows
from batch_runner import digest
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build/rvv-identify-compact-v1'
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
  want.sort(key=lambda r:r['hart']);self.assertEqual(self.c['cases'],want);self.assertEqual(sum(r['internal_split']=='train'for r in want),1410)
  self.assertEqual(sorted(r['case_id']for r in old if r['internal_split']=='reserved_holdout'),sorted(r['case_id']for r in want if r['internal_split']=='reserved_holdout'))
 def test_phase_export_keeps_deltas_hides_absolutes(self):
  rows=[dict(c,start_cycle=1000+i*10,issue_cycle=1003+i*10,end_cycle=1005+i*10,mtime_before=1,mtime_after=2,actual_record_uint64=list(range(17)))for i,c in enumerate(self.c['cases'])];out=training_rows(rows);self.assertEqual(len(out),1410)
  for r in out:
   self.assertEqual((r['issue_cycles'],r['drain_cycles']),(3,2));self.assertNotIn('actual_record_uint64',r);self.assertFalse({'start_cycle','issue_cycle','end_cycle','mtime_before','mtime_after'}&set(r))
 def test_partial_completed_hart(self):
  from rvv_identify_compact_review import validate_sections,expand
  text=(BUILD/'seed0/stdout').read_text();lines=text.splitlines();at=next(i for i,l in enumerate(lines)if l.startswith('IRIS_HART_SECTION '));proof=validate_sections(expand('\n'.join(lines[:at+1]),self.c,partial=True),self.c,partial=True);self.assertEqual(len(proof['completed_hart_sections']),1);self.assertEqual(proof['completed_hart_sections'][0]['hart'],0)
 def test_two_handoff_proof(self):
  r=json.loads((BUILD/'protocol-proof.json').read_text());self.assertTrue(r['pass_']);self.assertEqual(r['MSIP_wakeups'],2);self.assertEqual(r['deadlocks'],0);self.assertTrue(r['omitted_IPI_detected_deadlock']);self.assertEqual(len(r['source_guard_controls']),3)
 def test_wire_exact17fields(self):
  import base64,struct
  from rvv_identify_compact_review import expand
  text=(BUILD/'seed0/stdout').read_text();line=next(l for l in text.splitlines()if l.startswith('IRIS_BIN '));raw=base64.b64decode(line.split(' ')[2],validate=True);self.assertEqual(len(raw),136);self.assertEqual(len(struct.unpack('<17Q',raw)),17);decoded=expand(text,self.c);r=json.loads(next(l.split(' ',1)[1]for l in decoded.splitlines()if l.startswith('IRIS_REGION ')));self.assertEqual(r['actual_record_uint64'],list(struct.unpack('<17Q',raw)));self.assertIn('compiledcase',r['data_origin'])
 def test_empty_or_missing_compact_record_refused(self):
  from rvv_identify_compact_review import validator
  text=(BUILD/'seed0/stdout').read_text();line=next(l for l in text.splitlines()if l.startswith('IRIS_BIN '))
  with self.assertRaises(ValueError):validator().validate(text.replace(line+'\n','',1),self.c)
if __name__=='__main__':unittest.main()
