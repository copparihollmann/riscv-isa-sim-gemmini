"""Admission controls using existing functional output, never FPGA timing labels."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'timing'))
from compare_rvv_compute_heldout_asm_v1 import compare


class ProtectedPredictionAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / 'build/rvv-compute-heldout-asm-v1/corpus.json').read_text())['cases']
        text = (ROOT / 'build/rvv-compute-heldout-asm-functional-seed0-v1/stdout').read_text()
        cls.rows = [json.loads(line.split(' ', 1)[1]) for line in text.splitlines()
                    if line.startswith('IRIS_REGION ')]

    def test_complete_functional_fixture_is_admitted(self):
        result = compare(self.cases, self.rows, self.rows)
        self.assertEqual(len(result), 1320)
        self.assertTrue(all(row['total']['signed_error_percent'] == 0 for row in result))

    def test_missing_repetition(self):
        with self.assertRaises(ValueError):
            compare(self.cases, self.rows, self.rows[:-1])

    def test_reordered_repetitions(self):
        rows = copy.deepcopy(self.rows)
        rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaises(ValueError):
            compare(self.cases, self.rows, rows)

    def test_changed_actual_fields(self):
        changes = dict(hart=2, trial_id=True, checked_words=True, checksum=0,
                       mismatch_or=1, kind=99, sew=True, vl=0, operations=1,
                       end_cycle=0, issue_cycle=True, instret_delta=0)
        for key, value in changes.items():
            with self.subTest(key=key):
                rows = copy.deepcopy(self.rows)
                rows[0][key] = value
                with self.assertRaises(ValueError):
                    compare(self.cases, self.rows, rows)

    def test_training_row_refused(self):
        cases = copy.deepcopy(self.cases)
        cases[0]['internal_split'] = 'train'
        with self.assertRaises(ValueError):
            compare(cases, self.rows, self.rows)

    def test_zero_duration_is_explicit(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['end_cycle'] = rows[0]['issue_cycle']
        result = compare(self.cases, rows, self.rows)
        self.assertIsNone(result[0]['drain']['signed_error_percent'])
        self.assertEqual(result[0]['drain']['zero_duration_mismatch'],
                         self.rows[0]['end_cycle'] != self.rows[0]['issue_cycle'])


if __name__ == '__main__':
    unittest.main()
