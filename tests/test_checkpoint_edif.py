"""Offline checkpoint text decoding admits only bounded, exact chunk streams."""
import contextlib
import ctypes
import ctypes.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from hardware.checkpoint_edif import LexicalBalance,extract


@unittest.skipUnless(ctypes.util.find_library('zstd'),'installed libzstd required')
class CheckpointEdifTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.lib=ctypes.CDLL(ctypes.util.find_library('zstd'))
        self.lib.ZSTD_compressBound.argtypes=[ctypes.c_size_t];self.lib.ZSTD_compressBound.restype=ctypes.c_size_t
        self.lib.ZSTD_compress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
        self.lib.ZSTD_compress.restype=ctypes.c_size_t

    def chunk(self,plain,declared=None):
        source=ctypes.create_string_buffer(plain);target=ctypes.create_string_buffer(self.lib.ZSTD_compressBound(len(plain)))
        length=self.lib.ZSTD_compress(target,len(target),source,len(plain),1)
        amount=len(plain)if declared is None else declared
        return b'XlxV37EB'+('%8x%8x'%(amount,length)).encode()+target.raw[:length]

    def archive(self,payload):
        path=self.root/'source.dcp'
        with zipfile.ZipFile(path,'w')as z:z.writestr('overall_fpga_top.edf',payload)
        return path,hashlib.sha256(path.read_bytes()).hexdigest()

    def run_extract(self,payload,maximum=8192):
        path,sha=self.archive(payload);out=self.root/'decoded'
        with contextlib.redirect_stdout(io.StringIO()):code=extract(path,sha,'overall_fpga_top.edf',out,maximum)
        return code,json.loads((out/'report.json').read_text()),out

    def test_independent_zstd_frames_and_strings_across_chunk_boundary(self):
        first=b'(edif demo (comment "literal (';second=b') remains text") (cell leaf))\n'
        code,report,out=self.run_extract(self.chunk(first)+self.chunk(second))
        self.assertEqual(code,0);self.assertEqual(report['chunks'],2)
        self.assertEqual((out/'netlist.edf').read_bytes(),first+second)
        self.assertFalse(report['INIT_values_certified']);self.assertFalse(report['hardware_contacted'])

    def test_declared_size_mismatch_rejects(self):
        code,report,_=self.run_extract(self.chunk(b'(edif x)',declared=7))
        self.assertEqual(code,1);self.assertIn('exceeded',report['error'])

    def test_unsupported_wrapper_rejects_without_guessing_legacy_codec(self):
        payload=self.chunk(b'(edif x)');payload=b'XlxV18EB'+payload[8:]
        code,report,_=self.run_extract(payload)
        self.assertEqual(code,1);self.assertIn('Unsupported',report['error'])

    def test_truncated_compressed_chunk_and_unbalanced_text_reject(self):
        for number,payload in enumerate((self.chunk(b'(edif x)')[:-1],self.chunk(b'(edif x'))):
            path=self.root/str(number);path.mkdir();source,sha=self.archive(payload)
            with contextlib.redirect_stdout(io.StringIO()):code=extract(source,sha,'overall_fpga_top.edf',path/'out')
            self.assertEqual(code,1)

    def test_output_bound_and_wrong_input_digest_refuse(self):
        code,report,_=self.run_extract(self.chunk(b'(edif x)'),maximum=7)
        self.assertEqual(code,1);self.assertIn('bound',report['error'])
        source=self.root/'source.dcp'
        with self.assertRaisesRegex(ValueError,'digest'):extract(source,'0'*64,'overall_fpga_top.edf',self.root/'bad')
        self.assertFalse((self.root/'bad').exists())

    def test_lexical_scan_does_not_accept_trailing_open_string_or_negative_depth(self):
        for data in(b'(edif x))',b'(edif "x)',b'(edif x)\x00'):
            with self.subTest(data=data),self.assertRaises(ValueError):
                scan=LexicalBalance();scan.accept(data);scan.finish()


if __name__=='__main__':unittest.main()
