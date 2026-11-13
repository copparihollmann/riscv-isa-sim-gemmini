import copy
from pathlib import Path
import tempfile
import unittest

from benchmarks.scalar_rtl.validate_components import compare, decode_signature, MASK


class ScalarComponentValidationTests(unittest.TestCase):
    def signature(self, root, n=0):
        words = [0x495249535343414c, 1, 0, 1, 1, 1, 0, 0]
        for hart in range(3):
            for kind in range(2):
                words += [100, 108, 500, 500 + n + int(hart == 2), n + (1 if kind == 0 else 36), n, 0, 0]
        path = Path(root) / 'signature'
        self.write(path, words)
        return path, words

    def write(self, path, words):
        path.write_text(''.join(f'{w:016x}\n' for w in words))

    def test_empty_body_valid_with_zero_shuttle_retired(self):
        with tempfile.TemporaryDirectory() as root:
            path, _ = self.signature(root)
            rows = decode_signature(path, 0)
            self.assertEqual([r['instret_delta'] for r in rows], [0, 0, 0, 0, 1, 1])

    def test_counter_rollover_is_unsigned(self):
        with tempfile.TemporaryDirectory() as root:
            path, words = self.signature(root, 7)
            words[8:12] = [MASK - 2, 5, MASK - 3, 3]
            self.write(path, words)
            row = decode_signature(path, 7)[0]
            self.assertEqual((row['cycles'], row['instret_delta']), (8, 7))

    def test_missing_hart_bad_checksum_and_wrong_policy_reject(self):
        with tempfile.TemporaryDirectory() as root:
            path, original = self.signature(root, 7)
            for index in (4, 12, 13, 14, 11, 43):
                with self.subTest(word=index):
                    words = list(original)
                    words[index] += 1
                    self.write(path, words)
                    with self.assertRaises(ValueError):
                        decode_signature(path, 7)

    def test_signature_framing_and_impossible_delta_reject(self):
        with tempfile.TemporaryDirectory() as root:
            path, words = self.signature(root)
            for text in (path.read_text() + '0000000000000000\n', path.read_text()[:-18], path.read_text().upper()):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    decode_signature(path, 0)
            words[9] = words[8]
            self.write(path, words)
            with self.assertRaises(ValueError):
                decode_signature(path, 0)

    def test_comparison_retains_signed_error_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as root:
            path, _ = self.signature(root, 8)
            refs = decode_signature(path, 8)
            predicted = copy.deepcopy(refs)
            predicted[0]['cycles'] = 9
            predicted[1]['cycles'] = 7
            errors = compare(refs, predicted)
            self.assertEqual([r['signed_error_percent'] for r in errors[:2]], [12.5, -12.5])
            self.assertFalse(errors[0]['within_2_percent'])
            predicted[1] = predicted[0]
            with self.assertRaises(ValueError):
                compare(refs, predicted)

    def test_functional_failure_cannot_be_scored_as_timing(self):
        with tempfile.TemporaryDirectory() as root:
            path, _ = self.signature(root, 32)
            refs = decode_signature(path, 32)
            predicted = copy.deepcopy(refs)
            predicted[4]['checksum'] ^= 1
            with self.assertRaises(ValueError):
                compare(refs, predicted)


if __name__ == '__main__':
    unittest.main()
