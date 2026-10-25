"""Pure standard-library source-custody controls; no compilation or simulation."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from merlin_timing import provider_bundle as BUILD

ROOT = Path(__file__).absolute().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXPORT = load("export_config")


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="provider-bundle-", dir=os.environ["TMPDIR"])
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.document = json.loads((ROOT / "stock_u250.json").read_bytes())
        self.bundle = self.base / "bundle"
        self.receipt = EXPORT.export_bundle(self.document, self.bundle)

    def test_closed_roster_and_reproducibility(self):
        self.assertEqual(self.receipt, BUILD.verify_bundle(self.bundle))
        self.assertLessEqual(self.receipt["total_bytes"], 1024 * 1024)
        second = self.base / "second"
        self.assertEqual(self.receipt, EXPORT.export_bundle(self.document, second))
        self.assertEqual(json.loads((second / "stock_u250.json").read_bytes()), self.document)
        self.assertEqual((second / "staged.hpp").read_bytes(), (ROOT / "staged.hpp").read_bytes())
        self.assertEqual({path.name for path in second.iterdir()},
                         {*(row["path"] for row in self.receipt["members"]), BUILD.MANIFEST})
        # Exported tooling must work without Merlin installed or importable.
        checked = subprocess.run([sys.executable, "-I", "-S", second / "build_provider.py", "--verify-only"],
                                 check=True, capture_output=True, text=True, timeout=10)
        self.assertEqual(json.loads(checked.stdout), self.receipt)

    def test_changed_member(self):
        source = self.bundle / "provider.hpp"
        source.write_bytes(source.read_bytes() + b"\n// mutation\n")
        with self.assertRaisesRegex(ValueError, "identity differs"):
            BUILD.verify_bundle(self.bundle)

    def test_changed_staged_member(self):
        source = self.bundle / "staged.hpp"
        source.write_bytes(source.read_bytes() + b"\n// mutation\n")
        with self.assertRaisesRegex(ValueError, "identity differs"):
            BUILD.verify_bundle(self.bundle)

    def test_missing_member(self):
        (self.bundle / "bridge.cpp").unlink()
        with self.assertRaisesRegex(ValueError, "missing, repeated or additional"):
            BUILD.verify_bundle(self.bundle)

    def test_additional_member(self):
        (self.bundle / "kernel.cpp").write_bytes(b"not part of the provider")
        with self.assertRaisesRegex(ValueError, "missing, repeated or additional"):
            BUILD.verify_bundle(self.bundle)

    def test_symlink_members_and_destinations(self):
        member = self.bundle / "README.md"
        moved = self.base / "saved-readme"
        member.rename(moved)
        member.symlink_to(moved)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            BUILD.verify_bundle(self.bundle)
        linked = self.base / "linked"
        linked.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            EXPORT.export_bundle(self.document, linked)

    def test_size_bound(self):
        (self.bundle / "README.md").write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, "byte budget"):
            BUILD.verify_bundle(self.bundle)

    def test_existing_destination_and_in_bundle_output(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            EXPORT.export_bundle(self.document, self.bundle)
        with self.assertRaisesRegex(ValueError, "outside the closed"):
            BUILD.build(self.bundle, self.base, self.bundle / "provider.so", "unused-compiler")
        nested = self.base / "outside" / ".." / "bundle" / "provider.so"
        with self.assertRaisesRegex(ValueError, "outside the closed"):
            BUILD.build(self.bundle, self.base, nested, "unused-compiler")

    def test_manifest_roster_cannot_name_outside_files(self):
        path = self.bundle / BUILD.MANIFEST
        manifest = json.loads(path.read_bytes())
        manifest["members"][0]["path"] = "../saved-readme"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "relative filenames"):
            BUILD.verify_bundle(self.bundle)


if __name__ == "__main__":
    unittest.main()
