"""No FireSim imports, SSH, helper execution or device access."""
import importlib.util
import io
import json
from pathlib import Path
import types
import unittest
from contextlib import redirect_stdout

spec = importlib.util.spec_from_file_location('setup_observer', Path(__file__).parents[1] / 'setup_phase_observer.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class ObserverTests(unittest.TestCase):
    def fixture(self):
        calls = []
        module = types.SimpleNamespace()
        def run(command, **kwargs):
            calls.append(('run', command, kwargs))
            if kwargs.get('fail'):
                raise ValueError('original error')
            return types.SimpleNamespace(return_code=0)
        def transfer(*args, **kwargs):
            calls.append(('transfer', args, kwargs)); return 'transfer result'
        class Base:
            def copy_sim_slot_infrastructure(self, *args, **kwargs):
                return module.rsync_project(local_dir='image', remote_dir='private')
            def extract_driver_tarball(self, *args, **kwargs): return 'extracted'
        class Alveo(Base):
            def unload_xdma(self): return 'unloaded'
            def flash_fpgas(self, **kwargs):
                module.rsync_project(local_dir='scripts', remote_dir='private')
                return module.run('/usr/local/bin/firesim-fpga-util.py --bitstream-map /private/map --fpga-db /fixed/db', **kwargs)
            def load_xdma(self): return 'loaded'
            def change_pcie_perms(self): return 'permissions'
        module.InstanceDeployManager = Base
        module.XilinxAlveoInstanceDeployManager = Alveo
        module.run, module.rsync_project = run, transfer
        return module, Alveo(), calls

    def test_preserves_calls_returns_and_nested_timings(self):
        module, target, calls = self.fixture()
        output = io.StringIO()
        observer.install(module)
        with redirect_stdout(output):
            self.assertEqual(target.copy_sim_slot_infrastructure(3, 'uri'), 'transfer result')
            self.assertEqual(target.flash_fpgas().return_code, 0)
        self.assertEqual([c[0] for c in calls], ['transfer', 'transfer', 'run'])
        report = observer.summarize(output.getvalue())
        self.assertEqual(len(report['records']), 5)
        self.assertEqual(report['partial_event_ids'], [])
        self.assertIsNotNone(report['rsync_host_seconds'])
        self.assertIsNotNone(report['programming_helper_host_seconds'])
        for r in report['records']:
            if r['phase'] in ('rsync_transfer', 'programming_helper'):
                self.assertIsNotNone(r['parent_id'])

    def test_original_exception_propagates_and_timings_report_failure(self):
        module, target, calls = self.fixture()
        observer.install(module); output = io.StringIO()
        with redirect_stdout(output), self.assertRaisesRegex(ValueError, 'original error'):
            target.flash_fpgas(fail=True)
        report = observer.summarize(output.getvalue())
        self.assertIsNone(report['programming_helper_host_seconds'])
        self.assertEqual(calls[-1][2], {'fail': True})
        self.assertEqual(report['records'][-1]['completion']['error_type'], 'ValueError')

    def test_changed_source_contract_refuses_before_any_rebinding(self):
        module, target, calls = self.fixture()
        del module.XilinxAlveoInstanceDeployManager.load_xdma
        original = module.InstanceDeployManager.copy_sim_slot_infrastructure
        with self.assertRaisesRegex(RuntimeError, 'contract changed'):
            observer.install(module)
        self.assertIs(module.InstanceDeployManager.copy_sim_slot_infrastructure, original)
        self.assertEqual(calls, [])

    def test_programming_is_exact_fixed_command_match(self):
        valid = '/usr/local/bin/firesim-fpga-util.py --bitstream-map /x --fpga-db /y'
        self.assertTrue(observer._program_command(valid))
        for x in [valid + '; touch x', 'echo ' + valid, valid.replace('/usr/local/bin/', './'), valid + ' --other', None]:
            self.assertFalse(observer._program_command(x))

    def test_missing_partial_or_corrupt_timings_do_not_invent_measurements(self):
        self.assertIsNone(observer.summarize('ordinary log')['rsync_host_seconds'])
        begin = {'schema':'iris.host_setup_phase.v1', 'id':0, 'parent_id':None, 'phase':'rsync_transfer',
                 'start_monotonic_ns':1, 'started_utc':'x', 'event':'begin'}
        text = observer.PREFIX + json.dumps(begin)
        self.assertEqual(observer.summarize(text)['partial_event_ids'], [0])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            observer.summarize(text + '\n' + text)
        end = dict(begin, event='end', host_elapsed_ns=-1, status='returned')
        with self.assertRaisesRegex(ValueError, 'duration'):
            observer.summarize(text + '\n' + observer.PREFIX + json.dumps(end))


if __name__ == '__main__':
    unittest.main()
