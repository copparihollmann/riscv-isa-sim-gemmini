#!/usr/bin/env python3
"""Mixed native protocol plus real host-envelope grammar; no hardware."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from fpga_mixed9_v1 import validate,host_cases,binary_proof,ELF
from batch_runner import digest,collect_guest_results
from prepare_zephyr_mixed9_v1 import admit,merge
QUAL=ROOT/'build/zephyr-fpga-mixed9-qualification-v1'
TEXT=(ROOT/'build/zephyr-fpga-mixed9-seed0-v1/stdout').read_text()
SCALAR=(ROOT/'build/zephyr-scalar6-FPGA-HARDWARE-validated-v3/uartlog').read_text()
WRAPPER=(ROOT/'build/zephyr-scalar6-FPGA-HARDWARE-validated-v3/sim-run.sh').read_text()
# Actual source-bound scalar host envelope is reused only as a host-parser
# fixture around actual mixed native output. This is not mixed FPGA evidence.
FULL=SCALAR.splitlines()[0]+'\n'+TEXT+'\n*** PASSED ***\n'+SCALAR.splitlines()[-1]+'\n'

class Checks(unittest.TestCase):
 def mutate(self,kind,fn):
  lines=TEXT.splitlines();i=next(i for i,x in enumerate(lines)if x.startswith(kind+' '));r=json.loads(lines[i].split(' ',1)[1]);fn(r);lines[i]=kind+' '+json.dumps(r)
  with self.assertRaises(ValueError):validate('\n'.join(lines))
 def test_actual_native9(self):self.assertEqual(validate(TEXT)['regions'],9)
 def test_host_envelope(self):self.assertIs(validate(FULL,True,WRAPPER)['driver_exit_verified'],True)
 def test_checksum(self):self.mutate('IRIS_REGION',lambda r:r.update(checksum=r['checksum']+1))
 def test_hart_bool(self):self.mutate('IRIS_REGION',lambda r:r.update(hart=False))
 def test_wrong_mask(self):self.mutate('IRIS_REGION',lambda r:r.update(hart_mask=3))
 def test_counter_bool(self):self.mutate('IRIS_REGION',lambda r:r.update(instret_delta=True))
 def test_counter_reverse(self):self.mutate('IRIS_REGION',lambda r:r.update(end_cycle=r['start_cycle']))
 def test_profile(self):self.mutate('IRIS_UART_PROFILE',lambda r:r.update(divisor=4339))
 def test_footer_bool(self):self.mutate('IRIS_BATCH_DONE',lambda r:r.update(failed=False))
 def test_hart2_vme_claim(self):
  text=TEXT.replace('"role":"vector.copy"','"role":"vme.compute"')
  self.assertNotEqual(text,TEXT)
  with self.assertRaises(ValueError):validate(text)
 def test_wrong_VME_sum(self):
  rows=TEXT.splitlines();i=next(i for i,x in enumerate(rows)if x.startswith('IRIS_REGION ')and 'zephyr.vme.yield'in x);r=json.loads(rows[i].split(' ',1)[1]);r['checksum']=1025;rows[i]='IRIS_REGION '+json.dumps(r)
  with self.assertRaises(ValueError):validate('\n'.join(rows))
 def test_duplicate_missing(self):
  row=next(x for x in TEXT.splitlines()if x.startswith('IRIS_REGION '))
  for text in [TEXT+row+'\n',TEXT.replace(row+'\n','',1),TEXT.replace('IRIS_BATCH_DONE','PARTIAL',1)]:
   with self.assertRaises(ValueError):validate(text)
 def test_driver_exit_controls(self):
  footer=SCALAR.splitlines()[-1]
  for marker in [footer[:-1],footer+'junk','prefix'+footer,footer.replace('"0"','"124"'),'[COMMAND_EXIT_CODE="0"]',footer+'\n'+footer,'COMMAND_EXIT_CODE="0"','']:
   with self.assertRaises(ValueError):validate(FULL.replace(footer,marker),True,WRAPPER)
 def test_no_host_wrapper_fabrication(self):
  with self.assertRaises(ValueError):validate(FULL,True)
 def test_runner_collector(self):
  with tempfile.TemporaryDirectory()as d:
   manager=Path(d);logs=manager/'results-workload/test/iris-batch0';logs.mkdir(parents=True);(logs/'uartlog').write_text(FULL);m=dict(cases=host_cases(),elf_sha256=ELF,image=dict(sha256='a'*64),require_regions=True,require_goldens=True);collect_guest_results(manager,m);self.assertEqual(len(m['regions']),9);self.assertIs(m['region_checksums_independently_validated'],True)
 def test_admission_and_body(self):
  ready,q,corpus,cases,elf,ids=admit(QUAL,digest(QUAL/'ready.json'));self.assertEqual(len(cases),3);self.assertEqual(binary_proof(elf)['MM_commands_per_worker'],32)
 def test_wrong_ready(self):
  with self.assertRaises(ValueError):admit(QUAL,'0'*64)
 def test_changed_binary(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'bad.elf';raw=bytearray((ROOT/'build/zephyr-firesim-uart/5e6/mixed-build/zephyr/zephyr.elf').read_bytes());raw[-1]^=1;p.write_bytes(raw)
   with self.assertRaises(ValueError):binary_proof(p)
 def test_modified_qualification(self):
  for change in ['patch','MM_count']:
   with tempfile.TemporaryDirectory()as d:
    p=Path(d);r=json.loads((QUAL/'ready.json').read_text());q=json.loads((QUAL/'qualification.json').read_text());(p/'corpus.json').write_bytes((QUAL/'corpus.json').read_bytes())
    if change=='patch':q['source_overlay']=None
    else:q['binary_proof']['MM_commands_per_worker']=31
    (p/'qualification.json').write_text(json.dumps(q));r['qualification_sha256']=digest(p/'qualification.json');(p/'ready.json').write_text(json.dumps(r))
    with self.assertRaises(ValueError):admit(p,digest(p/'ready.json'))
 def test_conflicting_digest(self):
  p=ROOT/'zephyr/fpga_mixed9_v1.py';ids={};merge(ids,{'zephyr/fpga_mixed9_v1.py':digest(p)});self.assertEqual(list(ids),[str(p)])
  with self.assertRaises(ValueError):merge(ids,{str(p):'0'*64})

if __name__=='__main__':unittest.main()
