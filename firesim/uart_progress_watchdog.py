"""Watch successful guest tests inside the managed foreground FireSim session."""

import base64
import functools
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

SCHEMA = "iris.uart_progress_watchdog.v1"
START = re.compile(rb"IRIS_PROGRESS v1 START ([1-9][0-9]*)")
DONE = re.compile(rb"IRIS_PROGRESS v1 DONE ([1-9][0-9]*) ([a-zA-Z0-9_-]{1,80}) ([0-9]{1,20})")
CASE_ID = re.compile(r"[a-zA-Z0-9_-]{1,80}")
NEEDLE = "&&  ./FireSim-corigine_mimicturbo_gt "
UART_PATH = Path("uartlog")
MAX_READ = 65536
POLL_SECONDS = 1
EXIT_DRAIN_SECONDS = 5


def policy(config):
    if config.get("schema") != SCHEMA:
        raise ValueError("UART watchdog protocol differs")
    for key in ("startup_seconds", "inactivity_seconds"):
        if type(config.get(key)) is not int or not 1 <= config[key] <= 21600:
            raise ValueError(f"Invalid watchdog interval: {key}")
    rows = config.get("roster")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError("Expected a finite guest roster")
    pairs = []
    for row in rows:
        key, checksum = row
        if (not isinstance(key, str) or not CASE_ID.fullmatch(key)
                or type(checksum) is not int or not 0 <= checksum < 2**64):
            raise ValueError("Invalid test identity or checksum")
        pairs.append((key.encode("ascii"), checksum))
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("Duplicate test ID")
    return tuple(pairs)


class Progress:
    def __init__(self, config, now):
        self.roster = policy(config)
        self.startup = config["startup_seconds"]
        self.inactivity = config["inactivity_seconds"]
        self.last = now
        self.started = False
        self.completed = 0

    def observe(self, line, now):
        line = line.rstrip(b"\r")
        if not self.started:
            match = START.fullmatch(line)
            if match and match[1] == str(len(self.roster)).encode():
                self.started = True
                self.last = now
                return True
            return False
        if self.completed == len(self.roster):
            return False
        match = DONE.fullmatch(line)
        if match and match[1] == str(self.completed + 1).encode():
            if (match[2], int(match[3])) == self.roster[self.completed]:
                self.completed += 1
                self.last = now
                return True
        return False

    def expiry(self, now):
        if not self.started and now - self.last >= self.startup:
            return "startup"
        if self.started and self.completed < len(self.roster) and now - self.last >= self.inactivity:
            return "no_valid_test_completion"
        return None


class UART:
    """Incrementally read the actual session log, keeping at most one small line."""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.identity = None
        self.pending = b""
        self.discard = False

    def poll(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            if self.identity is not None:
                raise RuntimeError("UART log disappeared")
            return
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise RuntimeError("UART is not an owned regular file")
            identity = (info.st_dev, info.st_ino)
            if self.identity is not None and (self.identity != identity or info.st_size < self.offset):
                raise RuntimeError("UART log was replaced or truncated")
            self.identity = identity
            stream.seek(self.offset)
            chunk = stream.read(MAX_READ)
            self.offset += len(chunk)
        pieces = chunk.split(b"\n")
        for piece in pieces[:-1]:
            if not self.discard and len(self.pending) + len(piece) <= 512:
                yield self.pending + piece
            self.pending = b""
            self.discard = False
        tail = pieces[-1]
        if not self.discard and len(self.pending) + len(tail) <= 512:
            self.pending += tail
        else:
            self.discard = True
            self.pending = b""


def log(event, monitor, **extra):
    print("IRIS_WATCHDOG " + json.dumps(dict(
        event=event, completed=monitor.completed, tests=len(monitor.roster),
        **extra), sort_keys=True), file=sys.stderr, flush=True)


def terminate_owned_child(process):
    if process.poll() is not None:
        return process.returncode
    process.terminate()
    try:
        return process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait()


def watch(config, command):
    if not command or command[0] != "./FireSim-corigine_mimicturbo_gt":
        raise ValueError("Unexpected managed driver command")
    monitor = Progress(config, time.monotonic())
    uart = UART(UART_PATH)
    process = subprocess.Popen(command)
    try:
        while True:
            now = time.monotonic()
            for line in uart.poll():
                monitor.observe(line, now)
            status = process.poll()
            if status is not None:
                if status == 0:
                    drain_deadline = now + EXIT_DRAIN_SECONDS
                    while monitor.completed != len(monitor.roster) and time.monotonic() < drain_deadline:
                        for line in uart.poll():
                            monitor.observe(line, time.monotonic())
                        if monitor.completed != len(monitor.roster):
                            time.sleep(0.1)
                    if monitor.completed != len(monitor.roster):
                        log("incomplete_progress_at_driver_exit", monitor)
                        return 125
                return status if status >= 0 else 128 - status
            reason = monitor.expiry(now)
            if reason:
                next_case = (monitor.roster[monitor.completed][0].decode()
                             if monitor.completed < len(monitor.roster) else None)
                log("expired", monitor, reason=reason, next_case=next_case,
                    seconds_since_progress=round(now - monitor.last, 3))
                terminate_owned_child(process)
                return 124
            time.sleep(POLL_SECONDS)
    except BaseException:
        terminate_owned_child(process)
        raise


def wrap_driver_command(text, payload):
    """Embed Python in the existing screen/bash/script command without a file transfer."""
    if text.count(NEEDLE) != 1:
        raise RuntimeError("Managed non-AWS FireSim command differs")
    if "+max-cycles" in text:
        raise RuntimeError("UART-progress workloads do not use a target cycle cap")
    # The original template places script's single-quoted command inside a
    # double-quoted bash argument. Escape the inner Python string at both levels.
    inner = '"import base64;exec(base64.b64decode(\\"' + payload + '\\"))"'
    outer = inner.replace("\\", "\\\\").replace('"', '\\"')
    return text.replace(NEEDLE, f"&& /usr/bin/python3 -I -S -c {outer} " +
                        "./FireSim-corigine_mimicturbo_gt ", 1)


def install(config_path, module=None):
    if module is None:
        import runtools.runtime_config as module
    config = json.loads(Path(config_path).read_text())
    policy(config)
    # In the remote interpreter __name__ is __main__; the sealed configuration
    # is injected through a literal assignment before the unchanged source.
    source = Path(__file__).read_bytes()
    payload = base64.b64encode(b"REMOTE_POLICY = " + repr(config).encode() + b"\n" + source).decode()
    owner = module.RuntimeHWConfig
    if getattr(owner, "_iris_workload_watchdog", False):
        raise RuntimeError("Workload watchdog already installed")
    original = owner.get_boot_simulation_command

    @functools.wraps(original)
    def command(*args, **kwargs):
        return wrap_driver_command(original(*args, **kwargs), payload)

    owner.get_boot_simulation_command = command
    owner._iris_workload_watchdog = True


if __name__ == "__main__":
    raise SystemExit(watch(REMOTE_POLICY, sys.argv[1:]))
