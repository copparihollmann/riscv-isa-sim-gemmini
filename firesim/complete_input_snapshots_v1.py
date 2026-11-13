#!/usr/bin/env python3
"""Complete a NEW unused job's local byte snapshots after optional hook install.

Hardware-free. Never changes the runner, hook plan, runtime or an executed job.
The exact preceding prepared manifest remains in the job's archived evidence.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import shutil

try:
    from firesim import batch_runner as batch
    from firesim import run_prepared
except ModuleNotFoundError:
    import batch_runner as batch
    import run_prepared


def need(value, message):
    if not value:
        raise ValueError(message)


def unused(manifest):
    need(manifest.get("status") == "prepared" and manifest.get("commands") == [] and
         manifest.get("lifecycle_started") in (None, False) and
         not any(k in manifest for k in ("lock_token", "shared_lock", "remote_simulation_dir",
                                        "execution_runner_sha256", "capture", "cleanup_status")),
         "Only a fresh unused prepared job may gain input snapshots")


def checked(path, expected):
    need(isinstance(expected, str) and re.fullmatch("[0-9a-f]{64}", expected),
         "Typed SHA256 required")
    need(path.is_absolute() and path.is_file() and batch.digest(path) == expected,
         "Bound input missing or changed: " + str(path))


def complete(job, expected):
    job = Path(job).resolve()
    manifest_path = job / "run.json"
    checked(manifest_path, expected)
    previous = manifest_path.read_bytes()
    manifest = json.loads(previous)
    unused(manifest)
    run_prepared.verify(job)
    inputs = dict(manifest["input_sha256"])
    for name, want in inputs.items():
        checked(Path(name), want)
    snapshot = job / "prepared-inputs"
    need(snapshot.is_dir() and not snapshot.is_symlink(), "Existing real snapshot directory required")
    added = job / "input-snapshot-completion-v1"
    need(not added.exists(), "Fresh snapshot-completion epoch required")
    added.mkdir(mode=0o700)
    predecessor = added / "preceding-prepared-run.json"
    predecessor.write_bytes(previous)
    for path in (Path(__file__).resolve(), predecessor):
        name, want = str(path), batch.digest(path)
        need(name not in inputs or inputs[name] == want, "Conflicting completion source")
        inputs[name] = want
    copies, existing = [], 0
    for name, want in sorted(inputs.items()):
        source, destination = Path(name), snapshot / want
        checked(source, want)
        need(not destination.is_symlink(), "Snapshot symlink refused")
        if destination.exists():
            checked(destination, want)
            existing += 1
        else:
            # Exclusive creation preserves old snapshot bytes on every outcome.
            with source.open("rb") as src, destination.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            copies.append(dict(input=name, sha256=want, bytes=destination.stat().st_size))
        checked(destination, want)
        checked(source, want)
    coverage = added / "coverage.json"
    report = dict(schema="iris.complete_prepared_input_snapshots.v1", **{"pass": True},
                  created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  hardware_contacted=False, runner_or_runtime_or_hook_changed=False,
                  preceding_prepared_manifest_sha256=expected,
                  inputs_before_coverage_self_record=len(inputs),
                  existing_copies_verified=existing, additional_copies=copies,
                  original_input_sha256=dict(manifest["input_sha256"]),
                  scope="All final input digests have standalone content-addressed copies; coverage self-record is copied separately")
    coverage.write_text(json.dumps(report, indent=2) + "\n")
    inputs[str(coverage)] = batch.digest(coverage)
    destination = snapshot / inputs[str(coverage)]
    need(not destination.exists(), "Coverage self-record destination must be fresh")
    shutil.copyfile(coverage, destination)
    checked(destination, inputs[str(coverage)])
    # Recheck all inputs and the original manifest before the only metadata edit.
    for name, want in inputs.items():
        checked(Path(name), want)
        checked(snapshot / want, want)
    need(manifest_path.read_bytes() == previous, "Prepared manifest changed during snapshot completion")
    manifest["input_sha256"] = inputs
    manifest["input_snapshot_completion"] = dict(
        coverage=str(coverage), coverage_sha256=batch.digest(coverage),
        preceding_manifest_sha256=expected, all_final_inputs_have_standalone_bytes=True)
    for parent in (snapshot, added):
        for path in parent.iterdir():
            need(path.is_file() and not path.is_symlink(), "Only regular local snapshot files allowed")
            manifest["prepared_file_sha256"][str(path.relative_to(job))] = batch.digest(path)
    batch.save_manifest(job, manifest)
    run_prepared.verify(job)
    return dict(status="completed_locally", hardware_contacted=False,
                final_input_count=len(inputs), added_copies=len(copies) + 1,
                final_prepared_manifest_sha256=batch.digest(manifest_path),
                coverage_sha256=batch.digest(coverage))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--expected-prepared-manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(complete(args.job, args.expected_prepared_manifest_sha256)))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, "iris-input-snapshot-completion: " + str(error) + "\n")
