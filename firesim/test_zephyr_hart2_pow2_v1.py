#!/usr/bin/env python3
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from hart2_pow2_managed_protocol_v1 import validate_console,cases
from prepare_zephyr_hart2_pow2_v1 import admit,merge
from batch_runner import digest,collect_guest_results
NORMAL=(ROOT/'build/zephyr-hart2-pow2-normal-seed0-v4/stdout').read_text();Q=ROOT/'build/zephyr-hart2-pow2-qualified-v2'
class Checks(unittest.TestCase):
 def test_full_actual_words(self):self.assertEqual(validate_console(NORMAL)['independent_elements'],181440)
 def changed(self,token,key,value):
  rows=NORMAL.splitlines();i=next(i for i,s in enumerate(rows)if s.startswith(token+' '));obj=json.loads(rows[i].partition(' ')[2]);obj[key]=value;rows[i]=token+' '+json.dumps(obj)
  with self.assertRaises(ValueError):validate_console('\n'.join(rows))
 def test_uart(self):self.changed('IRIS_UART_PROFILE','divisor',4339)
 def test_uart_bool(self):self.changed('IRIS_UART_PROFILE','clock_hz',True)
 def test_missing_profile(self):
  with self.assertRaises(ValueError):validate_console('\n'.join(s for s in NORMAL.splitlines()if not s.startswith('IRIS_UART_PROFILE ')))
 def test_duplicate_profile(self):
  with self.assertRaises(ValueError):validate_console(NORMAL+next(s for s in NORMAL.splitlines()if s.startswith('IRIS_UART_PROFILE ')))
 def test_counter_bool(self):self.changed('IRIS_REGION','start_cycle',True)
 def test_checksum(self):self.changed('IRIS_REGION','checksum',0)
 def test_wrong_controller(self):self.changed('IRIS_H2_CONTROL_READY','physical_hart',0)
 def test_missing_trial(self):
  with self.assertRaises(ValueError):validate_console('\n'.join(s for s in NORMAL.splitlines()if not s.startswith('IRIS_REGION ')or json.loads(s.partition(' ')[2])['trial']!=2))
 def test_word(self):self.changed('IRIS_DATA','little_endian_hex','00')
 def test_real_skip_not_normal(self):
  with self.assertRaises(ValueError):validate_console((ROOT/'build/zephyr-hart2-pow2-skip-seed0-v4/stdout').read_text())
 def test_footer_bool(self):self.changed('IRIS_BATCH_DONE','failed',False)
 def test_hart2_no_region(self):self.assertEqual({h for c in cases()for h in c['active_harts']},{0,1})
 def test_exact_cases(self):self.assertEqual((len(cases()),sum(len(c['active_harts'])for c in cases())),(486,648))
 def test_admission(self):self.assertEqual(admit(Q,digest(Q/'ready.json'))[0]['required_elements'],181440)
 def test_wrong_ready(self):
  with self.assertRaises(ValueError):admit(Q,'0'*64)
 def test_merge_relative_foreigncwd(self):
  ids={};name='benchmarks/zephyr_hart2_pow2_v4/split.json';merge(ids,{name:digest(ROOT/name)});self.assertEqual(list(ids),[str((ROOT/name).resolve())])
 def test_conflict(self):
  p=ROOT/'benchmarks/zephyr_hart2_pow2_v4/split.json'
  with self.assertRaises(ValueError):merge({str(p):'0'*64},{str(p):digest(p)})
 def test_unchanged_collector_actual(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp);u=p/'results-workload/test/iris-batch0';u.mkdir(parents=True);(u/'uartlog').write_text(NORMAL+'\nScript done on 2026-11-07 15:00:00+00:00 [COMMAND_EXIT_CODE="0"]\n');manifest=dict(cases=cases(),elf_sha256='a'*64,image=dict(sha256='b'*64),require_regions=True,require_goldens=True);collect_guest_results(p,manifest);self.assertEqual(len(manifest['regions']),648);self.assertIs(manifest['region_checksums_independently_validated'],True)
if __name__=='__main__':unittest.main()
