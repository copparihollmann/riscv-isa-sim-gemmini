"""Integrity and clock qualification at the source-profile input boundary."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from iris_model.saturn_profile_cli import Capsule, projection_rows, timebase


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ProfileCapsuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def capsule(self, documents):
        entries = []
        for name, value in documents.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            path.write_bytes(data)
            entries.append({'path': name, 'sha256': sha(data), 'bytes': len(data),
                            'mode': path.stat().st_mode & 0o7777})
        data = json.dumps({'schema': 'iris.saturn_qualified_activity_frozen_capsule.v1',
                           'pass': True, 'artifacts': entries}).encode()
        (self.root / 'report.json').write_bytes(data)
        return Capsule(self.root, sha(data))

    def clock_fixture(self, change=None):
        driver = b'always #(`CLOCK_PERIOD/2.0) clock = ~clock;\nalways @(posedge clock) trace_count = trace_count + 1;\n'
        build = {'verilate_argv': ['verilator', '--timescale', '1ns/1ps',
                                  '+define+CLOCK_PERIOD=1.0'],
                 'source_sha256': {'/source/TestDriver.v': sha(driver)}}
        if change:
            change(build)
        build_bytes = json.dumps(build).encode()
        observer = {'schema': 'iris.saturn_activity_whole_rtl_observer.v1',
                    'input_sha256': {'/reference/build.json': sha(build_bytes)}}
        observer_bytes = json.dumps(observer).encode()
        capture = {'exit_status': 0, 'timed_out': False,
                   'same_architectural_signature_as_frozen_guest': True,
                   'input_sha256': {'/observer/build.json': sha(observer_bytes)}}
        capture_bytes = json.dumps(capture).encode()
        capsule = self.capsule({'rtl/TestDriver.v': driver, 'reference/build.json': build_bytes,
                                'observer/build.json': observer_bytes,
                                'vme/report.json': capture_bytes})
        proof = {'input_sha256': {'/reference/vme/report.json': sha(capture_bytes)}}
        return capsule, proof

    def test_capture_clock_uses_the_bound_reference_not_a_cpu_or_host_frequency(self):
        capsule, proof = self.clock_fixture()
        hz, source = timebase(capsule, proof, 'vme')
        self.assertEqual(hz, 1e9)
        self.assertIn('distinct from per-hart mcycle', source['coordinate'])
        self.assertEqual(source['compiled_CLOCK_PERIOD_ns'], '1.0')

    def test_wrong_receipt_and_changed_or_uninventoried_artifacts_refuse(self):
        capsule = self.capsule({'data.json': {'known': True}})
        with self.assertRaisesRegex(ValueError, 'receipt SHA256'):
            Capsule(self.root, '0' * 64)
        with self.assertRaisesRegex(ValueError, 'Uninventoried/unsafe'):
            capsule.path('../escape')
        with self.assertRaisesRegex(ValueError, 'Uninventoried/unsafe'):
            capsule.path('missing')
        (self.root / 'data.json').write_text('{"known":false}')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            capsule.path('data.json')

    def test_symlink_substitution_and_mode_changes_refuse(self):
        capsule = self.capsule({'data.json': {'known': True}})
        path = self.root / 'data.json'
        path.chmod(0o400)
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            capsule.path('data.json')
        path.rename(self.root / 'original.json')
        path.symlink_to('original.json')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            capsule.path('data.json')

    def test_unqualified_clock_and_missing_capture_do_not_gain_a_default(self):
        def duplicate_period(build):
            build['verilate_argv'].append('+define+CLOCK_PERIOD=2.0')
        for kind in ('timescale', 'period', 'duplicate', 'driver'):
            def change(build):
                if kind == 'timescale':
                    build['verilate_argv'][2] = '1ps/1ps'
                elif kind == 'period':
                    build['verilate_argv'][-1] = '+define+CLOCK_PERIOD=NaN'
                elif kind == 'duplicate':
                    duplicate_period(build)
                else:
                    build['source_sha256'] = {}
            capsule, proof = self.clock_fixture(change)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                timebase(capsule, proof, 'vme')
        capsule, proof = self.clock_fixture()
        with self.assertRaisesRegex(ValueError, 'Unique actual'):
            timebase(capsule, proof, 'unmeasured')

    def projection(self, data=b'[0,0,3,1,1]\n[1,0,3,1,1]\n'):
        path = self.root / 'projection.ndjson.gz'
        path.write_bytes(gzip.compress(data, mtime=0))
        return path, sha(path.read_bytes())

    def test_projection_hash_and_complete_consumption_are_required(self):
        path, expected = self.projection()
        with projection_rows(path, expected) as rows:
            self.assertEqual(list(rows), [[0, 0, 3, 1, 1], [1, 0, 3, 1, 1]])
        with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
            with projection_rows(path, '0' * 64) as rows:
                list(rows)
        with self.assertRaisesRegex(ValueError, 'Complete projection'):
            with projection_rows(path, expected) as rows:
                next(rows)

    def test_projection_path_replacement_and_truncated_gzip_refuse(self):
        path, expected = self.projection()
        with self.assertRaisesRegex(ValueError, 'changed while profiling'):
            with projection_rows(path, expected) as rows:
                list(rows)
                path.rename(self.root / 'old.gz')
                path.write_bytes((self.root / 'old.gz').read_bytes())
        path.write_bytes(path.read_bytes()[:-5])
        with self.assertRaises(EOFError):
            with projection_rows(path, sha(path.read_bytes())) as rows:
                list(rows)

    def test_projection_oversized_records_refuse_before_unbounded_decode(self):
        path, expected = self.projection(b'[' + b'0,' * 40000 + b'0]\n')
        with self.assertRaisesRegex(ValueError, 'Oversized'):
            with projection_rows(path, expected) as rows:
                list(rows)


if __name__ == '__main__':
    unittest.main()
