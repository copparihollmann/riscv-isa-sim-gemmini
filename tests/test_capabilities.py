import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from iris_model.capabilities import load_verified, query


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "source").write_text("configured hardware\n")
        self.data = {"schema_version": 1, "scope": "hardware-source-audit", "bitstream_match_verified": False,
                     "repositories": {"rtl": {"commit": "a" * 40}},
                     "sources": {"config": {"repository": "rtl", "commit": "a" * 40,
                                            "snapshot": "source", "sha256": hashlib.sha256((self.root / "source").read_bytes()).hexdigest()}},
                     "capabilities": [dict(id="fp8", hart=0, unit="vme", status="configured",
                                           input_types=["ofp8_e4m3", "ofp8_e5m2"], accumulator_type="f32",
                                           output_types=["f32"], operations=["matrix_fma"],
                                           evidence=[{"source": "config", "lines": [1, 1]}]) ]}

    def path(self):
        path = self.root / "dtypes.json"
        path.write_text(json.dumps(self.data))
        return path

    def test_query_distinguishes_input_and_accumulator(self):
        data = load_verified(self.path())
        result = query(data, 0, "vme", "ofp8_e4m3", "matrix_fma", "input")
        self.assertTrue(result["configured_match_exists"])
        self.assertEqual(result["operation_support_decision"], "configured")
        self.assertFalse(result["bitstream_match_verified"])
        self.assertFalse(query(data, 0, "vme", "f32", role="input")["configured_match_exists"])
        self.assertTrue(query(data, 0, "vme", "f32", role="accumulator")["configured_match_exists"])
        self.assertFalse(query(data, 2, "vme", "ofp8_e4m3")["configured_match_exists"])
        self.assertEqual(query(data, 0, "vme", "ofp8_e4m3")["operation_support_decision"], "requires_operation")

    def test_unverified_is_not_enabled(self):
        self.data["capabilities"][0]["status"] = "unverified"
        self.assertFalse(query(load_verified(self.path()), 0)["configured_match_exists"])

    def test_changed_evidence_fails(self):
        path = self.path()
        (self.root / "source").write_text("different hardware\n")
        with self.assertRaisesRegex(ValueError, "digest mismatch"): load_verified(path)

    def test_missing_source_and_wrong_lines_fail(self):
        self.data["capabilities"][0]["evidence"][0]["lines"] = [1, 2]
        with self.assertRaisesRegex(ValueError, "evidence lines"): load_verified(self.path())


if __name__ == "__main__": unittest.main()
