#!/usr/bin/env python3
"""Controls for the disjoint stdlib-only memory evidence auditor."""
import copy,hashlib,io,json,struct,tarfile,tempfile,unittest
from pathlib import Path
import audit_memory_routes_current_independent as a
ROOT=Path(__file__).resolve().parents[1]
B=ROOT/'build/memory-routes-current-v1'
class Controls(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  c.corpus=json.loads((B/'corpus.json').read_text());c.cases=a.check_corpus(c.corpus);c.elf=(B/'memory-routes.elf').read_bytes();c.layout=json.loads((B/'readback-layout.json').read_text());c.uart=(B/'seed0/run.stdout').read_bytes()
 def test_positive_independent_math_elf_uart(self):
  self.assertEqual(a.check_elf(self.elf,self.cases,self.layout)['compiled_goldens'],4536)
  self.assertEqual(a.check_uart(self.uart,self.cases)[1]['regions'],2592)
 def test_wrong_role(self):
  with self.assertRaisesRegex(ValueError,'role'):a.check_role({'campaign_role':'compute_fit','expected_regions':1008})
 def test_changed_corpus(self):
  c=copy.deepcopy(self.corpus);c['cases'][0]['base']+=64
  with self.assertRaises(ValueError):a.check_corpus(c)
 def test_changed_uart_word(self):
  lines=self.uart.decode().splitlines();i=next(i for i,l in enumerate(lines)if l.startswith('IRIS_REGION '));r=json.loads(lines[i][12:]);r['checksum']^=1;lines[i]='IRIS_REGION '+json.dumps(r)
  with self.assertRaisesRegex(ValueError,'checksum'):a.check_uart(('\n'.join(lines)+'\n').encode(),self.cases)
 def test_truncated_uart(self):
  with self.assertRaises(ValueError):a.check_uart(self.uart[:len(self.uart)//2],self.cases)
 def test_typed_uart(self):
  lines=self.uart.decode().splitlines();i=next(i for i,l in enumerate(lines)if l.startswith('IRIS_REGION '));r=json.loads(lines[i][12:]);r['hart']=False;lines[i]='IRIS_REGION '+json.dumps(r)
  with self.assertRaises(ValueError):a.check_uart(('\n'.join(lines)+'\n').encode(),self.cases)
 def test_changed_compiled_word_beyond_outer_hash(self):
  e=a.Elf(self.elf);addr=e.syms['experiments'][0]+40
  base,off=next((base,off)for base,off,fs,ms in e.loads if base<=addr<base+fs);pos=off+addr-base
  changed=bytearray(self.elf);changed[pos]^=1
  with self.assertRaisesRegex(ValueError,'goldens'):a.check_elf(bytes(changed),self.cases,self.layout)
 def test_swapped_compiled_case_order(self):
  e=a.Elf(self.elf);addr=e.syms['experiments'][0];base,off=next((b,o)for b,o,fs,ms in e.loads if b<=addr< b+fs);pos=off+addr-base
  changed=bytearray(self.elf);changed[pos:pos+128]=changed[pos+64:pos+128]+changed[pos:pos+64]
  with self.assertRaisesRegex(ValueError,'order'):a.check_elf(bytes(changed),self.cases,self.layout)
 def test_truncated_elf(self):
  with self.assertRaises(ValueError):a.check_elf(self.elf[:70],self.cases,self.layout)
 def archive(self,path,change=False,extra=False):
  files={'job/run.json':b'{}\n','job/corpus.json':b'{"fixture":true}\n'}
  rows=[{'path':n,'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()}for n,v in files.items()]
  inv={'schema_version':1,'hardware_contacted':False,'files':rows}
  with tarfile.open(path,'w:gz')as t:
   for n,v in list(files.items())+[('capture-manifest.json',(json.dumps(inv)+'\n').encode())]:
    if change and n=='job/corpus.json':v=v.replace(b'true',b'null')
    info=tarfile.TarInfo(n);info.size=len(v);t.addfile(info,io.BytesIO(v))
   if extra:
    info=tarfile.TarInfo('unknown');info.size=1;t.addfile(info,io.BytesIO(b'!'))
  return hashlib.sha256(files['job/run.json']).hexdigest()
 def test_inventory_positive_and_changed_bytes(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'good.tgz';expected=self.archive(p);self.assertEqual(len(a.read_archive(p,expected)[1]),2)
   q=Path(d)/'changed.tgz';self.archive(q,change=True)
   with self.assertRaisesRegex(ValueError,'bytes differ'):a.read_archive(q,expected)
 def test_inventory_uninventoried(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'extra.tgz';expected=self.archive(p,extra=True)
   with self.assertRaisesRegex(ValueError,'Uninventoried|uninventoried'):a.read_archive(p,expected)
 def test_inventory_truncated(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'good.tgz';expected=self.archive(p);p.write_bytes(p.read_bytes()[:30])
   with self.assertRaises((EOFError,tarfile.TarError,OSError)):a.read_archive(p,expected)
if __name__=='__main__':unittest.main(verbosity=2)
