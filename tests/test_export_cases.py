import json
from pathlib import Path
import unittest

from benchmarks.export_cases import export
from firesim.batch_runner import validate_cases


class ExportTests(unittest.TestCase):
    def corpus(self):
        return json.loads((Path(__file__).resolve().parents[1] / "benchmarks/calibration-corpus.json").read_text())

    def test_manifests_match_actual_region_coverage(self):
        for smoke, expected in ((True, 12), (False, 54)):
            rows = validate_cases(export(self.corpus(), smoke=smoke))
            self.assertEqual(sum(len(row["active_harts"]) for row in rows), expected)

    def test_reduced_participation_drops_hart2_case(self):
        for harts in (1, 2):
            rows = validate_cases(export(self.corpus(), harts=harts))
            self.assertTrue(all(hart < harts for row in rows for hart in row["active_harts"]))

    def test_duplicate_identity_fails(self):
        corpus = self.corpus()
        corpus["cases"].append(dict(corpus["cases"][0]))
        with self.assertRaises(ValueError): export(corpus)

    def test_export_keeps_independent_host_checksums(self):
        rows=validate_cases(export(self.corpus(),smoke=True),require_goldens=True)
        expected={row['case_id']:row['expected_checksums_by_hart'] for row in self.corpus()['cases']}
        self.assertTrue(all(row['expected_checksums_by_hart']==expected[row['id']] for row in rows))

    def test_v2_masks_and_golden_roles_are_exported_without_dropping_hart2(self):
        corpus={'split_id':'fixture','expected_region_count':4,'cases':[
            {'case_id':'all','mask':7,'region':'kernel','expected_checksums':[1,2,3]},
            {'case_id':'rocket','mask':4,'region':'kernel','expected_checksums':[0,0,9]}]}
        rows=validate_cases(export(corpus),require_goldens=True)
        self.assertEqual([row['active_harts'] for row in rows],[[0,1,2],[2]])
        self.assertEqual(rows[1]['expected_checksums_by_hart'][2],9)
        with self.assertRaises(ValueError):export(corpus,harts=2)


if __name__ == "__main__": unittest.main()
