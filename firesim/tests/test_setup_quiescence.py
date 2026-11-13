"""Idle-timeout waiting never treats a live programmer as launch permission."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import test_batch_runner as fixtures

batch=fixtures.batch


class QuiescenceTests(unittest.TestCase):
    def test_only_waits_then_returns_fresh_complete_idle_inspection(self):
        idle=fixtures.BatchTests.idle();busy=dict(idle,busy_processes=[{'comm':'hw_server','uid':0,
            'cwd':'/home/agustin','command':'/tools/xilinx/2026.1/Vivado_Lab/bin/unwrapped/lnx64.o/hw_server -d -I20 -s TCP:127.0.0.1:3121',
            'pid':7,'start_time_ticks':12}])
        with tempfile.TemporaryDirectory() as temporary:
            manifest={'lock_token':'a'*32}
            with patch.object(batch.time,'sleep') as sleep,patch.object(batch,'checked_remote_lock')as lock, \
                 patch.object(batch,'inspect_remote',return_value=idle), \
                 patch.object(batch,'bind_launch_authorization',side_effect=lambda h,r,m:r):
                result=batch.await_setup_quiescence('not-contacted',busy,manifest,Path(temporary),{'boot_id':'boot-test'})
            self.assertIs(result,idle);sleep.assert_called_once_with(2);lock.assert_called_once()
            self.assertEqual(manifest['setup_quiescence_wait'],[busy])

    def test_foreign_or_uncertain_activity_never_gets_wait_exception(self):
        idle=fixtures.BatchTests.idle()
        for report in [dict(idle,busy_processes=[{'comm':'hw_server','uid':1004}]),
                       dict(idle,inspection_complete=False),dict(idle,device_holders=[{'pid':9}])]:
            with tempfile.TemporaryDirectory() as temporary,patch.object(batch.time,'sleep') as sleep:
                result=batch.await_setup_quiescence('not-contacted',report,{'lock_token':'a'*32},Path(temporary),{'boot_id':'boot-test'})
                self.assertIs(result,report);sleep.assert_not_called()


if __name__=='__main__':unittest.main()
