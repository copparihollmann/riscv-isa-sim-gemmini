"""Wrapper contract and local PTY checks; never contacts hardware."""
import importlib.util
from pathlib import Path
import types
import unittest

from pty_watchdog_probe import probe

s=importlib.util.spec_from_file_location('watchdog',Path(__file__).parents[1]/'workload_watchdog.py')
watchdog=importlib.util.module_from_spec(s);s.loader.exec_module(watchdog)


class WatchdogTests(unittest.TestCase):
    def test_same_manager_launch_keeps_driver_args_and_foreground_terminal(self):
        original='screen -S fsim0 bash -c "script -c \'stty intr ^] &&  ./FireSim-corigine_mimicturbo_gt +permissive +prog0=exact.elf && stty intr ^c\' uartlog"'
        class Config:
            def get_boot_simulation_command(self,*args,**kwargs):return original
        namespace=types.SimpleNamespace(RuntimeHWConfig=Config);watchdog.install(namespace)
        actual=Config().get_boot_simulation_command()
        self.assertIn('/usr/bin/timeout --foreground --signal=TERM --kill-after=30s 1500 ./FireSim-corigine_mimicturbo_gt',actual)
        self.assertEqual(actual.replace('/usr/bin/timeout --foreground --signal=TERM --kill-after=30s 1500 ',' '),original)

    def test_default_timeout_reproduces_terminal_stop_before_startup(self):
        result=probe(False,False)
        self.assertTrue(any(p['state']=='T' for p in result['observed_processes']))
        self.assertNotIn('DRIVER_READY',result['output'])

    def test_foreground_timeout_allows_real_terminal_initialization(self):
        result=probe(True,False)
        self.assertIn('DRIVER_READY',result['output'])
        self.assertIn('DRIVER_EXIT=0',result['output'])

    def test_foreground_timeout_expires_running_driver(self):
        result=probe(True,True)
        self.assertIn('DRIVER_READY',result['output'])
        self.assertIn('DRIVER_EXIT=124',result['output'])

    def test_unknown_driver_command_is_refused(self):
        class Config:
            def get_boot_simulation_command(self):return 'unknown launch'
        watchdog.install(types.SimpleNamespace(RuntimeHWConfig=Config))
        with self.assertRaisesRegex(RuntimeError,'refuses to guess'):Config().get_boot_simulation_command()

    def test_atoi_overflow_ambiguous_and_invalid_cycle_bounds_are_refused(self):
        for args in ('+max-cycles=100000000000','+max-cycles=0','+max-cycles=-1',
                     '+max-cycles=nope','+max-cycles=12 +max-cycles=34','+max-cycles'):
            with self.subTest(args=args):
                class Config:
                    def get_boot_simulation_command(self):return 'stty intr ^] &&  ./FireSim-corigine_mimicturbo_gt '+args+' && stty intr ^c'
                watchdog.install(types.SimpleNamespace(RuntimeHWConfig=Config))
                with self.assertRaisesRegex(RuntimeError,'signed32'):Config().get_boot_simulation_command()


if __name__=='__main__':unittest.main()
