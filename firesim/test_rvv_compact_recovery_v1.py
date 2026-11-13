"""Synthetic gate controls using real functional wire; no hardware/timing labels."""
import base64,copy,hashlib,io,json,sys,tarfile,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze_rvv_identify_compact_recovery_v1 import recover_collection_outcome,original_read_archive,parse_regions,validator,flatten,ELF
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build/rvv-identify-compact-v1'
class Recovery(unittest.TestCase):
 def setUp(self):
  self.c=json.loads((BUILD/'corpus.json').read_text());self.text=(BUILD/'seed0/stdout').read_text()+'COMMAND_EXIT_CODE="0"\n';self.m=dict(status='failed',error=None,cleanup_status='passed',cleanup_error=None,commands=[dict(task=t,status='passed',returncode=0,timed_out=False,cleanup_phase=i==3)for i,t in enumerate(['kill','infrasetup','runworkload','kill'])],console_process_exit_codes=[0],cases=flatten(self.c),elf_sha256=ELF,image=dict(sha256='0'*64))
  try:parse_regions(self.text,self.m['cases'],ELF,'0'*64,True,True)
  except ValueError as e:self.m['error']=str(e)
 def check(self,m=None,text=None):
  m=m or self.m;text=self.text if text is None else text;r=recover_collection_outcome(copy.deepcopy(m),m,text);v=validator().validate(text,self.c);return r,v
 def test_positive_collection_failure_only(self):
  r,v=self.check();self.assertFalse(r['original_runner_passed']);self.assertEqual(v['regions'],1908);self.assertEqual(v['checked_words'],225888)
 def test_nonzero_guest_exit(self):
  m=copy.deepcopy(self.m);m['console_process_exit_codes']=[124]
  with self.assertRaises(ValueError):self.check(m,self.text.replace('COMMAND_EXIT_CODE="0"','COMMAND_EXIT_CODE="124"'))
 def test_missing_exit(self):
  with self.assertRaises(ValueError):self.check(text=self.text.replace('COMMAND_EXIT_CODE="0"',''))
 def test_wrong_error(self):
  m=copy.deepcopy(self.m);m['error']='Guest failed'
  with self.assertRaises(ValueError):self.check(m)
 def test_changed_missing_list(self):
  m=copy.deepcopy(self.m);m['error']=m['error'][:-1]
  with self.assertRaises(ValueError):self.check(m)
 def test_timedout_phase(self):
  m=copy.deepcopy(self.m);m['commands'][2].update(status='timed_out',returncode=124,timed_out=True)
  with self.assertRaises(ValueError):self.check(m)
 def test_cleanup_failure(self):
  m=copy.deepcopy(self.m);m['cleanup_error']='not owned';m['cleanup_status']='refused_or_failed'
  with self.assertRaises(ValueError):self.check(m)
 def test_retained_lock(self):
  m=copy.deepcopy(self.m);m['lock_retained_for_operator']=True
  with self.assertRaises(ValueError):self.check(m)
 def test_already_passed_runner_not_reclassified(self):
  m=copy.deepcopy(self.m);m['status']='completed_uncertified';m['error']=None
  with self.assertRaises(ValueError):self.check(m)
 def test_missing_Done(self):
  with self.assertRaises(ValueError):self.check(text='\n'.join(l for l in self.text.splitlines()if not l.startswith('IRIS_BATCH_DONE '))+'\n')
 def test_truncated_payload(self):
  line=next(l for l in self.text.splitlines()if l.startswith('IRIS_BIN '))
  with self.assertRaises(ValueError):self.check(text=self.text.replace(line,line[:-1],1))
 def test_changed_both_checksums_cannot_forge_pass(self):
  import struct
  line=next(l for l in self.text.splitlines()if l.startswith('IRIS_BIN '));parts=line.split(' ');values=list(struct.unpack('<17Q',base64.b64decode(parts[2])));values[8]=values[9]=0;parts[2]=base64.b64encode(struct.pack('<17Q',*values)).decode()
  with self.assertRaises(ValueError):self.check(text=self.text.replace(line,' '.join(parts),1))
 def test_injected_JSON_region(self):
  with self.assertRaises(ValueError):self.check(text=self.text+'IRIS_REGION {}\n')
 def test_archive_byte_inventory(self):
  files={'job/run.json':b'{"schema":"synthetic-inventory-control"}','job/example':b'owned-source-bytes'};ids={k:hashlib.sha256(v).hexdigest()for k,v in files.items()};inventory=json.dumps(dict(files=[dict(path=k,bytes=len(v),sha256=ids[k])for k,v in files.items()])).encode()
  with tempfile.TemporaryDirectory()as td:
   def make(name,changed=False):
    p=Path(td)/name
    with tarfile.open(p,'w:gz')as t:
     for k,v in dict(files,**{'capture-manifest.json':inventory}).items():
      if changed and k=='job/example':v=b'changed-source-byt'
      info=tarfile.TarInfo(k);info.size=len(v);t.addfile(info,io.BytesIO(v))
    return p
   data,got=original_read_archive(make('good.tgz'),ids['job/run.json']);self.assertEqual(got,ids)
   with self.assertRaises(ValueError):original_read_archive(make('bad.tgz',True),ids['job/run.json'])
if __name__=='__main__':unittest.main()
