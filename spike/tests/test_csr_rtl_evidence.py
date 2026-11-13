"""Decode actual mailbox layout without trusting the reference's parsed summary."""
import importlib.util
from pathlib import Path
import unittest
MODULE=Path(__file__).resolve().parents[1]/'csr_rtl_evidence.py'
spec=importlib.util.spec_from_file_location('csr_rtl_evidence_test',MODULE)
rtl=importlib.util.module_from_spec(spec);spec.loader.exec_module(rtl)
class SelectedCsrSignatureTests(unittest.TestCase):
    def raw(self,words):return '\n'.join(f'{w:016x}' for w in words)+'\n'
    def rdtime(self):return [0x4952495350524f42,1,2,0]+[5,1,1,2,0x800002ca,0xc01022f3,5,1]*3
    def test_three_hart_time_trap(self):
        rows=rtl.decode_signature(self.raw(self.rdtime()),'rdtime');self.assertEqual([r['hart'] for r in rows],[0,1,2]);self.assertEqual(sum(r['checks'] for r in rows),15)
    def test_incomplete_peer_rejected(self):
        words=self.rdtime();words[-1]=0
        with self.assertRaises(ValueError):rtl.decode_signature(self.raw(words),'rdtime')
    def test_wrong_tval_rejected(self):
        words=self.rdtime();words[9]=0
        with self.assertRaises(ValueError):rtl.decode_signature(self.raw(words),'rdtime')
    def test_failing_mailbox_rejected(self):
        words=self.rdtime();words[3]=1
        with self.assertRaises(ValueError):rtl.decode_signature(self.raw(words),'rdtime')
if __name__=='__main__':unittest.main()
