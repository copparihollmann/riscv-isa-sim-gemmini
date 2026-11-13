"""Run a prepared UART-progress job through the stock FireSim lifecycle."""

import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

SCHEMA = "iris.progress_phase_bounds.v1"
TASKS = ("kill", "infrasetup", "runworkload", "cleanup")
RESERVE = ("capture_allowance_seconds", "safety_margin_seconds", "cleanup_grace_seconds")


def need(value, message):
    if not value:
        raise ValueError(message)


def validate(policy):
    need(isinstance(policy, dict) and policy.get("schema") == SCHEMA, "Expected progress phase policy")
    need(set(policy) == {"schema", "task_seconds", *RESERVE}, "Unknown phase policy fields")
    bounds = policy["task_seconds"]
    need(set(bounds) == set(TASKS) and bounds["runworkload"] == "allocation_remaining",
         "Runworkload must use the current allocation")
    for key, cap in (("kill", 480), ("infrasetup", 900), ("cleanup", 180)):
        need(type(bounds[key]) is int and 0 < bounds[key] <= cap, f"Invalid {key} bound")
    for key, minimum in zip(RESERVE, (1200, 600, 30)):
        need(type(policy[key]) is int and policy[key] >= minimum, f"Insufficient {key}")
    return bounds


def bounded_task(original, policy, source_sha256, now=None):
    bounds = validate(policy)
    now = now or (lambda: dt.datetime.now(dt.timezone.utc))

    def run(manager, output, task, env, timeout, manifest):
        stage = manifest.get("active_phase")
        need(stage in TASKS and task == ("kill" if stage == "cleanup" else stage),
             "Unexpected managed phase")
        need(manifest.get("phase_timeouts") == policy, "Frozen phase policy changed")
        remote = manifest.get("remote", {})
        need(remote.get("launch_authorization_verified") is True, "Stock verified authorization required")
        authorization = remote["launch_authorization"]
        need(authorization["authorization_id"] == manifest.get("authorization_id"),
             "Authorization changed")
        expiry = dt.datetime.fromisoformat(authorization["expires_at_utc"])
        need(expiry.utcoffset() is not None, "Timezone-aware authorization expiry required")
        remaining = (expiry - now()).total_seconds()
        cleanup = bounds["cleanup"]
        if stage == "cleanup":
            chosen = cleanup
            reserve = cleanup + policy["cleanup_grace_seconds"]
        else:
            after = cleanup + policy["capture_allowance_seconds"] + policy["safety_margin_seconds"]
            if stage == "runworkload":
                chosen = int(remaining - after) - 1
                need(chosen > 0, "No authorized workload time remains")
                reserve = chosen + after
            else:
                chosen = bounds[stage]
                reserve = chosen + after + (bounds["infrasetup"] if stage == "kill" else 0)
        need(remaining > reserve, "Insufficient authorization for remaining phases")
        manifest.setdefault("phase_budget_checks", []).append(dict(
            phase=stage, timeout_seconds=chosen, required_remaining_seconds=reserve,
            observed_remaining_seconds=remaining, adapter_sha256=source_sha256,
            workload_ceiling="exclusive_allocation" if stage == "runworkload" else None))
        return original(manager, output, task, env, chosen, manifest)

    return run


def main():
    import batch_runner
    import run_prepared
    if "--execute" not in sys.argv:
        return run_prepared.main()
    job = Path(sys.argv[1]).resolve()
    manifest = json.loads((job / "run.json").read_text())
    source = Path(__file__).resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    need(manifest.get("input_sha256", {}).get(str(source)) == digest,
         "Progress phase runner was not frozen with this job")
    policy = manifest["phase_timeouts"]
    original = batch_runner.run_task
    batch_runner.run_task = bounded_task(original, policy, digest)
    try:
        return run_prepared.main()
    finally:
        batch_runner.run_task = original


if __name__ == "__main__":
    raise SystemExit(main())
