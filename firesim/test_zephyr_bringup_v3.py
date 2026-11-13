#!/usr/bin/env python3
"""Counterfactuals use the actual captured util-linux header/footer/wrapper."""
import json,sys,tarfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from script_envelope_v3 import validate_envelope
from fpga_bringup_v2 import validate
from batch_runner import digest
JOB=ROOT/'runs/fpga-zephyr-scalar6-bringup-v2-001';CAP=json.loads((JOB/'run.json').read_text())['capture'];ARCHIVE=Path(CAP['archive'])
assert digest(ARCHIVE)==CAP['archive_sha256']=='933547eca11144bcd8a00e882f0e06df7c82b72285d74ca9a3782105c88d6723'
with tarfile.open(ARCHIVE,'r:gz')as t:
 TEXT=t.extractfile('job/optional-observability/uartlog').read().decode('utf-8','strict');WRAPPER=t.extractfile('job/optional-observability/sim-run.sh').read().decode('utf-8','strict')
HEADER=TEXT.splitlines()[0];FOOTER=TEXT.splitlines()[-1]

class Checks(unittest.TestCase):
 def refuse(self,text,wrapper=WRAPPER):
  with self.assertRaises(ValueError):validate_envelope(text,wrapper)
 def test_actual_guest_and_envelope(self):
  self.assertEqual(validate(TEXT,False)['regions'],6);self.assertIs(validate_envelope(TEXT,WRAPPER)['normal_driver_exit_zero'],True)
 def test_exit124(self):self.refuse(TEXT.replace('COMMAND_EXIT_CODE="0"','COMMAND_EXIT_CODE="124"'))
 def test_timestamp_junk(self):self.refuse(TEXT.replace(FOOTER,FOOTER.replace('2026-11-07','2026-99-07')))
 def test_timestamp_syntax(self):self.refuse(TEXT.replace(FOOTER,FOOTER.replace('12:57:07','junk')))
 def test_timestamp_reverse(self):self.refuse(TEXT.replace(FOOTER,FOOTER.replace('12:57:07','12:56:07')))
 def test_timestamp_unbounded(self):self.refuse(TEXT.replace(FOOTER,FOOTER.replace('12:57:07','22:57:07')))
 def test_duplicate_footer(self):self.refuse(TEXT+FOOTER+'\n')
 def test_injected_prefix(self):self.refuse(TEXT.replace(FOOTER,'junk '+FOOTER))
 def test_injected_suffix(self):self.refuse(TEXT.replace(FOOTER,FOOTER+' junk'))
 def test_missing_closing_bracket(self):self.refuse(TEXT.replace(FOOTER,FOOTER[:-1]))
 def test_unbracketed(self):self.refuse(TEXT.replace('[COMMAND_EXIT_CODE="0"]','COMMAND_EXIT_CODE="0"'))
 def test_missing_footer(self):self.refuse(TEXT.replace(FOOTER,''))
 def test_wrong_header(self):self.refuse(TEXT.replace('Script started on','Script began on',1))
 def test_wrong_header_command(self):self.refuse(TEXT.replace(HEADER,HEADER.replace('+fesvr-step-size=128','+fesvr-step-size=129')))
 def test_duplicate_header(self):self.refuse(HEADER+'\n'+TEXT)
 def test_missing_header(self):self.refuse(TEXT[len(HEADER)+1:])
 def test_header_prefix(self):self.refuse('junk'+TEXT)
 def test_header_terminal_junk(self):self.refuse(TEXT.replace('TERM="screen"','TERM="junk"',1))
 def test_marker_injected_in_body(self):self.refuse(TEXT.replace(FOOTER,'[COMMAND_EXIT_CODE="0"]\n'+FOOTER))
 def test_claimed_pass_only(self):self.refuse('*** PASSED ***\n[COMMAND_EXIT_CODE="0"]\n')
 def test_wrong_sim_run(self):self.refuse(TEXT,WRAPPER.replace('+fesvr-step-size=128','+fesvr-step-size=129'))
 def test_sim_run_trailing_command(self):self.refuse(TEXT,WRAPPER+'echo fake\n')
 def test_driver_failure(self):self.refuse(TEXT.replace('*** PASSED ***','*** FAILED ***'))
 def test_standalone_v2_is_not_actual_script_envelope(self):self.refuse(TEXT.replace(FOOTER,'[COMMAND_EXIT_CODE="0"]'))

if __name__=='__main__':unittest.main()
