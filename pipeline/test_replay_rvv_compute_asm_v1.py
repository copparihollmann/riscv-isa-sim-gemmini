"""Actual native readback mutations, never hardware/reference timing labels."""
import copy,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'pipeline'))
import replay_rvv_compute_asm_v1 as r
B=ROOT/'build/rvv-compute-asm-v5';RUN=ROOT/'build/rvv-compute-asm-C12-inherited-v1';INPUT=ROOT/'build/rvv-compute-asm-C12-model-inputs-v1'
class Replay(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=json.loads((B/'corpus.json').read_text());cls.layout=json.loads((B/'layout.json').read_text());cls.text=(RUN/'stderr').read_text()
 def test_actual_complete(self):self.assertEqual(len(r.decode(self.text,self.c,self.layout)),1320)
 def changed(self,index,value):
  lines=self.text.splitlines();lines[index+1]='0x%016x'%value;return '\n'.join(lines)+'\n'
 def test_sentinel_not_complete(self):
  with self.assertRaises(ValueError):r.decode(self.changed(0,2**64-1),self.c,self.layout)
 def test_after_sentinel_not_stable(self):
  with self.assertRaises(ValueError):r.decode(self.changed(2+1320*17,2**64-1),self.c,self.layout)
 def test_after_count_not_stable(self):
  with self.assertRaises(ValueError):r.decode(self.changed(3+1320*17,587),self.c,self.layout)
 def test_wrong_hart(self):
  with self.assertRaises(ValueError):r.decode(self.changed(3,2),self.c,self.layout)
 def test_wrong_checksum(self):
  with self.assertRaises(ValueError):r.decode(self.changed(2+8,0),self.c,self.layout)
 def test_missing_record(self):
  lines=self.text.splitlines();del lines[3]
  with self.assertRaises(ValueError):r.decode('\n'.join(lines),self.c,self.layout)
 def test_wrong_parked_pc(self):
  with self.assertRaises(ValueError):r.decode(self.changed(2+1320*17+2,0x80000412),self.c,self.layout)
 def test_actual_CSR_ELF_join(self):
  rows=r.decode(self.text,self.c,self.layout);proof=r.qualify_prefix(RUN/'features.jsonl',rows,B/'guest.elf',ROOT/'board/evidence/bootrom.rv64.img');self.assertEqual(proof['actual_CSR_ELF_endpoint_joins'],3960)
 def test_prefix_bool_and_changed_opcode(self):
  for key,value in [('sequence',True),('raw',0),('csr',True),('result_discarded',True)]:
   with tempfile.TemporaryDirectory()as td:
    raw=(RUN/'features.jsonl').read_text().splitlines();obj=json.loads(raw[0]);obj[key]=value;raw[0]=json.dumps(obj);path=Path(td)/'prefix.jsonl';path.write_text('\n'.join(raw)+'\n')
    with self.assertRaises((ValueError,KeyError)):r.qualify_prefix(path,r.decode(self.text,self.c,self.layout),B/'guest.elf',ROOT/'board/evidence/bootrom.rv64.img')
 def test_only_eligible_fourteen_rules_zero(self):
  a=(INPUT/'inherited.fixture').read_text().splitlines();b=(INPUT/'ownzero.fixture').read_text().splitlines();self.assertEqual(len(a),len(b));changed=0;families=[]
  for x,y in zip(a,b):
   x=x.split();y=y.split()
   if x==y:continue
   if x[0]=='empirical_profile':self.assertEqual(x[:2]+x[3:],y[:2]+y[3:]);continue
   self.assertEqual(x[:4]+x[6:],y[:4]+y[6:]);self.assertEqual(x[0],'empirical_family');self.assertIn(x[1],('0','1'));self.assertEqual(y[4:6],['0','0']);changed+=2;families.append(x[2])
  self.assertEqual(changed,28);self.assertEqual(len(families),14);self.assertEqual(families.count('rvv.integer'),2)
 def test_plan_not_authorized_or_fitted(self):
  p=json.loads((INPUT/'fit-plan.json').read_text());self.assertIs(p['fit_authorized'],False);self.assertIs(p['hardware_timing_labels_consumed'],False);self.assertEqual((p['TRAIN_rows_required'],p['reserved_rows_root_only'],p['parameters']),(978,342,13))
if __name__=='__main__':unittest.main()
