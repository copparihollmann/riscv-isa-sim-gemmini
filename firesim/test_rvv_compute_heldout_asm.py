"""Admission and protected-label guards; no hardware contact or timing labels."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_rvv_compute_heldout_asm import admit, merge, WATCHDOG, PHASE_TIMEOUT
from rvv_compute_heldout_asm_review import validator, scalar_wire_proof, flatten
from analyze_rvv_compute_heldout_asm import training_rows
from batch_runner import digest, parse_regions

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/rvv-compute-heldout-asm-v1'


class ProtectedAdmission(unittest.TestCase):
    def setUp(self):
        self.corpus = json.loads((BUILD / 'corpus.json').read_text())
        self.ready = digest(BUILD / 'ready.json')

    def copied(self, target):
        for name in ['ready.json'] + list(json.loads((BUILD / 'ready.json').read_text())['artifact_sha256']):
            (target / name).write_bytes((BUILD / name).read_bytes())

    def test_actual_admission(self):
        self.assertEqual(len(admit(BUILD, self.ready)[2]), 1320)

    def test_wrong_ready(self):
        with self.assertRaises(ValueError):
            admit(BUILD, '0' * 64)

    def test_corrupt_ELF(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            self.copied(build)
            raw = bytearray((build / 'guest.elf').read_bytes())
            raw[-1] ^= 1
            (build / 'guest.elf').write_bytes(raw)
            with self.assertRaises(ValueError):
                admit(build, digest(build / 'ready.json'))

    def test_boolean_region_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            self.copied(build)
            ready = json.loads((build / 'ready.json').read_text())
            ready['required_regions'] = True
            (build / 'ready.json').write_text(json.dumps(ready))
            with self.assertRaises(ValueError):
                admit(build, digest(build / 'ready.json'))

    def test_all_cases_protected_new_repetitions(self):
        cases = self.corpus['cases']
        self.assertTrue(all(row['internal_split'] == 'reserved_holdout'
                            and row['validation_role'] == 'protected_validation_only' for row in cases))
        self.assertEqual({row['n'] for row in cases if row['kind'] != 'rowmove'}, {32, 128})
        self.assertEqual({row['n'] for row in cases if row['kind'] == 'rowmove'}, {2, 8, 32, 128})
        self.assertEqual({row['hart'] for row in cases}, {0, 1})
        parent = json.loads((ROOT / 'build/rvv-compute-asm-v5/corpus.json').read_text())['cases']
        self.assertFalse(set(row['case_id'] for row in cases) & set(row['case_id'] for row in parent))
        self.assertEqual([row['source_case_id'] for row in cases], [row['case_id'] for row in parent])

    def test_old_repeat_count_rejected(self):
        corpus = copy.deepcopy(self.corpus)
        corpus['cases'][0]['n'] = 16
        with self.assertRaises(ValueError):
            validator().validate_corpus(corpus)

    def test_TRAIN_case_rejected(self):
        corpus = copy.deepcopy(self.corpus)
        corpus['cases'][0]['internal_split'] = 'train'
        with self.assertRaises(ValueError):
            validator().validate_corpus(corpus)

    def test_corpus_fitting_role_rejected(self):
        corpus = copy.deepcopy(self.corpus)
        corpus['fitting_only'] = True
        with self.assertRaises(ValueError):
            validator().validate_corpus(corpus)

    def test_changed_numerical_golden_rejected(self):
        corpus = copy.deepcopy(self.corpus)
        corpus['cases'][0]['expected_checksum'] ^= 1
        with self.assertRaises(ValueError):
            validator().validate_corpus(corpus)

    def test_hart2_case_rejected(self):
        corpus = copy.deepcopy(self.corpus)
        corpus['cases'][0]['hart'] = 2
        with self.assertRaises(ValueError):
            validator().validate_corpus(corpus)

    def test_ordinary_runner_JSON(self):
        text = (ROOT / 'build/rvv-compute-heldout-asm-functional-seed0-v1/stdout').read_text()
        rows = parse_regions(text, flatten(self.corpus), json.loads((BUILD / 'ready.json').read_text())['ELF_sha256'],
                             '0' * 64, require_regions=True, require_goldens=True)
        self.assertEqual(len(rows), 1320)
        self.assertTrue(all(row['hart'] in (0, 1) for row in rows))

    def test_scalar_wire_and_all_four_row_bodies(self):
        proof = scalar_wire_proof((BUILD / 'guest.elf').read_bytes(), self.corpus)
        self.assertEqual(proof['emit_vector_instructions'], 0)
        self.assertEqual(len(proof['bodies']), 17)
        for count in (2, 8, 32, 128):
            self.assertEqual(proof['bodies']['asm_row' + str(count)]['static_target_instructions'], count)
        self.assertEqual(proof['compiled_counter_phase_proof']['wrapper_scalar_data_loads_in_ROI'], 0)

    def test_TRAIN_export_forbidden(self):
        with self.assertRaisesRegex(ValueError, 'Protected validation-only'):
            training_rows(self.corpus['cases'])

    def test_sources_absolute_and_collisions_rejected(self):
        target = {str(BUILD / 'guest.elf'): 'a' * 64}
        with self.assertRaises(ValueError):
            merge(target, {str(BUILD / 'guest.elf'): 'b' * 64})
        target = {}
        merge(target, {'benchmarks/rvv_compute_heldout_asm_v1/guest.c': 'a' * 64})
        self.assertTrue(all(Path(name).is_absolute() for name in target))

    def test_requested_bounds(self):
        self.assertEqual((WATCHDOG, PHASE_TIMEOUT), (180, 360))


if __name__ == '__main__':
    unittest.main()
