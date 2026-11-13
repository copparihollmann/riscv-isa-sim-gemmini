"""Local terminal-job-control reproduction; no remote commands or hardware."""
import errno
import json
import os
from pathlib import Path
import pty
import select
import shlex
import signal
import time


def session_processes(session):
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().split(') ', 1)[1].split()
            if int(fields[3]) == session and proc.stat().st_uid == os.getuid():
                found.append({'pid': int(proc.name), 'state': fields[0],
                              'pgrp': int(fields[2]), 'foreground_pgrp': int(fields[5])})
        except (OSError, ValueError):
            pass
    return found


def probe(foreground, expire):
    driver = "import termios,time; a=termios.tcgetattr(0); termios.tcsetattr(0,termios.TCSANOW,a); print('DRIVER_READY',flush=True); time.sleep(" + ('10' if expire else '0') + ')'
    command = ('stty intr ^] && /usr/bin/timeout '
               + ('--foreground ' if foreground else '')
               + '--signal=TERM --kill-after=1s 1s python3 -c '
               + shlex.quote(driver) + '; code=$?; echo DRIVER_EXIT=$code; exit $code')
    pid, master = pty.fork()
    if pid == 0:
        os.execl('/bin/bash', 'bash', '-c', command)
    output = b''
    deadline = time.monotonic() + 3
    status = None
    observed = []
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output += chunk
            observed = session_processes(pid)
            if status is None:
                got, value = os.waitpid(pid, os.WNOHANG)
                if got:
                    status = value
                    # Drain the PTY through EOF; exit can precede delivery of
                    # its final output to this reader.
            if not foreground and any(p['state'] == 'T' for p in observed):
                break
        observed = session_processes(pid) or observed
    finally:
        # Exact private local PTY session only; never name-based killing.
        for proc in session_processes(pid):
            try:
                os.kill(proc['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass
        os.close(master)
        if status is None:
            try:
                _, status = os.waitpid(pid, 0)
            except ChildProcessError:
                pass
    return {'foreground': foreground, 'expiry_test': expire,
            'output': output.decode(errors='replace'), 'observed_processes': observed,
            'wait_status': status}


if __name__ == '__main__':
    rows = [probe(False, False), probe(True, False), probe(True, True)]
    assert any(p['state'] == 'T' for p in rows[0]['observed_processes']), rows[0]
    assert 'DRIVER_READY' not in rows[0]['output'], rows[0]
    assert 'DRIVER_READY' in rows[1]['output'] and 'DRIVER_EXIT=0' in rows[1]['output'], rows[1]
    assert 'DRIVER_READY' in rows[2]['output'] and 'DRIVER_EXIT=124' in rows[2]['output'], rows[2]
    destination = Path(__file__).with_name('pty-probe-results.json')
    destination.write_text(json.dumps({'passed': True, 'hardware_contacted': False, 'cases': rows}, indent=2) + '\n')
    print(destination)
