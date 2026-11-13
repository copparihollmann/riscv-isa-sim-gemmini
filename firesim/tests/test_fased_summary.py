"""Reject fabricated counter timing, malformed samples and unsafe wrap inference."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from summarize_fased import parse


class RawCounterTests(unittest.TestCase):
    names = ['totalReads', 'totalReadBeats', 'totalWrites', 'totalWriteBeats',
             'readOutstandingHistogram_0', 'writeOutstandingHistogram_0', 'brespError', 'rrespError']

    def csv(self, rows, header=None):
        return (','.join(header or self.names) + ',\n' + '\n'.join(','.join(map(str,r)) + ',' for r in rows) + '\n').encode()

    def test_idle_tail_has_raw_stability_but_no_invented_bandwidth_or_latency(self):
        raw = self.csv([[1,8,2,16,10,10,0,0], [1,8,2,16,20,20,0,0], [1,8,2,16,30,30,0,0]])
        result = parse(raw, self.names)
        self.assertTrue(result['tail_transaction_registers_all_observed_constant'])
        self.assertEqual(result['tail_modular_counter_deltas']['readOutstandingHistogram_0'], [10,10])
        for key in ['sample_target_timestamps','elapsed_target_cycles','bandwidth_bytes_per_cycle','per_hart_attribution','latency_distribution']:
            self.assertIsNone(result[key])
        self.assertFalse(result['occupancy_bin_thresholds_verified'])
        self.assertTrue(result['raw_status_zero_is_not_a_complete_bus_error_proof'])

    def test_counter_decrease_is_recorded_without_assuming_wrap_or_reset(self):
        raw = self.csv([[2**32-2,8,2,16,10,10,0,0], [1,8,2,16,20,20,0,0]])
        result = parse(raw,self.names)
        self.assertEqual(result['raw_decrease_sample_indices']['totalReads'],[1])
        self.assertEqual(result['tail_modular_counter_deltas']['totalReads'],[3])
        self.assertNotIn('unwrapped_total',result)

    def test_one_snapshot_does_not_establish_stability(self):
        result = parse(self.csv([[1,8,2,16,10,10,0,0]]), self.names)
        self.assertFalse(result['tail_transaction_registers_all_observed_constant'])

    def test_truncated_negative_float_nonascii_and_overflow_samples_refuse(self):
        for cell in ['-1','1.5','nan',' 1','4294967296','\ufffd']:
            with self.subTest(cell=cell),self.assertRaises((ValueError,UnicodeError)):
                parse(self.csv([[cell,8,2,16,10,10,0,0]]),self.names)
        with self.assertRaises(ValueError):parse(self.csv([[1,8,2]]),self.names)

    def test_duplicate_missing_or_uninstantiated_counter_names_refuse(self):
        for names in [self.names[:-1], self.names+['readLatency'], self.names[:-1]+['brespError']]:
            with self.subTest(names=names),self.assertRaises(ValueError):
                parse(self.csv([[0]*len(names)], names),self.names)

    def test_empty_or_header_only_is_explicitly_unavailable(self):
        self.assertEqual(parse(b'',self.names)['status'],'empty')
        self.assertEqual(parse(self.csv([]),self.names)['status'],'no_samples')


if __name__ == '__main__': unittest.main()
