"""Synthetic arithmetic controls; these fixtures are never admitted hardware runs."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_compiler_transforms import collect, summarize


def fixture():
    cases, rows, metrics = [], [], []
    cursor = 0
    for index, tile in enumerate((0, 32, 128, 512)):
        name = 'synthetic_' + str(tile)
        cases.append(dict(name=name, tile_m=tile, m=4096, n=64, k=144,
                          kind='conv_im2col_i8', measured=2, expected_checksum=123,
                          input_sha256={'A': 'same-test-input', 'B': 'same-test-weights'},
                          batch=1, ci=16, co=64, h=64, w=64, kh=3, kw=3, stride=1,
                          pads=[1, 1, 1, 1], oh=64, ow=64, layout='NCHW', weight_layout='OIHW', warmup=0))
        for route, ticks in [('RVV', 1000-index*100), ('VME', 500-index*50)]:
            for rep in range(2):
                count = ticks+rep*2
                rows.append(dict(case_index=index, variant=route+'_I8_clean', warmup=False,
                                 repetition=rep, hart=0, start_cycle=cursor, end_cycle=cursor+count,
                                 start_instret=0, end_instret=17, instret_delta=17,
                                 checksum=123, expected_checksum=123, **{'pass': True}))
                cursor += count+1
            metrics.append(dict(case=name, variant=route+'_I8_clean', cycles_median=ticks+1))
            metrics.append(dict(case=name, variant=route+'_I8_profile', cycles_median=ticks+11,
                                caller_phase_ticks_median=[100, 200, 0, 0, 0]))
            for rep in range(2):
                rows.append(dict(case_index=index, variant=route+'_I8_profile', warmup=False,
                                 repetition=rep, start_cycle=0, end_cycle=ticks+10+rep*2,
                                 caller_phase_ticks=[100, 200, 0, 0, 0]))
    return dict(cases=cases), dict(rows=rows, metrics=metrics, counter_semantics='target_mcycle_uncalibrated', **{'pass': True})


class TransformComparisonTests(unittest.TestCase):
    def test_total_caller_and_actual_workspace_not_profile_primitive_select_winner(self):
        plan, profile = fixture()
        result = summarize(plan, profile)
        self.assertEqual([r['A_panel_capacity_bytes'] for r in result['candidates']], [589824, 4608, 18432, 73728])
        self.assertEqual(result['observed_lowest_median'], dict(cycles=351, tile_rows=512, route='VME'))
        for record in result['candidates']:
            self.assertIsNone(record['routes']['VME']['clean_preparation_phase_cycles'])
        self.assertIsNone(result['physical_busy'])
        self.assertAlmostEqual(result['candidates'][-1]['routes']['VME']['full_unfold_baseline_over_candidate_total_ratio'], 501/351)

    def test_native_or_model_counter_counts_cannot_be_hardware_admitted(self):
        for basis in ('instruction_count_not_modeled_cycles', 'uncalibrated_modeled_cycles'):
            plan, profile = fixture()
            profile['counter_semantics'] = basis
            with self.assertRaisesRegex(ValueError, 'native/model'):
                summarize(plan, profile)

    def test_changed_operands_incomplete_repeats_and_forged_summary_refused(self):
        for mode in ('input', 'repetition', 'summary', 'checksum'):
            plan, profile = fixture()
            if mode == 'input':
                plan['cases'][1]['input_sha256'] = {'A': 'changed'}
            elif mode == 'repetition':
                profile['rows'].pop()
            elif mode == 'summary':
                profile['metrics'][0]['cycles_median'] = 7
            else:
                profile['rows'][0]['checksum'] = 99
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                summarize(plan, profile)

    def test_existing_output_is_never_changed_on_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'existing'
            output.mkdir()
            (output/'receipt').write_bytes(b'keep these exact bytes')
            with self.assertRaisesRegex(ValueError, 'Fresh output'):
                collect(Path(folder)/'unused', output, 0)
            self.assertEqual(list(output.iterdir()), [output/'receipt'])
            self.assertEqual((output/'receipt').read_bytes(), b'keep these exact bytes')

    def test_owned_missing_input_failure_is_terminal_and_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'fresh'
            with self.assertRaises(FileNotFoundError):
                collect(Path(folder)/'missing-queue', output, 0)
            self.assertEqual(json.loads((output/'status.json').read_text())['status'], 'failed_or_refused')
            self.assertFalse(json.loads((output/'collector-failure.json').read_text())['hardware_contacted'])


if __name__ == '__main__':
    unittest.main()
