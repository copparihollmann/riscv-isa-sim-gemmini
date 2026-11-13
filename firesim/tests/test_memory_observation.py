"""Memory observer admission/ownership controls; no test opens a hardware device."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

FIRESIM = Path(__file__).parents[1]
sys.path.insert(0, str(FIRESIM))
import memory_observation as observer
import test_batch_runner as fixtures
batch = fixtures.batch


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / 'job'; self.output.mkdir()
        self.build = self.root / 'build'; self.build.mkdir()
        self.binary = b'reviewed observer unit-test stand-in; never executed'
        self.binary_sha = sha(self.binary)
        self.addCleanup(patch.stopall)
        patch.object(observer, 'BINARY_SHA', self.binary_sha).start()
        (self.build / 'readonly-fased-latency').write_bytes(self.binary)
        self.build_receipt = {'schema': 'iris.readonly_memory_observer_build.v1', 'pass': True,
            'source_sha256': observer.SOURCE_SHA, 'binary_sha256': self.binary_sha,
            'input_sha256': {}, 'artifact_sha256': {'readonly-fased-latency': self.binary_sha}}
        (self.build / 'report.json').write_text(json.dumps(self.build_receipt))
        self.audit = self.root / 'audit.json'
        self.audit_data = {'generated_header_sha256': observer.HEADER_SHA,
                           'fased': {'readable': {'writeLatency': 0, 'readLatency': 4}}}
        self.audit.write_text(json.dumps(self.audit_data))
        self.manifest = {'observability_audit': {'report': str(self.audit), 'sha256': observer.digest(self.audit), 'verified': True},
            'input_sha256': {}, 'lifecycle_started': True, 'active_phase': 'runworkload',
            'shared_lock': {'uid': 1003, 'user': 'agustin', 'boot_id': 'boot',
                            'authorization_id': 'test', 'authorization_sha256': 'a'*64},
            'lock_token': 'b'*32, 'launch_authorization_receipt': {'remote_path': '/home/agustin/.iris-model/authorizations/test.json'}}
        self.owned = '/scratch/agustin/firesim/' + 'b'*32

    def freeze(self):
        return observer.freeze(self.build, self.output, self.manifest)

    def test_freeze_binds_reviewed_layout_and_exact_executable_inputs(self):
        plan = self.freeze()
        self.assertEqual(plan['binary_sha256'], self.binary_sha)
        self.assertEqual(plan['device'], '/dev/xdma0_user')
        self.assertFalse(plan['calibration_usable'])
        self.assertIn(str(self.build / 'report.json'), self.manifest['input_sha256'])
        self.assertIn(str(Path(observer.__file__).resolve()), self.manifest['input_sha256'])
        self.assertEqual((self.output / plan['binary']).read_bytes(), self.binary)

    def test_changed_or_unreviewed_header_register_source_or_binary_refuses(self):
        for field in ('header', 'register', 'source', 'binary', 'audit_digest'):
            with self.subTest(field=field):
                audit = copy.deepcopy(self.audit_data); receipt = copy.deepcopy(self.build_receipt)
                if field == 'header': audit['generated_header_sha256'] = '0'*64
                if field == 'register': audit['fased']['readable']['readLatency'] = 8
                if field == 'source': receipt['source_sha256'] = '0'*64
                if field == 'binary': receipt['binary_sha256'] = '0'*64
                self.audit.write_text(json.dumps(audit)); (self.build / 'report.json').write_text(json.dumps(receipt))
                self.manifest['observability_audit']['sha256'] = observer.digest(self.audit)
                if field == 'audit_digest': self.manifest['observability_audit']['sha256'] = '0'*64
                with self.assertRaisesRegex(ValueError, 'audit|Unreviewed'):
                    self.freeze()
                self.assertFalse((self.output / 'memory-observation').exists())

    def remote(self):
        return {'status': 'sampled', 'returncode': 0, 'binary_sha256': self.binary_sha,
            'uid': 1003, 'base': self.owned, 'device_identity': {'bdf': '0000:01:00.0'},
            'probe': {'test_file': False, 'hardware_writes': False, 'access': 'O_RDONLY/PROT_READ',
                'register_width_bits': 32, 'presence_byte_offset': 356,
                'presence_verified_before_and_after': True, 'stable_two_samples': True,
                'writeLatency': {'byte_offset': 0, 'first': 37, 'second': 37},
                'readLatency': {'byte_offset': 4, 'first': 41, 'second': 41}}}

    def observe(self, remote=None):
        (self.output / 'run.json').write_text(json.dumps(self.manifest))
        completed = subprocess.CompletedProcess([], 0, json.dumps(remote or self.remote()).encode(), b'raw transport warning\xff')
        with patch.object(observer.subprocess, 'run', return_value=completed) as run:
            value = observer.observe(self.output, self.owned, 1003, ['ssh', 'never-contacted'])
        return value, run

    def test_valid_samples_remain_candidate_values_with_raw_transport_preserved(self):
        self.freeze(); result, run = self.observe()
        self.assertEqual(result['selected_parameters'], {'writeLatency': 37, 'readLatency': 41})
        self.assertFalse(result['calibration_usable']); self.assertFalse(result['loaded_image_readback_verified'])
        self.assertTrue(result['sampled_before_driver_initialization'])
        self.assertEqual((self.output / 'memory-observation/transport.stderr').read_bytes(), b'raw transport warning\xff')
        args = run.call_args.args[0]
        self.assertEqual(args[-4:], ['/usr/bin/python3', '-I', '-S', '-'])
        self.assertIn(b'own_lock()', run.call_args.kwargs['input'])
        compile(run.call_args.kwargs['input'], '<remote-observer>', 'exec')

    def test_bad_presence_unstable_allones_identity_or_types_never_become_values(self):
        self.freeze()
        for kind in ('presence', 'unstable', 'allones', 'bool', 'wrong_offset', 'test_file', 'uid', 'bdf', 'status'):
            with self.subTest(kind=kind):
                remote = self.remote(); probe = remote['probe']
                if kind == 'presence': probe['presence_verified_before_and_after'] = False
                if kind == 'unstable': probe['readLatency']['second'] = 99
                if kind == 'allones': probe['readLatency'].update(first=2**32-1, second=2**32-1)
                if kind == 'bool': probe['readLatency'].update(first=True, second=True)
                if kind == 'wrong_offset': probe['readLatency']['byte_offset'] = 0
                if kind == 'test_file': probe['test_file'] = True
                if kind == 'uid': remote['uid'] = 0
                if kind == 'bdf': remote['device_identity']['bdf'] = '0000:02:00.0'
                if kind == 'status': remote['status'] = 'unavailable'
                result, _ = self.observe(remote)
                self.assertIsNone(result['selected_parameters']); self.assertEqual(result['status'], 'unavailable')

    def test_not_in_active_lifecycle_or_changed_local_executable_never_uses_ssh(self):
        self.freeze()
        for change in ({'lifecycle_started': False}, {'active_phase': 'cleanup'}, {'lock_token': 'bad'}):
            saved = copy.deepcopy(self.manifest); self.manifest.update(change)
            with patch.object(observer.subprocess, 'run', side_effect=AssertionError('must not use SSH')):
                with self.assertRaises(ValueError): self.observe()
            self.manifest = saved
        (self.output / 'memory-observation/readonly-fased-latency').write_bytes(b'changed')
        with patch.object(observer.subprocess, 'run', side_effect=AssertionError('must not use SSH')):
            with self.assertRaisesRegex(ValueError, 'executable changed'):
                self.observe()

    def test_actual_remote_program_refuses_unowned_path_before_device_access(self):
        prefix = "BASE='/tmp/unowned'\nUID=1003\nLOCK={}\nAUTH=''\nBINARY=''\nEXPECTED=''\n"
        run = subprocess.run([sys.executable, '-I', '-S', '-'], input=(prefix + observer.REMOTE).encode(), capture_output=True, check=True)
        report = json.loads(run.stdout)
        self.assertFalse(report['hardware_access_started']); self.assertFalse(report['hardware_writes'])
        self.assertIsNone(report['selected_parameters'])
        self.assertIn('Invalid owned directory', report['error'])

    def test_transport_timeout_preserves_partial_raw_bytes_and_no_values(self):
        self.freeze(); (self.output / 'run.json').write_text(json.dumps(self.manifest))
        failure = subprocess.TimeoutExpired(['ssh'], 25, output=b'partial\xff', stderr=b'failed\x00')
        with patch.object(observer.subprocess, 'run', side_effect=failure):
            result = observer.observe(self.output, self.owned, 1003, ['ssh', 'never-contacted'])
        self.assertIsNone(result['selected_parameters']); self.assertEqual(result['status'], 'unavailable')
        self.assertEqual((self.output / 'memory-observation/transport.stdout').read_bytes(), b'partial\xff')
        self.assertEqual((self.output / 'memory-observation/transport.stderr').read_bytes(), b'failed\x00')


class ManagedObserverTests(unittest.TestCase):
    setUp = fixtures.BatchTests.setUp
    invoke = fixtures.BatchTests.invoke
    idle = staticmethod(fixtures.BatchTests.idle)

    def test_observer_runs_only_after_setup_with_held_lock_before_workload(self):
        self.manifest['readonly_memory_observation'] = {'unit_test_only': True}
        def observe(*args):
            self.assertEqual(self.tasks, ['kill', 'infrasetup']); self.assertEqual(self.locks, [True])
            return {'status': 'observed_candidate_values', 'selected_parameters': {'readLatency': 31}, 'calibration_usable': False}
        with patch.object(batch, 'observe_selected_memory_settings', side_effect=observe) as observation:
            self.invoke([self.idle()])
        self.assertEqual(observation.call_count, 1)
        self.assertEqual(self.tasks, ['kill', 'infrasetup', 'runworkload', 'kill'])
        self.assertEqual(self.locks, [True, False])
        stages = [x['stage'] for x in self.manifest['safety_inspections']]
        self.assertEqual(stages, ['kill', 'infrasetup', 'runworkload', 'readonly_memory_before', 'readonly_memory_after', 'cleanup'])

    def test_optional_observation_failure_does_not_mask_guest_or_skip_cleanup(self):
        self.manifest['readonly_memory_observation'] = {'unit_test_only': True}
        with patch.object(batch, 'observe_selected_memory_settings', side_effect=RuntimeError('read permission unavailable')):
            self.invoke([self.idle()])
        result = self.manifest['readonly_memory_observation_result']
        self.assertIsNone(result['selected_parameters']); self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(self.manifest['status'], 'completed_uncertified')
        self.assertEqual(self.tasks, ['kill', 'infrasetup', 'runworkload', 'kill'])

    def test_foreign_occupancy_before_probe_blocks_probe_workload_and_cleanup(self):
        self.manifest['readonly_memory_observation'] = {'unit_test_only': True}
        busy = dict(self.idle(), device_holders=[{'uid': 1003, 'cwd': '/foreign', 'pid': 7}])
        with patch.object(batch, 'observe_selected_memory_settings', side_effect=AssertionError('must not observe')) as observe:
            with self.assertRaisesRegex(RuntimeError, 'occupied'):
                self.invoke([self.idle()]*4 + [busy])
        observe.assert_not_called(); self.assertEqual(self.tasks, ['kill', 'infrasetup'])
        self.assertEqual(self.locks, [True]); self.assertTrue(self.manifest['lock_retained_for_operator'])

    def test_foreign_occupancy_after_probe_blocks_workload_and_foreign_cleanup(self):
        self.manifest['readonly_memory_observation'] = {'unit_test_only': True}
        busy = dict(self.idle(), device_holders=[{'uid': 0, 'cwd': '/foreign', 'pid': 7}])
        with patch.object(batch, 'observe_selected_memory_settings', return_value={'status': 'unavailable'}) as observe:
            with self.assertRaisesRegex(RuntimeError, 'occupied'):
                self.invoke([self.idle()]*5 + [busy])
        self.assertEqual(observe.call_count, 1); self.assertEqual(self.tasks, ['kill', 'infrasetup'])
        self.assertEqual(self.locks, [True]); self.assertTrue(self.manifest['lock_retained_for_operator'])


if __name__ == '__main__':
    unittest.main()
