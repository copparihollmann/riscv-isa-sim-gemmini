import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

SPEC = importlib.util.spec_from_file_location('iris_firesim_batch', Path(__file__).parents[1] / 'batch_runner.py')
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.deploy = self.base / 'source' / 'deploy'
        self.deploy.mkdir(parents=True)
        (self.deploy.parent / 'platforms').mkdir()
        self.source = 'env.disable_known_hosts = True\n    env.key_filename = os.path.expanduser("~/firesim.pem")\n'
        (self.deploy / 'firesim').write_text(self.source)
        runtime = {'target_config': {'default_hw_config': 'iris'},
                   'workload': {'workload_name': 'bare.json', 'terminate_on_completion': False},
                   'tracing': {'enable': False},
                   'run_farm': {'recipe_arg_overrides': {'run_farm_hosts_to_use': [{'host.example': 'one_fpgas_spec'}]}}}
        (self.deploy / 'config_runtime.yaml').write_text(yaml.safe_dump(runtime))
        image = self.base / 'image.tar.gz'
        image.write_bytes(b'image fixture')
        (self.deploy / 'config_hwdb.yaml').write_text(yaml.safe_dump({'iris': {'bitstream_tar': image.as_uri()}}))
        self.elf = self.base / 'cases.elf'
        self.elf.write_bytes(b'\x7fELF case fixture')
        self.key = self.base / 'ssh-key'
        self.key.touch()
        self.driver = self.base / 'driver.tar.gz'
        self.driver.write_bytes(b'driver fixture')
        self.output = self.base / 'run'
        self.manager, self.manifest = batch.prepare(self.deploy, self.output, self.elf,
            [{'id': 'smp', 'active_harts': [0, 1, 2]}], self.deploy / 'config_runtime.yaml',
            self.deploy / 'config_hwdb.yaml', self.driver)
        # Hardware lifecycle tests use a synthetic source-independent audit;
        # real preparation's exact archive binding is tested separately.
        self.manifest.update(capture_checklist_frozen=True,observability_audit={'verified':True,'unit_test_only':True})
        self.manifest['launch_authorization_receipt']={'remote_path':'/home/agustin/.iris-model/authorizations/test.json','sha256':'a'*64}
        (self.manager / 'results-workload' / 'uartlog').write_text('Target Cycles Emulated: 500\nScript done [COMMAND_EXIT_CODE="0"]\n')

    def invoke(self, inspections, task_hook=None, capture_hook=None, staging_hook=None, release_hook=None):
        self.tasks = []
        self.locks = []
        def task(manager, output, name, env, timeout, manifest):
            self.tasks.append(name)
            if task_hook:
                task_hook(name)
        if callable(inspections):
            inspect = inspections
        else:
            remaining = iter(inspections)
            latest = None
            def inspect(host):
                nonlocal latest
                latest = next(remaining, latest)
                if latest is None:
                    raise AssertionError('Unexpected inspection')
                return latest
        resolved = 'user agustin\nhostname host.example\nidentityfile ' + str(self.key) + '\n'
        def lock(host, token, acquire, identity=None):
            if acquire is not None:
                self.locks.append(acquire)
            if acquire is False and release_hook:
                release_hook()
        def capture(output, manifest):
            if capture_hook:
                return capture_hook(output, manifest)
            manifest.update(capture={'status':'captured','unit_test_only':True})
            return True
        with patch.dict(os.environ, FIRESIM_SOURCED='1'), \
             patch.object(batch.subprocess, 'check_output', return_value=resolved), \
             patch.object(batch, 'inspect_remote', side_effect=inspect), \
             patch.object(batch, 'bind_launch_authorization', side_effect=lambda host,remote,manifest:remote), \
             patch.object(batch, 'checked_remote_lock', side_effect=lock), \
             patch.object(batch, 'verify_remote_staging', side_effect=staging_hook, return_value={'status':'synthetic-unit-test-staging'}), \
             patch.object(batch, 'create_remote_private_directory', return_value={'uid':1003,'mode':0o700,'unit_test_only':True}), \
             patch.object(batch, 'collect_optional_observability', return_value={'status':'unavailable','unit_test_only':True}), \
             patch.object(batch, 'capture_quiescent_run', side_effect=capture), \
             patch.object(batch, 'run_task', side_effect=task):
            batch.execute(self.manager, self.output, 'host', 'allocation-42', 30, self.manifest)

    @staticmethod
    def idle():
        return {'busy_processes': [], 'device_holders': [], 'inspection_complete': True,
                'inspection_method':'fixed-root-helper',
                'uid': 1003, 'user': 'agustin', 'boot_id': 'boot-test',
                'launch_authorization_verified': True, 'launch_authorization': {'authorization_id': 'allocation-42',
                    'authorization_source':'explicit_current_user_launch_instruction','uid':1003,'user': 'agustin', 'boot_id': 'boot-test',
                    'expires_at_utc': '2099-01-01T00:00:00+00:00'},
                'fpga_db_present': True, 'xdma_devices': ['/dev/xdma0_h2c_0'],
                'fpga_bdfs':['0000:01:00.0'],'pci_inventory':['0000:01:00.0']}

    def test_preparation_preserves_upstream_and_instrumentation(self):
        self.assertEqual((self.deploy / 'firesim').read_text(), self.source)
        prepared = (self.manager / 'firesim').read_text()
        self.assertIn('env.disable_known_hosts = False', prepared)
        self.assertIn('IRIS_FIRESIM_SSH_KEY', prepared)
        runtime = yaml.safe_load((self.manager / 'config_runtime.yaml').read_text())
        self.assertFalse(runtime['tracing']['enable'])
        self.assertTrue(runtime['workload']['terminate_on_completion'])
        self.assertEqual(self.manifest['image']['sha256'], batch.digest(self.base / 'image.tar.gz'))
        self.assertEqual(self.manifest['driver']['sha256'], batch.digest(self.driver))
        self.assertEqual((self.manager / 'workloads/iris-batch/batch.elf').read_bytes(), self.elf.read_bytes())
        workload = json.loads((self.manager / 'workloads/iris-batch.json').read_text())
        self.assertIsNone(workload['common_rootfs'])

    def test_relocated_build_recipe_preserves_existing_makefrag_directory(self):
        makefrag=self.base/'makefrag';makefrag.mkdir()
        recipe=self.deploy/'config_build_recipes.yaml'
        recipe.write_text(yaml.safe_dump({'example':{'TARGET_PROJECT_MAKEFRAG':'../../makefrag'}}))
        manager,manifest=batch.prepare(self.deploy,self.base/'relocated',self.elf,self.manifest['cases'],
            self.deploy/'config_runtime.yaml',self.deploy/'config_hwdb.yaml',self.driver)
        self.assertEqual(yaml.safe_load((manager/'config_build_recipes.yaml').read_text())['example']['TARGET_PROJECT_MAKEFRAG'],str(makefrag))
        self.assertIn(str(recipe),manifest['input_sha256'])

    def test_required_lifecycle(self):
        self.invoke([self.idle(), self.idle()])
        self.assertEqual(self.tasks, ['kill', 'infrasetup', 'runworkload', 'kill'])
        self.assertEqual(self.locks, [True, False])
        self.assertEqual(self.manifest['status'], 'completed_uncertified')

    def test_failed_infrasetup_still_kills(self):
        def fail(name):
            if name == 'infrasetup':
                raise RuntimeError('setup failure')
        with self.assertRaisesRegex(RuntimeError, 'setup failure'):
            self.invoke([self.idle(), self.idle()], fail)
        self.assertEqual(self.tasks, ['kill', 'infrasetup', 'kill'])
        self.assertEqual(self.locks, [True, False])
        self.assertEqual(self.manifest['status'], 'failed')

    def test_occupied_fpga_never_killed(self):
        busy = dict(self.idle(), busy_processes=['someone 123 FireSim'])
        with self.assertRaisesRegex(RuntimeError, 'occupied'):
            self.invoke([busy])
        self.assertEqual(self.tasks, [])
        self.assertEqual(self.locks, [])

    def test_occupancy_race_releases_lock_without_killing(self):
        busy = dict(self.idle(), busy_processes=['someone 123 FireSim'])
        with self.assertRaisesRegex(RuntimeError, 'occupied'):
            self.invoke([self.idle(), busy])
        self.assertEqual(self.tasks, [])
        self.assertEqual(self.locks, [True, False])
        self.assertEqual(self.manifest['status'], 'failed')

    def test_incomplete_visibility_never_kills(self):
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            self.invoke([dict(self.idle(), inspection_complete=False)])
        self.assertEqual(self.tasks, [])
        self.assertEqual(self.locks, [])

    def test_complete_unprivileged_scan_cannot_replace_pinned_root_inspector(self):
        with self.assertRaisesRegex(RuntimeError,'root inspector'):
            self.invoke([dict(self.idle(),inspection_method='complete-unprivileged')])
        self.assertEqual(self.tasks,[]);self.assertEqual(self.locks,[])

    def test_operator_reservation_json_is_not_a_prerequisite(self):
        report=self.idle();report.update(allocation_trusted=False,allocation_error='absent')
        self.invoke([report])
        self.assertEqual(self.tasks,['kill','infrasetup','runworkload','kill'])

    def test_unloaded_xdma_does_not_prevent_owned_setup_or_cleanup(self):
        self.invoke([dict(self.idle(),xdma_devices=[])])
        self.assertEqual(self.tasks,['kill','infrasetup','runworkload','kill'])
        with self.assertRaisesRegex(RuntimeError,'PCIe presence'):
            self.invoke([dict(self.idle(),xdma_devices=[],pci_inventory=[])])

    def test_untrusted_expired_and_rebooted_authorizations_never_kill(self):
        for change in ({'launch_authorization_verified': False}, {'boot_id': 'new-boot'},
                       {'launch_authorization': dict(self.idle()['launch_authorization'], expires_at_utc='2000-01-01T00:00:00+00:00')},
                       {'launch_authorization': dict(self.idle()['launch_authorization'], authorization_id='someone-else')},
                       {'launch_authorization': dict(self.idle()['launch_authorization'], user='other')},
                       {'launch_authorization': dict(self.idle()['launch_authorization'], uid=0)},
                       {'launch_authorization': dict(self.idle()['launch_authorization'], authorization_source='unconfirmed_Ethan_allocation')}):
            with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, 'allocation'):
                self.invoke([dict(self.idle(), **change)])
            self.assertEqual(self.tasks, [])

    def test_foreign_job_appearing_after_initial_kill_blocks_setup_and_cleanup(self):
        busy = dict(self.idle(), device_holders=[{'uid':1003, 'cwd':'/some/other/run', 'pid':123}])
        with self.assertRaisesRegex(RuntimeError, 'occupied'):
            self.invoke([self.idle(), self.idle(), busy])
        self.assertEqual(self.tasks, ['kill'])
        self.assertEqual(self.locks, [True])
        self.assertTrue(self.manifest['lock_retained_for_operator'])

    def test_visibility_loss_during_run_withholds_cleanup_and_retains_lock(self):
        uncertain = dict(self.idle(), inspection_complete=False)
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            self.invoke([self.idle(), self.idle(), self.idle(), self.idle(), uncertain])
        self.assertEqual(self.tasks, ['kill', 'infrasetup', 'runworkload'])
        self.assertEqual(self.locks, [True])

    def test_cleanup_allows_only_owned_uid_and_private_directory(self):
        def inspect(host):
            report = self.idle()
            if self.tasks == ['kill', 'infrasetup', 'runworkload']:
                report['device_holders'] = [{'pid':456, 'uid':1003,
                    'cwd': self.manifest['remote_simulation_dir'] + '/sim_slot_0'}]
            return report
        self.invoke(inspect)
        self.assertEqual(self.tasks, ['kill', 'infrasetup', 'runworkload', 'kill'])
        self.assertEqual(self.locks, [True, False])
        remote = dict(self.idle(), device_holders=[{'uid':0, 'cwd':self.manifest['remote_simulation_dir']}])
        with self.assertRaisesRegex(RuntimeError, 'occupied'):
            batch.require_safe_remote(remote, 'allocation-42', 'boot-test', self.manifest['remote_simulation_dir'])

    def test_missing_driver_fails_before_ssh(self):
        self.manifest['driver']['sha256'] = None
        with self.assertRaisesRegex(RuntimeError, 'driver-tar'):
            self.invoke([])
        self.assertEqual(self.tasks, [])

    def test_cases_require_distinct_identifiers_and_harts(self):
        for cases in ([], [{'id': 'a', 'active_harts': [0, 0]}],
                      [{'id': 'a', 'active_harts': [False]}],
                      [{'id': 'a', 'active_harts': [0]}, {'id': 'a', 'active_harts': [1]}]):
            with self.assertRaises(ValueError):
                batch.validate_cases(cases)

    def test_region_counters_and_provenance(self):
        record = {'case_id': 'smp', 'region': 'gemm', 'hart': 1, 'start_cycle': 100,
                  'end_cycle': 180, 'instret_delta': 14, 'checksum': 42}
        console = 'IRIS_REGION ' + json.dumps(record)
        parsed = batch.parse_regions(console, self.manifest['cases'], 'elfhash', 'imagehash')
        self.assertEqual(parsed[0]['cycles'], 80)
        self.assertEqual(parsed[0]['elf_sha256'], 'elfhash')
        self.assertEqual(parsed[0]['image_sha256'], 'imagehash')
        with self.assertRaisesRegex(ValueError, 'Missing target regions'):
            batch.parse_regions(console, self.manifest['cases'], 'elfhash', 'imagehash', True)
        with self.assertRaisesRegex(ValueError, 'Duplicate region'):
            batch.parse_regions(console + '\n' + console, self.manifest['cases'], 'elfhash', 'imagehash')

    def test_reject_wrap_bad_hart_and_bool_counter(self):
        record = {'case_id': 'smp', 'region': 'gemm', 'hart': 0, 'start_cycle': 100,
                  'end_cycle': 180, 'instret_delta': 14, 'checksum': 42}
        for changes in ({'end_cycle': 50}, {'hart': 7}, {'start_cycle': True}, {'checksum': -1}):
            with self.assertRaises(ValueError):
                batch.parse_regions('IRIS_REGION ' + json.dumps(dict(record, **changes)),
                                    self.manifest['cases'], 'elfhash', 'imagehash')

    def test_guest_region_correctness_is_required_when_reported(self):
        record = {'case_id': 'smp', 'region': 'gemm', 'hart': 0, 'start_cycle': 100,
                  'end_cycle': 180, 'instret_delta': 14, 'checksum': 42}
        for change in ({'pass': False}, {'pass': 1}, {'expected_checksum': 41},
                       {'expected_checksum': True}):
            with self.assertRaises(ValueError):
                batch.parse_regions('IRIS_REGION ' + json.dumps(dict(record, **change)),
                                    self.manifest['cases'], 'elfhash', 'imagehash')

    def test_independent_host_golden_defeats_self_consistent_guest_result(self):
        cases=[{'id':'smp','active_harts':[0],'region':'kernel','expected_checksums_by_hart':[42,43,44]}]
        record={'case_id':'smp','region':'kernel','hart':0,'start_cycle':10,'end_cycle':20,
                'instret_delta':3,'checksum':99,'expected_checksum':99,'pass':True}
        with self.assertRaisesRegex(ValueError,'independent host checksum'):
            batch.parse_regions('IRIS_REGION '+json.dumps(record),cases,'elf','image',require_goldens=True)
        record.update(checksum=42,expected_checksum=42)
        parsed=batch.parse_regions('IRIS_REGION '+json.dumps(record),cases,'elf','image',require_goldens=True)
        self.assertTrue(parsed[0]['independent_checksum_validated'])
        record['region']='different'
        with self.assertRaisesRegex(ValueError,'host case identity'):
            batch.parse_regions('IRIS_REGION '+json.dumps(record),cases,'elf','image',require_goldens=True)

    def test_required_goldens_reject_unknown_and_incomplete_evidence(self):
        with self.assertRaisesRegex(ValueError,'Independent host checksums'):
            batch.validate_cases([{'id':'smp','active_harts':[0]}],require_goldens=True)
        for values in ([True],[42.0],[],[-1],[2**64]):
            with self.subTest(values=values),self.assertRaises(ValueError):
                batch.validate_cases([{'id':'smp','active_harts':[0],'expected_checksums_by_hart':values}],True)
        cases=[{'id':'smp','active_harts':[0],'expected_checksums_by_hart':[42]}]
        with self.assertRaisesRegex(ValueError,'Missing target regions'):
            batch.parse_regions('',cases,'elf','image',require_goldens=True)

    def prepared_verifier(self):
        spec=importlib.util.spec_from_file_location('iris_prepared',Path(__file__).parents[1]/'run_prepared.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'batch_runner':batch}):spec.loader.exec_module(module)
        return module

    def test_prepared_job_verifies_copied_payload_without_network(self):
        verifier=self.prepared_verifier()
        with self.assertRaisesRegex(ValueError,'old results'):verifier.verify(self.output)
        (self.manager/'results-workload/uartlog').unlink()
        self.assertEqual(verifier.verify(self.output)['status'],'prepared')
        (self.manager/'workloads/iris-batch/batch.elf').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Prepared file changed'):verifier.verify(self.output)

    def test_prepared_job_cannot_change_hwdb_or_retry_old_execution(self):
        verifier=self.prepared_verifier();(self.manager/'results-workload/uartlog').unlink()
        manifest=json.loads((self.output/'run.json').read_text());manifest['commands']=[{'task':'kill'}]
        batch.save_manifest(self.output,manifest)
        with self.assertRaisesRegex(ValueError,'fresh prepared'):verifier.verify(self.output)
        manifest['commands']=[];batch.save_manifest(self.output,manifest)
        (self.manager/'config_hwdb.yaml').write_text('changed')
        with self.assertRaisesRegex(ValueError,'Prepared file changed'):verifier.verify(self.output)

    def test_nonzero_guest_exit_fails_and_still_cleans_up(self):
        (self.manager / 'results-workload' / 'uartlog').write_text('Script done [COMMAND_EXIT_CODE="134"]\n')
        with self.assertRaisesRegex(RuntimeError, 'nonzero process exit'):
            self.invoke([self.idle(), self.idle()])
        self.assertEqual(self.tasks, ['kill', 'infrasetup', 'runworkload', 'kill'])
        self.assertEqual(self.manifest['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
