import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest


PATH = Path(__file__).resolve().parents[1] / 'integration/iris-mlir/configure_empirical_v2.py'
SPEC = importlib.util.spec_from_file_location('iris_empirical_publisher_v2_archive_tests', PATH)
PUBLISHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISHER)


class ActualArchiveMemberTests(unittest.TestCase):
    def archive(self, directory, entries):
        path = Path(directory) / 'artifacts.tar.gz'
        with tarfile.open(path, 'w:gz') as target:
            for name, payload in entries:
                info = tarfile.TarInfo(name)
                if payload is None:
                    info.type = tarfile.SYMTYPE; info.linkname = 'foreign-file'
                    target.addfile(info)
                else:
                    info.size = len(payload); target.addfile(info, io.BytesIO(payload))
        return path

    def test_hashes_actual_member_bytes_without_extracting_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.archive(directory, [('other', b'ignored'), ('nested/firesim.bit', b'actual-image')])
            result = PUBLISHER.archived_member(path, 'firesim.bit')
            self.assertEqual(result, {'name': 'nested/firesim.bit', 'bytes': 12,
                                     'sha256': hashlib.sha256(b'actual-image').hexdigest()})
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['artifacts.tar.gz'])

    def test_duplicate_basename_and_duplicate_path_refuse(self):
        for names in [('a/firesim.bit', 'b/firesim.bit'), ('a/firesim.bit', 'a/firesim.bit')]:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as directory:
                path = self.archive(directory, [(name, b'image') for name in names])
                with self.assertRaisesRegex(ValueError, 'Unique actual'):
                    PUBLISHER.archived_member(path, 'firesim.bit')

    def test_link_cannot_substitute_for_actual_member(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.archive(directory, [('firesim.bit', None)])
            with self.assertRaisesRegex(ValueError, 'regular file'):
                PUBLISHER.archived_member(path, 'firesim.bit')

    def test_absent_member_refuses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.archive(directory, [('unrelated', b'image')])
            with self.assertRaisesRegex(ValueError, 'Unique actual'):
                PUBLISHER.archived_member(path, 'FireSim-corigine_mimicturbo_gt')


if __name__ == '__main__': unittest.main()
