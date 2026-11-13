import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('capture_run',Path(__file__).parents[1]/'capture_run.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.job=self.root/'job';self.job.mkdir()
        (self.job/'run.json').write_text('{"status":"failed","commands":[{"task":"infrasetup","returncode":1}]}')
        (self.job/'stderr').write_bytes(b'raw failure\x00\xff\n')
    def test_failure_logs_and_each_archived_byte_are_preserved(self):
        output=self.root/'evidence.tar.gz'
        module.capture(self.job,output)
        with tarfile.open(output) as archive:
            manifest=json.load(archive.extractfile('capture-manifest.json'))
            self.assertEqual(archive.extractfile('job/stderr').read(),b'raw failure\x00\xff\n')
            for row in manifest['files']:
                self.assertEqual(hashlib.sha256(archive.extractfile(row['path']).read()).hexdigest(),row['sha256'])
            self.assertFalse(manifest['hardware_contacted'])
    def test_shared_symlink_tree_and_secret_are_not_followed(self):
        shared=self.root/'shared';shared.mkdir();(shared/'auth.json').write_text('do not archive')
        (self.job/'manager-lib').symlink_to(shared,target_is_directory=True)
        (self.job/'linked-file').symlink_to(shared/'auth.json')
        output=self.root/'evidence.tar.gz';module.capture(self.job,output)
        with tarfile.open(output) as archive:
            self.assertFalse(any('auth.json' in name for name in archive.getnames()))
            manifest=json.load(archive.extractfile('capture-manifest.json'))
            self.assertEqual(len(manifest['skipped']),2)
    def test_cannot_overwrite_or_archive_recursively(self):
        output=self.root/'evidence.tar.gz';module.capture(self.job,output)
        with self.assertRaises(FileExistsError):module.capture(self.job,output)
        with self.assertRaises(ValueError):module.capture(self.job,self.job/'recursive.tar.gz')
    def test_context_missing_is_explicit_not_certification(self):
        (self.root/'AGENTS.md').write_text('required lifecycle')
        output=self.root/'evidence.tar.gz';module.capture(self.job,output,self.root)
        with tarfile.open(output) as archive:
            self.assertEqual(archive.extractfile('context/AGENTS.md').read(),b'required lifecycle')
            manifest=json.load(archive.extractfile('capture-manifest.json'))
            self.assertIn('hardware/manifest.json',manifest['missing_optional_context'])

if __name__=='__main__':unittest.main()
