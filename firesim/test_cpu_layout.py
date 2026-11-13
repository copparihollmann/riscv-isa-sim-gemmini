#!/usr/bin/env python3
"""Local admission/analysis controls; no FPGA access or manufactured measurements."""
import copy
import json
from pathlib import Path
import unittest

from analyze_cpu_layout import repeat_statistics
from prepare_cpu_layout import ROOT, TARGET_BOUND_REASON, admit, check_cases, check_rows

BUILD = ROOT/'build/cpu-layout-v2'
READY_SHA = 'cb4d01e9c029b0cc7bf63502cfcf03111134b2bb749436074192f78fe80916ba'


class CpuLayoutTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((BUILD/'cases.json').read_text())
        cls.proof = json.loads((BUILD/'binary-proof.json').read_text())
        cls.lines = (BUILD/'seed0/stdout').read_text().splitlines()

    def test_real_frozen_packet_and_both_seeded_executions(self):
        ready, cases, elf, identities = admit(BUILD, READY_SHA)
        self.assertEqual(len(cases), 771)
        self.assertEqual(sum(len(c['active_harts']) for c in cases), 2313)
        self.assertEqual(ready['elf_sha256'], '917e170577cc82ace8d0779ae2d49e12f3873e995844485b4f278811dfc5257d')
        self.assertIn(str(elf), identities)

    def test_changed_ready_packet_refused(self):
        with self.assertRaisesRegex(ValueError, 'frozen explicitly'):
            admit(BUILD, '0'*64)

    def test_superseded_real_v1_packet_refused(self):
        from batch_runner import digest
        old = ROOT/'build/cpu-layout-v1'
        with self.assertRaises(ValueError):
            admit(old, digest(old/'ready.json'))

    def test_case_id_golden_and_active_harts_are_independently_guarded(self):
        for key, value in [('expected_checksums_by_hart', [0, 0, 0]), ('active_harts', [0, 1]),
                           ('id', 'cpu.layout.v1.compact.off0.n16.repeat0'), ('loop_offset', 2)]:
            with self.subTest(field=key):
                bad = copy.deepcopy(self.document); bad['cases'][0][key] = value
                with self.assertRaises(ValueError):
                    check_cases(bad)

    def test_real_console_identity_numeric_pc_and_counter_corruptions(self):
        for field in ('case_id', 'checksum', 'counter_end', 'loop_pc', 'begin_pc', 'end_pc', 'instret_delta'):
            with self.subTest(field=field):
                lines = list(self.lines)
                index = next(i for i, line in enumerate(lines) if line.startswith('IRIS_REGION '))
                row = json.loads(lines[index].split(' ', 1)[1])
                row[field] = 'wrong-id' if field == 'case_id' else row[field]+1
                lines[index] = 'IRIS_REGION '+json.dumps(row)
                with self.assertRaises(ValueError):
                    check_rows(lines, self.proof)

    def test_missing_or_duplicate_records_and_missing_completion_refused(self):
        index = next(i for i, line in enumerate(self.lines) if line.startswith('IRIS_REGION '))
        for lines in (self.lines[:index]+self.lines[index+1:], self.lines+[self.lines[index]],
                      [s for s in self.lines if not s.startswith('IRIS_BATCH_DONE ')]):
            with self.subTest(lines=len(lines)):
                with self.assertRaises(ValueError):
                    check_rows(lines, self.proof)

    def test_actual_repetition_statistics_preserve_zero_noop_samples(self):
        rows = check_rows(self.lines, self.proof)
        stats = repeat_statistics(rows)
        self.assertEqual(len(stats), 771)
        self.assertEqual(len([r for r in stats if r['mode'] == 'noop']), 3)
        for row in stats:
            self.assertEqual([s['repeat'] for s in row['samples']], [0, 1, 2])
            if row['cycle_mean'] == 0:
                self.assertIsNone(row['cycle_coefficient_of_variation'])

    def test_loader_bound_rationale_preserves_startup_and_atoi_hazards(self):
        self.assertIn('5,000,000,000', TARGET_BOUND_REASON)
        self.assertIn('1,900,000,000', TARGET_BOUND_REASON)
        self.assertIn('32-bit atoi', TARGET_BOUND_REASON)


if __name__ == '__main__':
    unittest.main()
