#!/usr/bin/env python3
"""Inner-proof corruptions for the disjoint operator archive/math auditor."""
import copy,hashlib,importlib.util,io,json,tarfile,tempfile,unittest
from pathlib import Path
import audit_model_operators_independent as a
R=Path(__file__).resolve().parents[1]
class Controls(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  b=R/'build/model-operator-second-independent-audit-v2';cls.corpus=a.js((b/'corpus.json').read_bytes());cls.uart=(b/'uartlog').read_bytes();cls.math=a.math_all();cls.canonical=a.check_corpus(cls.corpus,cls.math);p=R/'firesim/audit_memory_routes_current_independent.py';a.need(a.hf(p)==a.HELPER_SHA,'Pinned helper');s=importlib.util.spec_from_file_location('audit_transport_control',p);cls.t=importlib.util.module_from_spec(s);s.loader.exec_module(cls.t)
  cur=a.js((R/'runs/fpga-model-operator-batch-v1-001/run.json').read_bytes());cls.current=cur;data,cls.ids,_=cls.t.read_archive(Path(cur['capture']['archive']),cur['capture']['captured_run_manifest_sha256']);cls.m=a.js(data['job/run.json']);cls.runtime=data['job/manager/config_runtime.yaml']
 def changed(self,tag,field,value):
  lines=self.uart.decode().splitlines();i=next(i for i,x in enumerate(lines)if x.startswith(tag+' '));r=a.js(lines[i].split(' ',1)[1]);r[field]=value(r[field])if callable(value)else value;lines[i]=tag+' '+json.dumps(r);return ('\n'.join(lines)+'\n').encode()
 def test_positive_independent_numerics(self):self.assertEqual(a.check_uart(self.uart,self.canonical,self.math)[1]['int32_words'],3072)
 def test_boolean_hart_equal_zero(self):
  with self.assertRaisesRegex(ValueError,'Typed'):a.check_uart(self.changed('IRIS_REGION','hart',False),self.canonical,self.math)
 def test_boolean_retirement(self):
  with self.assertRaisesRegex(ValueError,'Unsigned'):a.check_uart(self.changed('IRIS_REGION','instret_delta',True),self.canonical,self.math)
 def test_boolean_terminal_failed_equal_zero(self):
  with self.assertRaisesRegex(ValueError,'typed'):a.check_uart(self.changed('IRIS_BATCH_DONE','failed',False),self.canonical,self.math)
 def test_counter_reversal(self):
  with self.assertRaisesRegex(ValueError,'counter'):a.check_uart(self.changed('IRIS_REGION','end_cycle',0),self.canonical,self.math)
 def test_changed_checksum(self):
  with self.assertRaisesRegex(ValueError,'checksum'):a.check_uart(self.changed('IRIS_REGION','checksum',lambda v:v^1),self.canonical,self.math)
 def test_changed_actual_int32(self):
  with self.assertRaisesRegex(ValueError,'perword'):a.check_uart(self.changed('IRIS_WORDS','accumulator_u32',lambda v:[v[0]^1]+v[1:]),self.canonical,self.math)
 def test_changed_actual_W8A8(self):
  with self.assertRaisesRegex(ValueError,'perword'):a.check_uart(self.changed('IRIS_WORDS','W8A8_f32_words',lambda v:[v[0]^1]+v[1:]),self.canonical,self.math)
 def test_boolean_actual_word(self):
  with self.assertRaisesRegex(ValueError,'perword'):a.check_uart(self.changed('IRIS_WORDS','accumulator_u32',lambda v:[False]+v[1:]),self.canonical,self.math)
 def test_changed_embedded_golden(self):
  c=copy.deepcopy(self.corpus);c['cases'][0]['expected_words']['accumulator_u32'][0]^=1
  with self.assertRaisesRegex(ValueError,'corpus fullwords'):a.check_corpus(c,self.math)
 def test_missing_trial(self):
  text='\n'.join(x for x in self.uart.decode().splitlines()if '.trial2"'not in x)
  with self.assertRaisesRegex(ValueError,'Complete'):a.check_uart(text.encode(),self.canonical,self.math)
 def test_duplicate_JSON_field(self):
  text=self.uart.decode().replace('"hart":0','"hart":0,"hart":0',1)
  with self.assertRaisesRegex(ValueError,'Duplicate'):a.check_uart(text.encode(),self.canonical,self.math)
 def test_wrong_hart_role(self):
  with self.assertRaises(ValueError):a.check_uart(self.changed('IRIS_REGION','region','producer'),self.canonical,self.math)
 def test_corpus_bool_active_hart(self):
  c=copy.deepcopy(self.corpus);c['cases'][0]['active_harts'][0]=False
  with self.assertRaisesRegex(ValueError,'Typed'):a.check_corpus(c,self.math)
 def test_TinyLlama_unprotected(self):
  c=copy.deepcopy(self.corpus);c['TinyLlama_protected_validation_only']=False
  with self.assertRaisesRegex(ValueError,'Protected'):a.check_corpus(c,self.math)
 def test_source_hash_only_elsewhere_insufficient(self):
  ids=dict(self.ids);wanted=next(iter(self.m['input_sha256'].values()));ids.pop('job/prepared-inputs/'+wanted);ids['unrelated']=wanted
  with self.assertRaisesRegex(ValueError,'Named source'):a.additional_lifecycle(self.m,self.current,ids)
 def test_extra_runtime_change(self):
  with self.assertRaisesRegex(ValueError,'private-directory'):a.check_prepared(self.m,self.ids,self.runtime+b'# extra unapproved mutation\n')
 def test_changed_prepared_file(self):
  ids=dict(self.ids);ids['job/manager/config_build.yaml']='0'*64
  with self.assertRaisesRegex(ValueError,'Prepared bytes'):a.check_prepared(self.m,ids,self.runtime)
 def test_boolean_exit_zero(self):
  m=copy.deepcopy(self.m);m['commands'][0]['returncode']=False
  with self.assertRaisesRegex(ValueError,'Boolean'):a.additional_lifecycle(m,self.current,self.ids)
 def test_expired_grant(self):
  m=copy.deepcopy(self.m);m['commands'][0]['started_at_utc']='2030-01-01T00:00:00+00:00'
  with self.assertRaisesRegex(ValueError,'Authorization current'):a.additional_lifecycle(m,self.current,self.ids)
 def test_wrong_role(self):
  m=copy.deepcopy(self.m);m['campaign_role']='other'
  with self.assertRaisesRegex(ValueError,'experiment role'):a.additional_lifecycle(m,self.current,self.ids)
 def test_missing_owned_cleanup(self):
  m=copy.deepcopy(self.m);m['cleanup_status']='failed'
  with self.assertRaisesRegex(ValueError,'cleanup'):self.t.check_lifecycle(m,self.current,self.ids)
 def test_inventory_changed_bytes(self):
  with tempfile.TemporaryDirectory()as d:
   path=Path(d)/'bad.tar.gz';files={'job/run.json':b'{}\n','job/corpus.json':b'good'};inventory=dict(schema_version=1,hardware_contacted=False,files=[dict(path=n,bytes=len(v),sha256=a.hb(v))for n,v in files.items()])
   with tarfile.open(path,'w:gz')as t:
    for name,raw in list(files.items())+[('capture-manifest.json',json.dumps(inventory).encode())]:
     if name=='job/corpus.json':raw=b'evil'
     info=tarfile.TarInfo(name);info.size=len(raw);t.addfile(info,io.BytesIO(raw))
   with self.assertRaisesRegex(ValueError,'bytes differ'):self.t.read_archive(path,a.hb(files['job/run.json']))
 def test_inventory_untracked_member(self):
  with tempfile.TemporaryDirectory()as d:
   path=Path(d)/'extra.tar.gz';raw=b'{}';inv=dict(schema_version=1,hardware_contacted=False,files=[dict(path='job/run.json',bytes=2,sha256=a.hb(raw))])
   with tarfile.open(path,'w:gz')as t:
    for name,value in [('job/run.json',raw),('capture-manifest.json',json.dumps(inv).encode()),('untracked',b'!')]:
     info=tarfile.TarInfo(name);info.size=len(value);t.addfile(info,io.BytesIO(value))
   with self.assertRaisesRegex(ValueError,'uninventoried'):self.t.read_archive(path,a.hb(raw))
if __name__=='__main__':unittest.main(verbosity=2)
