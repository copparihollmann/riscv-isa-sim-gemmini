import base64
import datetime as dt
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_progress_prepared as phases
import uart_progress_watchdog as watch


def config(start=1200, inactivity=6000):
    return dict(schema=watch.SCHEMA, startup_seconds=start, inactivity_seconds=inactivity,
                roster=[["p0_c0_r0", 11], ["p0_c0_r1", 22]])


class ProgressWatchdog(unittest.TestCase):
    def test_progress_extends_past_a_whole_workload_timeout(self):
        p = watch.Progress(config(), 0)
        self.assertTrue(p.observe(b"IRIS_PROGRESS v1 START 2\r\r", 1000))
        self.assertTrue(p.observe(b"IRIS_PROGRESS v1 DONE 1 p0_c0_r0 11", 6900))
        self.assertIsNone(p.expiry(12000))
        self.assertTrue(p.observe(b"IRIS_PROGRESS v1 DONE 2 p0_c0_r1 22", 12800))
        self.assertIsNone(p.expiry(999999))  # completed export uses the allocation ceiling

    def test_uart_chatter_and_bad_markers_do_not_extend(self):
        p = watch.Progress(config(), 0)
        self.assertTrue(p.observe(b"IRIS_PROGRESS v1 START 2", 10))
        self.assertTrue(p.observe(b"IRIS_PROGRESS v1 DONE 1 p0_c0_r0 11", 100))
        for line in (b"IRIS_PROGRESS v1 START 2", b"Heartbeat tick 2",
                     b"IRIS_PROGRESS v1 DONE 1 p0_c0_r0 11",
                     b"IRIS_PROGRESS v1 DONE 2 p0_c0_r1 21",
                     b"IRIS_PROGRESS v1 DONE 3 p0_c0_r1 22",
                     b"IRIS_PROGRESS v1 DONE 2 p0_c0_r0 22"):
            self.assertFalse(p.observe(line, 6000))
        self.assertEqual(p.expiry(6100), "no_valid_test_completion")

    def test_initial_loader_has_its_own_bound(self):
        p = watch.Progress(config(), 0)
        self.assertFalse(p.observe(b"IRIS_PROGRESS v1 START 4", 1000))
        self.assertEqual(p.expiry(1200), "startup")

    def test_partial_uart_line_and_log_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"uartlog"
            uart = watch.UART(path)
            self.assertEqual(list(uart.poll()), [])
            path.write_bytes(b"junk\nIRIS_PROGRESS v1")
            self.assertEqual(list(uart.poll()), [b"junk"])
            with path.open("ab") as stream:
                stream.write(b" START 2\r\n")
            self.assertEqual(list(uart.poll()), [b"IRIS_PROGRESS v1 START 2\r"])
            path.rename(path.with_suffix(".old"))
            path.write_bytes(b"replacement")
            with self.assertRaises(RuntimeError):
                list(uart.poll())

    def test_real_script_terminal_and_exit_codes(self):
        source = Path(watch.__file__).read_bytes()
        fixtures = (
            (0, "IRIS_PROGRESS v1 START 2\nIRIS_PROGRESS v1 DONE 1 p0_c0_r0 11\n"
                "IRIS_PROGRESS v1 DONE 2 p0_c0_r1 22\n", ""),
            (124, "IRIS_PROGRESS v1 START 2\nIRIS_PROGRESS v1 DONE 1 p0_c0_r0 11\n", "sleep 4"),
            (125, "IRIS_PROGRESS v1 START 2\n", ""),
        )
        for status, uart, action in fixtures:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stub = root/"FireSim-corigine_mimicturbo_gt"
                stub.write_text("#!/bin/sh\nprintf '%s' " + shlex.quote(uart) + "\n" + action + "\n")
                stub.chmod(0o700)
                payload = base64.b64encode(
                    b"REMOTE_POLICY = " + repr(config(3, 1)).encode() + b"\n" + source
                ).decode()
                original = (
                    'screen -S mock -d -m bash -c "script -q -e -f -c '
                    "'stty intr ^] &&  ./FireSim-corigine_mimicturbo_gt "
                    "+permissive fake && stty intr ^c' uartlog" + '"; sleep 1'
                )
                command = shlex.split(watch.wrap_driver_command(original, payload).removesuffix("; sleep 1"))
                result = subprocess.run(command[5:], cwd=root, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, status, result.stdout[-300:])

    def test_manager_ceiling_uses_allocation_and_leaves_cleanup(self):
        policy = dict(schema=phases.SCHEMA,
                      task_seconds=dict(kill=480,infrasetup=900,runworkload="allocation_remaining",cleanup=180),
                      capture_allowance_seconds=1200,safety_margin_seconds=600,cleanup_grace_seconds=30)
        epoch = dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc)
        authorization = dict(authorization_id="current",
                             expires_at_utc=(epoch+dt.timedelta(seconds=20000)).isoformat())
        m = dict(active_phase="runworkload", phase_timeouts=policy, authorization_id="current",
                 remote=dict(launch_authorization_verified=True,launch_authorization=authorization))
        bound = phases.bounded_task(lambda _, __, ___, ____, timeout, _____: timeout,
                                    policy,"sha",now=lambda:epoch)
        self.assertEqual(bound(None,None,"runworkload",None,1,m), 18019)
        self.assertEqual(m["phase_budget_checks"][-1]["workload_ceiling"], "exclusive_allocation")


if __name__ == "__main__":
    unittest.main()
