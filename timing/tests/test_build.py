"""Source-custody regressions without configuring or compiling a simulator."""

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class BuildCustody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os

        cls.base = Path(os.environ["TMPDIR"]) / "annotated-builder-controls"
        cls.base.mkdir(parents=True, exist_ok=True)

    def invoke(self, path):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "timing/build.py"),
                "--build-dir",
                str(path),
                "--identity-only",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_foreign_checkout_preserves_existing_identity(self):
        for source in ("/different/checkout", "."):
            directory = self.base / (
                "foreign-absolute" if source.startswith("/") else "foreign-relative"
            )
            directory.mkdir(exist_ok=True)
            (directory / "Makefile").write_text("src_dir := " + source + "\n")
            receipt = directory / "timing-source-manifest.json"
            receipt.write_text('{"sentinel":true}')
            header = directory / "timing_build_identity.h"
            header.write_text("original identity")
            result = self.invoke(directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("different source checkout", result.stderr)
            self.assertEqual(receipt.read_text(), '{"sentinel":true}')
            self.assertEqual(header.read_text(), "original identity")

    def test_symlink_destination_refused(self):
        destination = self.base / "actual"
        destination.mkdir(exist_ok=True)
        link = self.base / "link"
        if not link.exists():
            link.symlink_to(destination, target_is_directory=True)
        result = self.invoke(link)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlinks", result.stderr)
        self.assertFalse((destination / "timing-source-manifest.json").exists())

    def test_exported_core_manifest_matches(self):
        spec = importlib.util.spec_from_file_location(
            "build_identity", ROOT / "timing/build.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        identity = module.source_identity()
        members = {row["path"]: row for row in identity["members"]}
        core = json.loads((ROOT / "timing/core/source-manifest.json").read_text())
        for row in core["members"]:
            if "timing/core/" + row["path"] in members:
                self.assertEqual(
                    members["timing/core/" + row["path"]]["sha256"], row["sha256"]
                )


if __name__ == "__main__":
    unittest.main()
