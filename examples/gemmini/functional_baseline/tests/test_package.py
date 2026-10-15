"""Bounded source-integrity controls; no compiler or simulator invocation."""

import copy
import hashlib
import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("functional_build", ROOT / "build.py")
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_archive_bytes_are_checked_before_build(self):
        payload = b"pinned public source"
        (self.root / "spike.tar").write_bytes(payload)
        manifest = {
            "schema": "merlin.functional_spike_sources.v1",
            "package_files": {},
            "sources": {
                "spike": {
                    "archive": "spike.tar",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            },
        }
        (self.root / "sources.json").write_text(json.dumps(manifest))
        B.verify_package(self.root)
        (self.root / "spike.tar").write_bytes(payload + b"changed")
        with self.assertRaisesRegex(ValueError, "source archive changed"):
            B.verify_package(self.root)

    def test_declared_abi_must_match_header(self):
        profile = json.loads((ROOT / "profile.json").read_text())
        (self.root / "gemmini_params.h").write_text("""
#define DIM 16
#define ADDR_LEN 32
#define BANK_NUM 4
#define BANK_ROWS 4096
#define ACC_ROWS 1024
#define MAX_BYTES 64
#define XCUSTOM_ACC 3
typedef int8_t elem_t;
typedef int32_t acc_t;
#define ACC_READ_FULL_WIDTH
#define HAS_FIRST_LAYER_OPTIMIZATIONS
""")
        B.verify_abi(self.root, profile)
        changed = copy.deepcopy(profile)
        changed["software_abi"]["dim"] = 8
        with self.assertRaisesRegex(ValueError, "profile differs"):
            B.verify_abi(self.root, changed)

    def test_internal_source_symlink_preserved(self):
        archive = self.root / "source.tar"
        with tarfile.open(archive, "w") as output:
            regular = tarfile.TarInfo("fesvr/options.cc")
            regular.size = 1
            output.addfile(regular, io.BytesIO(b"x"))
            link = tarfile.TarInfo("spike_dasm/options.cc")
            link.type = tarfile.SYMTYPE
            link.linkname = "../fesvr/options.cc"
            output.addfile(link)
        B.unpack(archive, self.root / "unpacked")
        self.assertEqual(
            (self.root / "unpacked/spike_dasm/options.cc").read_bytes(), b"x"
        )

    def test_source_escape_refuses(self):
        archive = self.root / "source.tar"
        with tarfile.open(archive, "w") as output:
            link = tarfile.TarInfo("escape")
            link.type = tarfile.SYMTYPE
            link.linkname = "../outside"
            output.addfile(link)
        with self.assertRaisesRegex(ValueError, "escapes"):
            B.unpack(archive, self.root / "unpacked")
        self.assertFalse((self.root / "outside").exists())

    def test_full_source_roster_rejects_added_instrumentation(self):
        source = self.root / "spike"
        source.mkdir()
        (source / "core.cc").write_bytes(b"stock")
        expected = {
            "kind": "file",
            "bytes": 5,
            "sha256": hashlib.sha256(b"stock").hexdigest(),
        }
        manifest = {
            "sources": {
                "spike": {"source_roster": {"core.cc": expected}, "critical_files": {}}
            }
        }
        B.verify_sources(self.root, manifest)
        (source / "annotated_timing.cc").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "full extracted source roster"):
            B.verify_sources(self.root, manifest)

    def test_full_source_roster_rejects_changed_noncritical_file(self):
        source = self.root / "spike"
        source.mkdir()
        (source / "core.cc").write_bytes(b"stock")
        expected = {
            "kind": "file",
            "bytes": 5,
            "sha256": hashlib.sha256(b"stock").hexdigest(),
        }
        manifest = {
            "sources": {
                "spike": {"source_roster": {"core.cc": expected}, "critical_files": {}}
            }
        }
        (source / "core.cc").write_bytes(b"other")
        with self.assertRaisesRegex(ValueError, "full extracted source roster"):
            B.verify_sources(self.root, manifest)

    def test_runtime_does_not_copy_headers_or_source(self):
        prefix = self.root / "install"
        for name in (
            "bin/spike",
            "lib/libgemmini.so",
            "include/gemmini.h",
            "source/gemmini.cc",
        ):
            path = prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        receipt = {
            "artifacts": {
                name: {"sha256": B.sha(prefix / name)}
                for name in ("bin/spike", "lib/libgemmini.so")
            }
        }
        runtime = self.root / "runtime"
        B.prepare_runtime(prefix, runtime, receipt)
        self.assertEqual(
            {
                p.relative_to(runtime).as_posix()
                for p in runtime.rglob("*")
                if p.is_file()
            },
            {"bin/spike", "lib/libgemmini.so", "deployment.json"},
        )


if __name__ == "__main__":
    unittest.main()
