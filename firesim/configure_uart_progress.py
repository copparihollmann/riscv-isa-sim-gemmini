"""Add UART-progress monitoring to a fresh prepared job before freezing it."""

import json
from pathlib import Path
import shutil

from uart_progress_watchdog import SCHEMA, policy

HERE = Path(__file__).resolve().parent
OLD = (
    "from iris_workload_watchdog import install as _iris_install_workload_watchdog\n"
    "_iris_install_workload_watchdog()\n"
)
NEW = (
    "from iris_uart_progress_watchdog import install as _iris_install_workload_watchdog\n"
    "_iris_install_workload_watchdog(Path(__file__).resolve().with_name('iris-progress.json'))\n"
)


def configure(manager, ordered_cases, *, startup_seconds=6000, inactivity_seconds=6000):
    """Return the source and exact guest roster to pin before launch."""
    config = dict(schema=SCHEMA, startup_seconds=startup_seconds,
                  inactivity_seconds=inactivity_seconds,
                  roster=[[case["id"], case["expected_checksums_by_hart"][0]]
                          for case in ordered_cases])
    policy(config)
    front = manager / "firesim"
    text = front.read_text()
    if text.count(OLD) != 1:
        raise ValueError("Prepared manager must contain exactly one original watchdog")
    updated = text.replace(OLD, "from pathlib import Path\n" + NEW, 1)
    compile(updated, str(front), "exec")
    source = HERE / "uart_progress_watchdog.py"
    shutil.copyfile(source, manager / "iris_uart_progress_watchdog.py")
    (manager / "iris-progress.json").write_text(json.dumps(config, indent=2) + "\n")
    front.write_text(updated)
    return config
