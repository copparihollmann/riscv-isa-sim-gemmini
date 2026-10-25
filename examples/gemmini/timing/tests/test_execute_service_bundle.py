"""Distinct evaluator release keeps its reviewed legacy substrate unchanged."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from merlin_timing import provider_bundle as B

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "execute_service_export", ROOT / "export_execute_service.py"
)
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)


class ExecuteServiceBundleTests(unittest.TestCase):
    def test_distinct_closed_bundle(self):
        with tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"]) as folder:
            base = Path(folder)
            legacy = base / "legacy"
            B.export_bundle(
                {
                    name: (ROOT / name).read_bytes()
                    for name in (
                        "bridge.cpp",
                        "provider.hpp",
                        "staged.hpp",
                        "README.md",
                    )
                },
                legacy,
                entrypoint="bridge.cpp",
                runtime_headers=B.RUNTIME_HEADERS,
            )
            selected = base / "selected"
            receipt = E.export(legacy, selected)
            self.assertEqual(receipt, B.verify_bundle(selected))
            self.assertEqual(
                (selected / "legacy_bridge.cpp").read_bytes(),
                (legacy / "bridge.cpp").read_bytes(),
            )
            for name in ("provider.hpp", "staged.hpp", "README.md"):
                self.assertEqual(
                    (selected / name).read_bytes(), (legacy / name).read_bytes()
                )
            self.assertEqual(
                (selected / "bridge.cpp").read_bytes(),
                E.specialize_bridge((legacy / "bridge.cpp").read_bytes()),
            )
            self.assertNotEqual(
                hashlib.sha256((selected / "bridge.cpp").read_bytes()).digest(),
                hashlib.sha256((legacy / "bridge.cpp").read_bytes()).digest(),
            )
            with self.assertRaises(ValueError):
                E.export(legacy, selected)
            (selected / "execute_service.hpp").write_bytes(b"mutated")
            with self.assertRaises(ValueError):
                B.verify_bundle(selected)

    def test_changed_legacy_bridge_refused(self):
        with self.assertRaisesRegex(ValueError, "exact reviewed legacy bridge"):
            E.specialize_bridge((ROOT / "bridge.cpp").read_bytes() + b"\n")


if __name__ == "__main__":
    unittest.main()
