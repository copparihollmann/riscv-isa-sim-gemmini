"""Mocked managed postrun readout checks. No test opens a hardware device."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

FS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FS))
import memory_observation_postrun_v2 as post


class PostrunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.job = self.root / 'job'
        self.manager = self.job / 'manager'
        (self.manager / 'workloads/iris-batch').mkdir(parents=True)
        (self.manager / 'results-workload').mkdir()
        (self.manager / 'firesim').write_text('local unit fixture; never executed')
        self.image = self.root / 'image.tar.gz'; self.image.write_bytes(b'image-fixture')
        self.driver = self.root / 'driver.tar.gz'; self.driver.write_bytes(b'driver-fixture')
        elf = self.manager / 'workloads/iris-batch/batch.elf'; elf.write_bytes(b'ELF-unit-fixture')
        (self.manager / 'config_hwdb.yaml').write_text('unit: true\n')
        runtime = {'run_farm': {'recipe_arg_overrides': {}}, 'target_config': {'unchanged': 77}}
        (self.manager / 'config_runtime.yaml').write_text(yaml.safe_dump(runtime))
        (self.manager / 'workloads/iris-batch.json').write_text(json.dumps({'benchmark_name': 'iris-batch'}))
        self.audit = self.root / 'audit.json'
        self.audit.write_text(json.dumps({'driver_binary_sha256': post.DRIVER_ELF_SHA,
             'generated_header_sha256': post.original.HEADER_SHA, 'input_sha256': {}}))
        self.build = self.root / 'probe'; self.build.mkdir()
        binary = self.build / 'readonly-fased-config-v2'; binary.write_bytes(b'mock observer; NEVER executed')
        receipt = {'schema': 'iris.readonly_fased_config_observer_build.v2', 'pass': True,
                   'source_sha256': post.original.SOURCE_SHA, 'binary_sha256': post.digest(binary), 'registers': post.original.REGISTER_MAP,
                   'input_sha256': {}, 'artifact_sha256': {'readonly-fased-config-v2': post.digest(binary)}}
        (self.build / 'report.json').write_text(json.dumps(receipt))
        self.patches = [patch.object(post.original, 'verify_audit', return_value={}), patch.object(post, 'IMAGE_TAR_SHA', post.digest(self.image)),
                        patch.object(post, 'DRIVER_TAR_SHA', post.digest(self.driver)),
                        patch.object(post, 'OBSERVABILITY_SHA', post.digest(self.audit)),
                        patch.object(post.original, 'BINARY_SHA', post.digest(binary))]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        self.manifest = {'schema_version': 1, 'status': 'prepared', 'created_at_utc': 'unit-test', 'commands': [],
                        'runner_sha256': post.digest(FS / 'batch_runner.py'),
                        'prepared_manager_sha256': post.digest(self.manager / 'firesim'),
                        'prepared_runtime_sha256': post.digest(self.manager / 'config_runtime.yaml'),
                        'prepared_hwdb_sha256': post.digest(self.manager / 'config_hwdb.yaml'),
                        'elf_sha256': post.digest(elf),
                        'image': {'uri': self.image.as_uri(), 'sha256': post.digest(self.image)},
                        'driver': {'uri': self.driver.as_uri(), 'sha256': post.digest(self.driver)},
                        'observability_audit': {'report': str(self.audit), 'sha256': post.digest(self.audit), 'verified': True},
                        'capture_checklist_frozen': True, 'require_regions': True, 'require_goldens': True,
                        'cases': [{'id': 'unit.case', 'active_harts': [0], 'region': 'kernel', 'expected_checksums_by_hart': [7]}],
                        'launch_authorization_receipt': {'sha256': 'a'*64, 'remote_path': '/home/agustin/.iris-model/authorizations/unit.json'},
                        'input_sha256': {str(self.audit): post.digest(self.audit)},
                        'prepared_file_sha256': {str(p.relative_to(self.job)): post.digest(p) for p in self.manager.rglob('*') if p.is_file()}}
        post.batch.save_manifest(self.job, self.manifest)

    def install(self, prototype=False):
        return post.install(self.job, post.digest(self.job / 'run.json'), self.build, 'never-contacted', prototype)

    def active(self, prototype=False):
        result = self.install(prototype)
        self.plan_sha = result['plan_sha256']
        m = json.loads((self.job / 'run.json').read_text())
        self.token = 'b'*32; self.owned = '/scratch/agustin/firesim/' + self.token
        m.update(lifecycle_started=True, active_phase='runworkload', lock_token=self.token,
                 remote_simulation_dir=self.owned, cleanup_status='not_started',
                 shared_lock={'uid': 1003, 'user': 'agustin', 'boot_id': 'boot-unit',
                              'authorization_id': 'auth-unit', 'authorization_sha256': 'a'*64},
                 commands=[{'task': x, 'status': 'passed', 'returncode': 0, 'timed_out': False} for x in ('kill', 'infrasetup')]
                          + [{'task': 'runworkload', 'status': 'running'}])
        runtime = yaml.safe_load((self.manager / 'config_runtime.yaml').read_text())
        runtime['run_farm']['recipe_arg_overrides']['default_simulation_dir'] = self.owned
        (self.manager / 'config_runtime.yaml').write_text(yaml.safe_dump(runtime))
        m['execution_runtime_sha256'] = post.digest(self.manager / 'config_runtime.yaml')
        post.batch.save_manifest(self.job, m)
        self.results = self.manager / 'results-workload/unit-iris-batch'; self.results.mkdir()
        self.console = self.results / 'uartlog'
        row = dict(case_id='unit.case', region='kernel', hart=0, start_cycle=10, end_cycle=20,
                   instret_delta=3, checksum=7, expected_checksum=7, **{'pass': True})
        self.console.write_text('Commencing simulation.\nIRIS_REGION ' + json.dumps(row)
                               + '\nSimulation complete.\n*** PASSED ***\n[COMMAND_EXIT_CODE="0"]\n')
        self.m = m

    def idle(self):
        return {'busy_processes': [], 'device_holders': [], 'inspection_complete': True,
                'inspection_method': 'fixed-root-helper', 'uid': 1003, 'user': 'agustin', 'boot_id': 'boot-unit',
                'launch_authorization_verified': True, 'launch_authorization': {
                    'authorization_id': 'auth-unit', 'authorization_source': 'explicit_current_user_launch_instruction',
                    'uid': 1003, 'user': 'agustin', 'boot_id': 'boot-unit', 'expires_at_utc': '2099-01-01T00:00:00+00:00'},
                'fpga_db_present': True, 'fpga_bdfs': ['0000:01:00.0'], 'pci_inventory': ['0000:01:00.0']}

    def remote(self):
        return {'status': 'sampled', 'returncode': 0, 'binary_sha256': post.original.BINARY_SHA,
                'uid': 1003, 'base': self.owned, 'device_identity': {'bdf': '0000:01:00.0'},
                'probe': {'schema': post.original.PROBE_SCHEMA, 'test_file': False, 'hardware_writes': False, 'access': 'O_RDONLY/PROT_READ',
                          'register_width_bits': 32, 'presence_byte_offset': 356,
                          'presence_verified_before_and_after': True, 'stable_two_samples': True,
                          'writeLatency': {'byte_offset': 0, 'first': 37, 'second': 37},
                          'readLatency': {'byte_offset': 4, 'first': 41, 'second': 41},
                          'writeMaxReqs': {'byte_offset': 8, 'first': 5, 'second': 5},
                          'readMaxReqs': {'byte_offset': 12, 'first': 7, 'second': 7},
                          'relaxFunctionalModel': {'byte_offset': 72, 'first': 1, 'second': 1}}}

    def observe(self, inspections=None, remote=None, transport_error=None):
        inspections = inspections or [self.idle(), self.idle()]
        with patch.object(post.batch, 'checked_remote_lock') as lock, \
             patch.object(post.batch, 'inspect_remote', side_effect=inspections) as inspect, \
             patch.object(post.batch, 'bind_launch_authorization', side_effect=lambda host, value, m: value), \
             patch.object(post, 'capture_remote', side_effect=transport_error, return_value=remote or self.remote()) as capture:
            result = post.observe(self.job, self.plan_sha, self.results)
        return result, lock, inspect, capture

    def test_install_is_additive_and_preinit_directory_is_untouched(self):
        original = self.job / 'memory-observation'; original.mkdir(); (original / 'keep').write_text('preserved')
        result = self.install()
        self.assertFalse(result['hardware_contacted'])
        m = post.run_prepared.verify(self.job)
        self.assertEqual((original / 'keep').read_text(), 'preserved')
        w = json.loads((self.manager / 'workloads/iris-batch.json').read_text())
        self.assertEqual(w['post_run_hook'], str(self.job / post.DIRECTORY / 'hook.sh'))
        self.assertIn(result['plan_sha256'], (self.job / post.DIRECTORY / 'hook.sh').read_text())
        self.assertEqual(m['commands'], [])

    def test_normal_postrun_records_values_but_no_latency_or_image_claim(self):
        self.active(); before = (self.job / 'run.json').read_bytes()
        r, lock, inspect, capture = self.observe()
        self.assertEqual(r['status'], 'observed_postdriver_configuration_registers')
        self.assertEqual(r['selected_parameters'], {'writeLatency': 37, 'readLatency': 41, 'writeMaxReqs': 5, 'readMaxReqs': 7, 'relaxFunctionalModel': 1})
        self.assertTrue(r['sampled_after_normal_driver_exit']); self.assertEqual(r['completion']['region_count'], 1)
        self.assertFalse(r['calibration_usable']); self.assertFalse(r['physical_memory_latency_measured'])
        self.assertEqual(lock.call_count, 2); self.assertEqual(inspect.call_count, 2); capture.assert_called_once()
        self.assertEqual((self.job / 'run.json').read_bytes(), before)

    def test_pre_and_post_occupancy_unknown_boot_authorization_refuse(self):
        for phase in (0, 1):
            for bad in ('foreign', 'sameuid_holder', 'incomplete', 'reboot', 'expired'):
                with self.subTest(phase=phase, bad=bad):
                    if not hasattr(self, 'plan_sha'): self.active()
                    (self.job / post.DIRECTORY / 'observation.json').unlink(missing_ok=True)
                    samples = [self.idle(), self.idle()]
                    if bad == 'foreign': samples[phase]['busy_processes'] = [{'uid': 0, 'cwd': '/foreign'}]
                    if bad == 'sameuid_holder': samples[phase]['device_holders'] = [{'uid': 1003, 'cwd': self.owned}]
                    if bad == 'incomplete': samples[phase]['inspection_complete'] = False
                    if bad == 'reboot': samples[phase]['boot_id'] = 'changed'
                    if bad == 'expired': samples[phase]['launch_authorization']['expires_at_utc'] = '2000-01-01T00:00:00+00:00'
                    r, lock, inspect, capture = self.observe(samples)
                    self.assertIsNone(r['selected_parameters']); self.assertEqual(r['status'], 'unavailable')
                    self.assertEqual(capture.call_count, phase)

    def test_wrong_runtime_case_goldens_plan_source_and_phase_never_reads(self):
        self.active(); saved = (self.job / 'run.json').read_bytes(); raw_console = self.console.read_bytes()
        path = self.manager / 'config_runtime.yaml'; raw_runtime = path.read_bytes()
        for bad in ('cleanup', 'wrong_input', 'wrong_case', 'runtime', 'plan', 'nonzero', 'noexit', 'nodriverpass'):
            with self.subTest(bad=bad):
                (self.job / post.DIRECTORY / 'observation.json').unlink(missing_ok=True)
                (self.job / 'run.json').write_bytes(saved); self.console.write_bytes(raw_console); path.write_bytes(raw_runtime)
                m = json.loads(saved); expected = self.plan_sha
                if bad == 'cleanup': m['active_phase'] = 'cleanup'
                if bad == 'wrong_input': m['input_sha256'][str(self.audit)] = '0'*64
                if bad == 'wrong_case': self.console.write_text(self.console.read_text().replace('"checksum": 7', '"checksum": 8'))
                if bad == 'runtime':
                    v = yaml.safe_load(path.read_text()); v['target_config']['unchanged'] = 88
                    path.write_text(yaml.safe_dump(v)); m['execution_runtime_sha256'] = post.digest(path)
                if bad == 'plan': expected = '0'*64
                if bad == 'nonzero': self.console.write_text(self.console.read_text().replace('COMMAND_EXIT_CODE="0"', 'COMMAND_EXIT_CODE="1"'))
                if bad == 'noexit': self.console.write_text(self.console.read_text().replace('[COMMAND_EXIT_CODE="0"]', ''))
                if bad == 'nodriverpass': self.console.write_text(self.console.read_text().replace('*** PASSED ***', ''))
                post.batch.save_manifest(self.job, m)
                with patch.object(post.batch, 'inspect_remote', side_effect=AssertionError('must not inspect')), \
                     patch.object(post, 'capture_remote', side_effect=AssertionError('must not read')):
                    r = post.observe(self.job, expected, self.results)
                self.assertEqual(r['status'], 'unavailable'); self.assertFalse(r['hardware_access_attempted'])

    def test_lock_loss_refuses_before_bar_and_never_releases_lock(self):
        self.active()
        with patch.object(post.batch, 'checked_remote_lock', side_effect=RuntimeError('wrong owner/token')), \
             patch.object(post, 'capture_remote') as capture:
            r = post.observe(self.job, self.plan_sha, self.results)
        self.assertIsNone(r['selected_parameters']); capture.assert_not_called()

    def test_transport_failure_still_checks_after_and_remains_optional(self):
        self.active(); r, lock, inspect, capture = self.observe(transport_error=ValueError('read unavailable'))
        self.assertIsNone(r['selected_parameters']); self.assertEqual(lock.call_count, 2)
        self.assertEqual(inspect.call_count, 2); self.assertFalse(r['guest_outcome_modified'])
        self.assertFalse(r['sampled_after_normal_driver_exit'])

    def test_malformed_probe_values_never_admitted(self):
        self.active()
        for bad in ('bool', 'allones', 'offset', 'unstable', 'presence', 'device', 'testfile'):
            with self.subTest(bad=bad):
                (self.job / post.DIRECTORY / 'observation.json').unlink(missing_ok=True)
                remote = self.remote(); v = remote['probe']['readLatency']
                if bad == 'bool': v.update(first=True, second=True)
                if bad == 'allones': v.update(first=2**32-1, second=2**32-1)
                if bad == 'offset': v['byte_offset'] = 0
                if bad == 'unstable': v['second'] = 42
                if bad == 'presence': remote['probe']['presence_verified_before_and_after'] = False
                if bad == 'device': remote['device_identity']['bdf'] = 'other'
                if bad == 'testfile': remote['probe']['test_file'] = True
                r, _, inspect, _ = self.observe(remote=remote)
                self.assertIsNone(r['selected_parameters']); self.assertEqual(inspect.call_count, 2)

    def test_each_extended_field_missing_bool_allones_or_changed_refuses(self):
        self.active()
        for field in post.original.REGISTER_MAP:
            for bad in ('missing', 'bool', 'allones', 'changed', 'offset'):
                with self.subTest(field=field, bad=bad):
                    (self.job / post.DIRECTORY / 'observation.json').unlink(missing_ok=True)
                    remote = self.remote(); p = remote['probe']
                    if bad == 'missing': del p[field]
                    if bad == 'bool': p[field].update(first=True, second=True)
                    if bad == 'allones': p[field].update(first=2**32-1, second=2**32-1)
                    if bad == 'changed': p[field]['second'] += 1
                    if bad == 'offset': p[field]['byte_offset'] += 4
                    r, _, inspect, _ = self.observe(remote=remote)
                    self.assertIsNone(r['selected_parameters']); self.assertEqual(inspect.call_count, 2)
        for bad in ('wrong_schema', 'relax_not_bool_domain'):
            (self.job / post.DIRECTORY / 'observation.json').unlink(missing_ok=True)
            remote = self.remote()
            if bad == 'wrong_schema': remote['probe']['schema'] = 'old.two.field.probe'
            else: remote['probe']['relaxFunctionalModel'].update(first=2, second=2)
            r, _, _, _ = self.observe(remote=remote)
            self.assertIsNone(r['selected_parameters'])

    def test_missing_compiled_register_map_is_not_admitted(self):
        receipt = self.build / 'report.json'; r = json.loads(receipt.read_text())
        del r['registers']; receipt.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError, 'five compiled'): self.install()
        self.assertFalse((self.job / post.DIRECTORY).exists())

    def test_bool_offset_in_build_receipt_is_not_an_integer_offset(self):
        receipt = self.build / 'report.json'; r = json.loads(receipt.read_text())
        r['registers']['writeLatency'] = False; receipt.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError, 'five compiled'): self.install()

    def test_nonlaunchable_prototype_and_repeated_hook_refuse(self):
        self.active(prototype=True)
        with patch.object(post.batch, 'inspect_remote', side_effect=AssertionError('must not inspect')):
            r = post.observe(self.job, self.plan_sha, self.results)
        self.assertFalse(r['hardware_access_attempted'])
        with self.assertRaisesRegex(ValueError, 'Fresh installed'): post.observe(self.job, self.plan_sha, self.results)

    def test_remote_program_has_separate_output_and_refuses_unowned_path(self):
        code = "BASE='/tmp/unowned'\nUID=1003\nLOCK={}\nAUTH=''\nBINARY=''\nEXPECTED=''\n" + post.remote_program()
        r = subprocess.run([sys.executable, '-I', '-S', '-'], input=code.encode(), capture_output=True, check=True)
        v = json.loads(r.stdout)
        self.assertFalse(v['hardware_access_started']); self.assertFalse(v['hardware_writes'])
        self.assertIn("base/'memory-observation-postrun-v2'", code)

    def test_used_job_existing_hook_and_stale_hash_cannot_install(self):
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            post.install(self.job, '0'*64, self.build, 'never-contacted')
        w = self.manager / 'workloads/iris-batch.json'; w.write_text(json.dumps({'post_run_hook': 'keep-existing'}))
        self.manifest['prepared_file_sha256'][str(w.relative_to(self.job))] = post.digest(w)
        post.batch.save_manifest(self.job, self.manifest)
        with self.assertRaisesRegex(ValueError, 'silently replaced'): self.install()


class ExtendedAuditTests(unittest.TestCase):
    def test_semantic_audit_impostors_refuse_even_if_envelope_hash_is_rebound(self):
        import memory_observation_extended_v2 as contract
        good = json.loads(contract.AUDIT.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'audit.json'
            for bad in ('read_offset', 'write_offset', 'bool_offset', 'driver', 'pass'):
                with self.subTest(bad=bad):
                    record = copy.deepcopy(good)
                    if bad == 'read_offset': record['registers_readable']['readMaxReqs'] = 8
                    if bad == 'write_offset': record['registers_writable']['relaxFunctionalModel'] = 76
                    if bad == 'bool_offset': record['registers_readable']['writeLatency'] = False
                    if bad == 'driver': record['driver_binary_sha256'] = '0'*64
                    if bad == 'pass': record['pass'] = 1
                    path.write_text(json.dumps(record))
                    with patch.object(contract, 'AUDIT', path), patch.object(contract, 'AUDIT_SHA', post.digest(path)):
                        with self.assertRaisesRegex(ValueError, 'proved'): contract.verify_audit()


if __name__ == '__main__':
    unittest.main()
