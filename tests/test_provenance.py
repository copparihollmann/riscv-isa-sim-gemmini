import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from iris_model.provenance import verify


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "patch").write_text("tracked changes\n")
        (self.root / "source").write_text("hardware fact\n")
        sha = lambda name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.manifest = {"certified": False, "calibration_usable": False,
                         "repositories": {"rtl": {"commit": "a" * 40, "tracked_diff": "patch",
                                                   "tracked_diff_sha256": sha("patch")}},
                         "sources": {"config": {"snapshot": "source", "sha256": sha("source"),
                                                "repository": "rtl", "repository_commit": "a" * 40}},
                         "facts": {"harts": {"value": 3, "evidence": {"source": "config", "lines": [1, 1]}}}}

    def save(self):
        path = self.root / "manifest.json"
        path.write_text(json.dumps(self.manifest))
        return path

    def test_integrity_does_not_imply_certification(self):
        result = verify(self.save())
        self.assertEqual(result["evidence_integrity"], "pass")
        self.assertFalse(result["calibration_usable"])

    def test_source_change_invalidates(self):
        path = self.save()
        (self.root / "source").write_text("different RTL\n")
        with self.assertRaisesRegex(ValueError, "digest mismatch"): verify(path)

    def test_patch_change_invalidates(self):
        path = self.save()
        (self.root / "patch").write_text("different patch\n")
        with self.assertRaisesRegex(ValueError, "patch digest"): verify(path)

    def test_full_commit_required(self):
        self.manifest["repositories"]["rtl"]["commit"] = "a" * 7
        with self.assertRaisesRegex(ValueError, "full commit"): verify(self.save())

    def test_fact_line_outside_source_fails(self):
        self.manifest["facts"]["harts"]["evidence"]["lines"] = [1, 2]
        with self.assertRaisesRegex(ValueError, "line reference"): verify(self.save())


if __name__ == "__main__": unittest.main()
