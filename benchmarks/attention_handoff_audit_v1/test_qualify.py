import unittest
from qualify import handoffs


class Handoffs(unittest.TestCase):
    GOOD = ('ATTN_HANDOFF v1 0 4 0 0 1 0 8192 8192 0 0 0 0\n'
            'ATTN_HANDOFF v1 1 1 0 0 1 32 8192 8192 1 1 2 2\n'
            'ATTN_HANDOFF_DONE v1 2 0\nDONE\n')

    def test_valid_and_only_metadata_removed(self):
        rows, remaining = handoffs(self.GOOD, 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(remaining, 'DONE\n')

    def test_drop_duplicate_overflow_and_wrong_hart_rejected(self):
        for broken in (self.GOOD.replace('ATTN_HANDOFF v1 0', 'REMOVED v1 0'),
                       self.GOOD + self.GOOD.splitlines()[1] + '\n',
                       self.GOOD.replace('DONE v1 2 0', 'DONE v1 2 1'),
                       self.GOOD.replace('1 1 0 0 1 32', '1 1 2 0 1 32')):
            with self.assertRaises(ValueError):
                handoffs(broken, 2)

    def test_missing_registration_or_counter_regression_rejected(self):
        for broken in (self.GOOD.replace('0 4 0 0 1 0', '0 1 0 0 0 1'),
                       self.GOOD.replace('8192 8192 1 1 2 2', '8192 8192 2 1 1 2'),
                       self.GOOD.replace('1 1 0 0 1 32', '1 1 0 0 0 32')):
            with self.assertRaises(ValueError):
                handoffs(broken, 2)


if __name__ == '__main__':
    unittest.main()
