"""Adversarial unit/semantic controls for the new read-only capacity overlay."""
import copy
import unittest

from iris_model.conditional_capacity_overlay import (
    byte_coordinates, capacity, clock_edges, conditional_fraction, delta,
    render_svg, work_completion,
)


def record(hart=0, family='vme.int8'):
    return dict(hart=hart, family=family, value=256,
                units='cell_MACs/accepted_array_edge',
                kind='conditional_source_capacity_upper_bound',
                arithmetic_ops_per_mac=2, conditions=['ready operands and accepted edge'])


def event(**kw):
    result = dict(id=1, hart=0, pc=4096, name='empirical.async.vme.int8',
                  resource='vme0', macs=1024, start=11, end=15, completed=True)
    result.update(kw)
    return result


class CapacityControls(unittest.TestCase):
    def test_half_open_clock_edges(self):
        self.assertEqual(clock_edges(10, 20, 1), 10)
        self.assertEqual(clock_edges(1, 10, 3), 3)
        self.assertEqual(clock_edges(1, 10, 3, 1), 3)
        self.assertEqual(clock_edges(0, 1, 3, 1), 0)
        self.assertEqual(clock_edges(0, 1, 3), 1)

    def test_clock_invalid_types_windows(self):
        for args in [(True, 5, 1), (1, 1, 1), (2, 1, 1), (0, 2, 0), (0, 2, 2, 2), (-1, 2, 1)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                clock_edges(*args)

    def test_alternate_formats_do_not_add_peaks(self):
        records = [record(), record(family='vme.fp8'), record(hart=1)]
        self.assertEqual(capacity(records, 0, 'vme.int8')['value'], 256)
        self.assertEqual(capacity(records, 0, 'vme.fp8')['value'], 256)

    def test_duplicate_capacity_refused(self):
        with self.assertRaises(ValueError):
            capacity([record(), record()], 0, 'vme.int8')

    def test_wrong_unit_refused(self):
        r = record(); r['units'] = 'FLOPs/second'
        with self.assertRaises(ValueError):
            capacity([r], 0, 'vme.int8')

    def test_hart2_has_no_opu(self):
        self.assertIsNone(capacity([record()], 2, 'vme.int8'))
        self.assertIsNone(conditional_fraction(0, 50, None, True)['fraction'])
        self.assertTrue(conditional_fraction(1, 50, None, True)['inconsistency'])
        with self.assertRaises(ValueError):
            capacity([record(hart=2)], 2, 'vme.int8')

    def test_fraction_above_one_not_clamped(self):
        result = conditional_fraction(1024, 2, 256, True)
        self.assertEqual(result['fraction'], 2)
        self.assertTrue(result['inconsistency'])

    def test_unknown_or_empty_window_has_no_fraction(self):
        self.assertIsNone(conditional_fraction(1024, 0, 256, True)['fraction'])
        self.assertIsNone(conditional_fraction(1024, 8, 256, False)['fraction'])
        with self.assertRaises(ValueError):
            conditional_fraction(1024, 8, 256, 1)

    def test_only_completed_inside_work_is_credited(self):
        result = work_completion([event(), event(id=2, hart=1)], 0, 10, 20)
        self.assertEqual(result['completed_logical_MACs'], 1024)
        self.assertTrue(result['model_completion_window_qualified'])

    def test_boundary_tie_is_unqualified(self):
        for kw in ({'end': 20}, {'start': 9}, {'completed': False}):
            result = work_completion([event(**kw)], 0, 10, 20)
            self.assertEqual(result['completed_logical_MACs'], 0)
            self.assertFalse(result['model_completion_window_qualified'])

    def test_canceled_and_squashed_get_no_logical_credit(self):
        events = [event(id=1, completed=False, issued=False, cancelled=True, start=12, end=12),
                  event(id=2, squashed=True), event(id=3, completed=False, cancelled=True, issued=True)]
        result = work_completion(events, 0, 10, 20)
        self.assertEqual(result['completed_logical_MACs'], 0)
        self.assertEqual(len(result['excluded_canceled_or_squashed_operations']), 3)
        self.assertFalse(result['physical_MAC_completion_verified'])

    def test_lifecycle_and_payload_malformed_refused(self):
        for kw in ({'completed': 1}, {'issued': 1}, {'cancelled': 1}, {'squashed': 1},
                   {'macs': True}, {'macs': -1}, {'end': 10},
                   {'cancelled': True}, {'issued': False}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                work_completion([event(**kw)], 0, 10, 20)

    def test_counter_deltas_not_wrapped_or_boolean(self):
        self.assertEqual(delta({'x': {'bytes': 4}}, {'x': {'bytes': 8}}), {'x': {'bytes': 4}})
        for after in ({'x': {'bytes': 3}}, {'x': {'bytes': True}}, {}):
            with self.assertRaises(ValueError):
                delta({'x': {'bytes': 4}}, after)

    def test_requested_byte_scopes_are_separate(self):
        features = {'memory.vector.store': {'bytes': 128}, 'memory.DRAM.load': {'bytes': 80},
                    'vme.row_move': {'bytes': 128}}
        memory = {'DRAM': {'bytes': 240}, 'ICACHE.DRAM': {'bytes': 500}}
        result = byte_coordinates(features, memory, 4096)
        self.assertEqual(result['retired_instruction_requested_data_bytes'], 208)
        self.assertEqual(result['accepted_timing_intent_requested_data_bytes'], 240)
        self.assertAlmostEqual(result['architectural_MACs_per_requested_data_byte'], 4096/208)
        self.assertEqual(result['retired_VRF_row_move_bytes_excluded_from_data_denominator'], 128)
        self.assertIsNone(result['physical_DRAM_bytes'])
        self.assertIsNone(result['physical_arithmetic_intensity'])

    def test_zero_bytes_do_not_produce_infinite_intensity(self):
        self.assertIsNone(byte_coordinates({}, {}, 4096)['architectural_MACs_per_requested_data_byte'])
        with self.assertRaises(ValueError):
            byte_coordinates({'memory.x': {'bytes': True}}, {}, 1)

    def test_svg_preserves_above_one_fraction(self):
        region = dict(region='profile.source.VME.uint8::kernel', hart=0,
                      conditional_source_peak_fraction={'fraction': 1.5},
                      byte_coordinates={'architectural_MACs_per_requested_data_byte': 8})
        rendered = render_svg([region])
        self.assertIn('150.0000%', rendered)
        self.assertIn('Physical DRAM/L2 traffic', rendered)


if __name__ == '__main__':
    unittest.main()
