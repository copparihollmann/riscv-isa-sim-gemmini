"""Admission controls on the real frozen packet; no hardware actions."""
import copy
import json
from pathlib import Path
import unittest

from prepare_compute_fit import ROOT, admit, check_readback, corpus_cases, validator

BUILD = ROOT / 'build/compute-fit-v3'
READY = '430c407df3f818f9340a2a4edf97d711937ac367320dfcc150ba98945f687fff'


class ComputeAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads((BUILD / 'corpus.json').read_text())
        cls.original = json.loads((BUILD / 'original-corpus.json').read_text())
        cls.layout = json.loads((BUILD / 'readback-layout.json').read_text())
        cls.console = (BUILD / 'seed0/run.stdout').read_text()

    def test_exact_real_packet_and_both_independent_functional_schedules(self):
        _, _, cases, elf, inputs = admit(BUILD, READY)
        self.assertEqual(len(cases), 456)
        self.assertEqual(sum(len(c['active_harts']) for c in cases), 1008)
        self.assertIn(str(elf), inputs)
        self.assertTrue(all(Path(name).is_absolute() for name in inputs))

    def test_ready_byte_change_refuses(self):
        with self.assertRaises(ValueError): admit(BUILD, '0' * 64)

    def test_bulk_memory_injection_refuses(self):
        corpus = copy.deepcopy(self.corpus); corpus['cases'][0]['kind'] = 'memory'
        with self.assertRaises(ValueError): corpus_cases(corpus, self.original)

    def test_altered_parameters_or_independent_goldens_refuse(self):
        for field, value in [('n', 99), ('expected_checksums', [0, 0, 0]), ('mask', 4)]:
            corpus = copy.deepcopy(self.corpus); corpus['cases'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): corpus_cases(corpus, self.original)

    def test_reordered_or_missing_case_refuses(self):
        corpus = copy.deepcopy(self.corpus); corpus['cases'][0], corpus['cases'][1] = corpus['cases'][1], corpus['cases'][0]
        with self.assertRaises(ValueError): corpus_cases(corpus, self.original)
        corpus = copy.deepcopy(self.corpus); corpus['cases'].pop()
        with self.assertRaises(ValueError): corpus_cases(corpus, self.original)

    def test_old_corpus_cannot_claim_new_reference_identity(self):
        with self.assertRaises(ValueError): validator().validate(self.console, self.original)

    def test_independent_console_and_required_terminal(self):
        self.assertEqual(validator().validate(self.console, self.corpus)['regions'], 1008)
        with self.assertRaises(ValueError):
            validator().validate('\n'.join(line for line in self.console.splitlines()
                                            if not line.startswith('IRIS_BATCH_DONE ')), self.corpus)

    def test_corrupt_or_wrong_ELF_readback_refuses(self):
        check_readback(BUILD / 'campaign.elf', self.layout, self.corpus)
        changed = copy.deepcopy(self.layout); changed['objects']['buffered_records']['size'] += 8
        with self.assertRaises(ValueError): check_readback(BUILD / 'campaign.elf', changed, self.corpus)
        changed = copy.deepcopy(self.layout); changed['elf_sha256'] = '0' * 64
        with self.assertRaises(ValueError): check_readback(BUILD / 'campaign.elf', changed, self.corpus)


if __name__ == '__main__': unittest.main()
