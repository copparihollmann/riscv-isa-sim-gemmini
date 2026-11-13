"""Real frozen functional UART through the exact managed compact collector.

Only temporary copies of the packet are changed. No hardware/network action.
"""
import base64,copy,hashlib,json,struct,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;sys.path.insert(0,str(HERE))
import batch_runner as runner
import rvv_compute1320_review as review
BUILD=ROOT/'build/rvv-compute1320-v2'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class Collector(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.raw=(BUILD/'seed0/stdout').read_text();cls.corpus=json.loads((BUILD/'corpus.json').read_text());cls.ready=json.loads((BUILD/'ready.json').read_text());seed=json.loads((BUILD/'seed0/run.json').read_text())
  if seed.get('pass')is not True or seed.get('normal_guest_exit_verified')is not True or seed['exit_status']!=0:raise ValueError('Exact successful functional UART required')
  if sha(BUILD/'seed0/stdout')!=seed['stdout_sha256']or sha(BUILD/'guest.elf')!=review.ELF:raise ValueError('Exact UART/ELF identity')
  for name,h in cls.ready['artifact_sha256'].items():
   if sha(BUILD/name)!=h:raise ValueError('Frozen packet changed '+name)
  cls.bound=[HERE/'batch_runner.py',HERE/'rvv_compute1320_review.py',*[ROOT/'benchmarks/rvv_compute1320_v1'/n for n in('codec.py','validate.py','qualify.py','cases.py','build.py','protocol.py')],ROOT/'calibration/rvv-compute1320-v1/split.json']
  cls.before={str(p):sha(p)for p in cls.bound}
 @classmethod
 def tearDownClass(cls):
  for p,h in cls.before.items():
   if sha(p)!=h:raise ValueError('Source changed while testing '+p)
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='compute1320-collector-');self.addCleanup(self.tmp.cleanup);self.job=Path(self.tmp.name);self.manager=self.job/'manager';self.elf=self.manager/'workloads/iris-batch/batch.elf';self.elf.parent.mkdir(parents=True)
  self.elf.write_bytes((BUILD/'guest.elf').read_bytes())
  for n in('corpus.json','ready.json','layout.json','review.json'):(self.job/n).write_bytes((BUILD/n).read_bytes())
  self.uart=self.manager/'results-workload/test/uartlog';self.uart.parent.mkdir(parents=True)
  self.console=self.raw+'Script done [COMMAND_EXIT_CODE="0"]\n'
  self.m={'compact_collector':{'format':'IRIS_BIN_17Q_LE_base64_v1','review_path':str(HERE/'rvv_compute1320_review.py'),'review_sha256':sha(HERE/'rvv_compute1320_review.py'),'corpus_sha256':sha(self.job/'corpus.json'),'ready_sha256':sha(self.job/'ready.json'),'ELF_sha256':sha(self.elf)},'input_sha256':dict(self.before),'corpus_sha256':sha(self.job/'corpus.json'),'reviewed_ready_sha256':sha(self.job/'ready.json'),'elf_sha256':sha(self.elf),'campaign_role':review.ROLE,'prepared_file_sha256':{n:sha(self.job/n)for n in('layout.json','review.json')},'cases':review.flatten(self.corpus),'expected_regions':1320,'image':{'sha256':'f'*64},'require_regions':True,'require_goldens':True}
 def collect(self):
  self.uart.write_text(self.console);runner.collect_guest_results(self.manager,self.m);return self.m
 def refused(self):
  with self.assertRaises((ValueError,RuntimeError,AssertionError,KeyError,TypeError,struct.error)):self.collect()
 def change_word(self,positions):
  line=next(x for x in self.console.splitlines()if x.startswith('IRIS_BIN '));parts=line.split(' ');words=list(struct.unpack('<17Q',base64.b64decode(parts[2],validate=True)))
  for index in positions:words[index]^=1
  changed=parts[0]+' '+parts[1]+' '+base64.b64encode(struct.pack('<17Q',*words)).decode();self.console=self.console.replace(line,changed,1)
 def test_actual_complete_success(self):
  m=self.collect();self.assertEqual(len(m['regions']),1320);self.assertIs(m['compact_console_validation']['normal_completion'],True);self.assertEqual(m['console_process_exit_codes'],[0]);self.assertIs(m['region_checksums_independently_validated'],True)
 def test_missing_exit(self):self.console=self.raw;self.refused()
 def test_duplicate_zero_exit(self):self.console+='[COMMAND_EXIT_CODE="0"]\n';self.refused()
 def test_nonzero_exit(self):self.console=self.console.replace('[COMMAND_EXIT_CODE="0"]','[COMMAND_EXIT_CODE="1"]');self.refused()
 def test_extra_negative_exit(self):self.console+='[COMMAND_EXIT_CODE="-1"]\n';self.refused()
 def test_extra_NaN_exit(self):self.console+='[COMMAND_EXIT_CODE="NaN"]\n';self.refused()
 def test_broken_bracket_exit(self):self.console=self.console.replace('[COMMAND_EXIT_CODE="0"]','COMMAND_EXIT_CODE="0"');self.refused()
 def test_missing_final_record(self):
  line=[x for x in self.console.splitlines()if x.startswith('IRIS_BIN ')][-1];self.console=self.console.replace(line+'\n','',1);self.refused()
 def test_duplicate_record(self):
  line=next(x for x in self.console.splitlines()if x.startswith('IRIS_BIN '));self.console=self.console.replace(line,line+'\n'+line,1);self.refused()
 def test_truncated_base64(self):
  line=next(x for x in self.console.splitlines()if x.startswith('IRIS_BIN '));self.console=self.console.replace(line,line[:-1],1);self.refused()
 def test_wrong_actual_word(self):self.change_word((8,));self.refused()
 def test_self_consistent_wrong_golden(self):self.change_word((8,9));self.refused()
 def test_missing_Done(self):
  self.console='\n'.join(x for x in self.console.splitlines()if not x.startswith('IRIS_BATCH_DONE '))+'\n';self.refused()
 def test_missing_section_footer(self):
  line=next(x for x in self.console.splitlines()if x.startswith('IRIS_HART_SECTION '));self.console=self.console.replace(line+'\n','',1);self.refused()
 def test_changed_ELF(self):
  raw=bytearray(self.elf.read_bytes());raw[-1]^=1;self.elf.write_bytes(raw);self.refused()
 def test_changed_corpus(self):
  c=copy.deepcopy(self.corpus);c['cases'][0]['vl']+=1;(self.job/'corpus.json').write_text(json.dumps(c));self.refused()
 def test_changed_ready(self):
  p=self.job/'ready.json';p.write_text(p.read_text()+' ');self.refused()
 def test_changed_reader_digest(self):self.m['compact_collector']['review_sha256']='0'*64;self.refused()
 def test_changed_transitive_reader_binding(self):self.m['input_sha256'][str(ROOT/'benchmarks/rvv_compute1320_v1/codec.py')]='0'*64;self.refused()
 def test_changed_layout(self):
  p=self.job/'layout.json';p.write_text(p.read_text()+' ');self.refused()
 def test_wrong_compiled_table_proof_rebound_hash(self):
  p=self.job/'review.json';d=json.loads(p.read_text());d['compiled_and_layout_proof']['compiled_case_records']=1319;p.write_text(json.dumps(d));self.m['prepared_file_sha256']['review.json']=sha(p);self.refused()
 def test_wrong_host_case_table(self):self.m['cases'][0]['active_harts']=[1];self.refused()
 def test_wrong_format_or_role(self):self.m['campaign_role']='other';self.refused()
 def test_partial_hart0_is_not_full_completion(self):
  at=self.console.index('IRIS_HART_BEGIN {"hart":1');self.console=self.console[:at]+'[COMMAND_EXIT_CODE="0"]\n';self.refused()

if __name__=='__main__':
 import argparse,io
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False);stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(Collector);result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite);(o/'tests.log').write_text(stream.getvalue());inputs={str(x):sha(x)for x in[Path(__file__).resolve(),HERE/'batch_runner.py',HERE/'rvv_compute1320_review.py',BUILD/'ready.json',BUILD/'guest.elf',BUILD/'corpus.json',BUILD/'seed0/run.json',BUILD/'seed0/stdout',*[ROOT/'benchmarks/rvv_compute1320_v1'/n for n in('codec.py','validate.py','qualify.py','protocol.py')]]};report={'schema':'iris.compute1320_managed_compact_collector_controls.v1','pass':result.wasSuccessful(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'actual_frozen_functional_UART':True,'hardware_contacted':False,'protected_timing_labels_consumed':False,'input_sha256':inputs};(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':result.wasSuccessful(),'tests':result.testsRun,'report':str(o/'report.json'),'sha256':sha(o/'report.json')}));sys.exit(0 if result.wasSuccessful()else 1)
