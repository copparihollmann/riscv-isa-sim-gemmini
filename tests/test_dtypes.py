import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from iris_model.capabilities import load_verified, query

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dtype_audit', ROOT / 'hardware/dtypes.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DtypeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / 'hardware/dtypes.json'
        cls.data = load_verified(cls.path)

    def test_complete_frozen_source_audit_validates(self):
        result = audit.verify(self.data, ROOT / 'hardware')
        self.assertGreaterEqual(result['source_count'], 31)
        self.assertEqual({row['hart'] for row in self.data['capabilities']}, {0, 1, 2})
        self.assertFalse(result['bitstream_match_verified'])
        self.assertFalse(result['model_support_certified'])

    def test_main_hardware_manifest_identity_is_bound(self):
        self.assertEqual(self.data['hardware_manifest_sha256'],
                         hashlib.sha256((ROOT / 'hardware/manifest.json').read_bytes()).hexdigest())

    def test_compute_fp8_vme_is_present_and_dma_vme_absent(self):
        for hart in (0, 1, 2):
            for dtype in ('ofp8_e4m3', 'ofp8_e5m2'):
                result = query(self.data, hart, 'vme', dtype, 'mac', 'input')
                self.assertEqual(result['configured_match_exists'], hart < 2)
                if hart < 2:
                    row = next(row for row in result['matches'] if row['status'] == 'configured')
                    self.assertEqual(row['accumulator_type'], 'f32')
                    self.assertEqual(row['output_types'], ['f32'])
                    self.assertEqual({tuple(pair) for pair in row['input_type_pairs']},
                                     {(a, b) for a in ('ofp8_e4m3', 'ofp8_e5m2') for b in ('ofp8_e4m3', 'ofp8_e5m2')})

    def test_dma_has_vector_arithmetic_but_no_matrix_unit(self):
        for dtype in ('f16', 'f32', 'f64'):
            self.assertTrue(query(self.data, 2, 'vector', dtype, 'fma', 'input')['configured_match_exists'])
        for dtype in ('i8', 'u8', 'i16', 'u16', 'i32', 'u32', 'i64', 'u64'):
            self.assertTrue(query(self.data, 2, 'vector', dtype, 'mul', 'input')['configured_match_exists'])
        self.assertFalse(query(self.data, 2, 'vme')['configured_match_exists'])

    def test_scalar_bf16_advertisement_is_not_certified_arithmetic(self):
        for hart in (0, 1, 2):
            bf16 = query(self.data, hart, 'scalar', 'bf16', 'convert', 'input')
            self.assertFalse(bf16['configured_match_exists'])
            if hart < 2:
                self.assertEqual({row['status'] for row in bf16['matches']}, {'not_configured'})
            self.assertTrue(query(self.data, hart, 'scalar', 'f32', 'convert', 'input')['configured_match_exists'])

    def test_elaborated_opu_has_fp8_but_no_column_readout(self):
        source = self.data['sources']['fir-opu-ports']
        excerpt = (ROOT / 'hardware' / source['snapshot']).read_text()
        self.assertIn('flip fp8', excerpt)
        self.assertNotIn('out_col', excerpt)
        for hart in (0, 1, 2):
            self.assertFalse(query(self.data, hart, 'vme', 'f32', 'tile_column_read', 'input')['configured_match_exists'])
            self.assertEqual(query(self.data, hart, 'vme', 'f32', 'tile_column_write', 'input')['configured_match_exists'], hart < 2)

    def test_minifloat_fma_does_not_imply_minifloat_division(self):
        for hart in (0, 1):
            for dtype in ('bf16', 'ofp8_e4m3', 'ofp8_e5m2'):
                self.assertTrue(query(self.data, hart, 'vector', dtype, 'fma', 'input')['configured_match_exists'])
                self.assertFalse(query(self.data, hart, 'vector', dtype, 'div', 'input')['configured_match_exists'])


if __name__ == '__main__':
    unittest.main()
