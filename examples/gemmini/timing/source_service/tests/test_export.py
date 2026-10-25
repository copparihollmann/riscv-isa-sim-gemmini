"""Closed experimental bundle, untouched original provider, explicit source selection."""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from merlin_timing import provider_bundle as B
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('source_service_export', ROOT/'export_source_service.py')
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)

class SourceServiceExportTest(unittest.TestCase):
    def test_closed_source_identity(self):
        original = {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()
                    for n in ('provider.hpp','staged.hpp','bridge.cpp','stock_u250.json','export_config.py')}
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as folder:
            p = Path(folder)/'bundle'
            receipt = E.export(p)
            self.assertEqual(receipt,B.verify_bundle(p))
            self.assertEqual({x['path'] for x in receipt['members']},set(E.SOURCES)|{'build_provider.py'})
            for n in E.SOURCES:
                self.assertEqual((p/n).read_bytes(),(ROOT/'source_service'/n).read_bytes())
            with self.assertRaises(ValueError): E.export(p)
            (p/'provider.hpp').write_bytes(b'changed')
            with self.assertRaises(ValueError): B.verify_bundle(p)
        self.assertEqual(original,{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest()for n in original})
if __name__=='__main__':unittest.main()
