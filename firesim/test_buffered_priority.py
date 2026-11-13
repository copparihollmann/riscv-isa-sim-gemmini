#!/usr/bin/env python3
"""Actual buffered-input admission controls; no FPGA access or fabricated timing."""
import copy
import json
from pathlib import Path
import unittest

from analyze_buffered_priority import repetitions
from prepare_buffered_priority import ROOT, admit, check_readback, corpus_cases, merge_inputs, validator

BUILD = ROOT/'build/campaign-buffered-priority-v2-final'
READY = 'e6259bb479743e74f6e433cc60c34552d28e1cc35d2818d9252f537d66fe8bca'


class BufferedTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads((BUILD/'corpus.json').read_text())
        cls.original = json.loads((BUILD/'parent-derived/corpus.json').read_text())
        cls.layout = json.loads((BUILD/'readback-layout.json').read_text())
        cls.text = (BUILD/'seed0/run.stdout').read_text()
        cls.rows = [json.loads(line.split(' ', 1)[1]) for line in cls.text.splitlines() if line.startswith('IRIS_REGION ')]

    def test_real_frozen_packet_both_schedules_and_all_independent_goldens(self):
        ready, corpus, cases, elf, identities = admit(BUILD, READY)
        self.assertEqual(len(cases), 2208)
        self.assertEqual(sum(len(c['active_harts']) for c in cases), 4050)
        self.assertEqual(ready['elf_sha256'], '30598c1a89abaa2e7bd0a52b3734e3cf268ab35ecabbdab652ab9bc7b29e4ff3')
        self.assertIn(str(elf), identities)

    def test_changed_ready_and_old_corpus_refused(self):
        with self.assertRaises(ValueError): admit(BUILD, '0'*64)
        with self.assertRaises(ValueError): corpus_cases(self.original, self.original)

    def test_all_real_evidence_input_paths_are_absolute(self):
        _, _, _, _, identities = admit(BUILD, READY)
        self.assertTrue(all(Path(name).is_absolute() for name in identities))
        self.assertIn(str(ROOT/'calibration/empirical-priority-v2/policy.json'), identities)

    def test_relative_and_absolute_aliases_merge_or_refuse_conflicting_hashes(self):
        identities = {}
        merge_inputs(identities, {'benchmarks/campaign_buffered/main_reordered.c': 'a'*64})
        absolute = str(ROOT/'benchmarks/campaign_buffered/main_reordered.c')
        self.assertEqual(identities, {absolute: 'a'*64})
        merge_inputs(identities, {absolute: 'a'*64})
        with self.assertRaises(ValueError): merge_inputs(identities, {absolute: 'b'*64})

    def test_changed_independent_golden_mask_and_semantic_parent_refused(self):
        for field, value in [('expected_checksums', [99, 99, 99]), ('mask', 7),
                             ('semantic_parent_case_id', 'invented-parent'), ('trial_id', 2),
                             ('parent_case_id', 'baseline.empty')]:
            with self.subTest(field=field):
                bad = copy.deepcopy(self.corpus); bad['cases'][0][field] = value
                with self.assertRaises(ValueError): corpus_cases(bad, self.original)

    def test_duplicate_case_or_missing_parent_refused(self):
        bad = copy.deepcopy(self.corpus); bad['cases'][1] = bad['cases'][0]
        with self.assertRaises(ValueError): corpus_cases(bad, self.original)
        bad = copy.deepcopy(self.corpus); bad['cases'].pop()
        with self.assertRaises(ValueError): corpus_cases(bad, self.original)

    def test_actual_file_backed_sentinel_and_record_geometry(self):
        check_readback(BUILD/'campaign.elf', self.layout, self.corpus)
        for field, value in [('record_bytes', 32), ('records', 4049),
                             ('stop_sentinel_initial_value', 0), ('file_backed_initial_sentinel_verified', False)]:
            with self.subTest(field=field):
                bad = copy.deepcopy(self.layout); bad[field] = value
                with self.assertRaises(ValueError): check_readback(BUILD/'campaign.elf', bad, self.corpus)

    def test_real_console_corruptions_rejected_independently(self):
        lines = self.text.splitlines(); index = next(i for i, s in enumerate(lines) if s.startswith('IRIS_REGION '))
        for field in ('checksum', 'expected_checksum', 'parent_case_id', 'trial_id', 'hart', 'end_cycle'):
            with self.subTest(field=field):
                bad = list(lines); row = json.loads(bad[index].split(' ', 1)[1])
                if field == 'parent_case_id': row[field] = 'wrong-parent'
                elif field == 'end_cycle': row[field] = row['start_cycle']
                elif field == 'hart': row[field] = 3
                else: row[field] += 1
                bad[index] = 'IRIS_REGION '+json.dumps(row)
                with self.assertRaises(ValueError): validator().validate('\n'.join(bad), self.corpus)

    def test_missing_duplicate_and_legacy_phase_console_refused(self):
        lines = self.text.splitlines(); index = next(i for i, s in enumerate(lines) if s.startswith('IRIS_REGION '))
        altered = [lines[:index]+lines[index+1:], lines+[lines[index]],
                   [s for s in lines if not s.startswith('IRIS_BATCH_DONE ')],
                   lines+['IRIS_CAMPAIGN_PHASE {"suite":"baseline","trial_id":0,"begin":true}']]
        for bad in altered:
            with self.subTest(lines=len(bad)):
                with self.assertRaises(ValueError): validator().validate('\n'.join(bad), self.corpus)

    def test_actual_repetitions_preserve_semantic_lineage_and_all_trials(self):
        groups = repetitions(self.rows, self.corpus)
        self.assertEqual(len(groups), 1350)
        for group in groups:
            self.assertTrue(group['parent_case_id'].startswith('buffered.v2.'))
            self.assertFalse(group['semantic_parent_case_id'].startswith('buffered.v2.'))
            self.assertEqual([s['trial_id'] for s in group['samples']], [0, 1, 2])


if __name__ == '__main__': unittest.main()
