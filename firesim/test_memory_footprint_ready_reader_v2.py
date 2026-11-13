import hashlib,io,sys,tarfile,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze_memory_footprints_mtime_groups_v2 import ready_member
class ReadyReader(unittest.TestCase):
 def fixture(self,raw=b'{"schema":"test"}',kind=tarfile.REGTYPE):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);p=Path(tmp.name)/'a.tar.gz'
  with tarfile.open(p,'w:gz')as t:
   info=tarfile.TarInfo('job/ready.json');info.type=kind;info.size=len(raw)if kind==tarfile.REGTYPE else 0;t.addfile(info,io.BytesIO(raw)if info.size else None)
  return p,raw
 def test_exact_bytes(self):
  p,r=self.fixture();self.assertEqual(ready_member(p,{'job/ready.json':hashlib.sha256(r).hexdigest()}),r)
 def test_changed_bytes(self):
  p,r=self.fixture()
  with self.assertRaises(ValueError):ready_member(p,{'job/ready.json':'0'*64})
 def test_missing_inventory(self):
  p,r=self.fixture()
  with self.assertRaises(ValueError):ready_member(p,{})
 def test_nonregular_member(self):
  p,r=self.fixture(kind=tarfile.DIRTYPE)
  with self.assertRaises(ValueError):ready_member(p,{'job/ready.json':hashlib.sha256(r).hexdigest()})
if __name__=='__main__':unittest.main()
