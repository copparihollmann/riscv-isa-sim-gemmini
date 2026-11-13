#!/usr/bin/env python3
"""Freeze the declared operator inputs and outputs without rewriting receipts."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--qualification", type=Path, default=ROOT / "build/workload-operator-qualification-v2/report.json")
    p.add_argument("--facts", type=Path, required=True)
    p.add_argument("--failures", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    objects = out / "objects"
    objects.mkdir()
    qualification = json.loads(args.qualification.read_text())
    if not qualification.get("pass"):
        raise ValueError("positive qualification required")
    identities = dict(qualification["input_sha256"])

    def add(path, expected=None):
        path = Path(path).resolve()
        observed = digest(path)
        if expected is not None and expected != observed:
            raise ValueError("changed input: " + str(path))
        if str(path) in identities and identities[str(path)] != observed:
            raise ValueError("conflicting input identity")
        identities[str(path)] = observed

    for path in (Path(__file__), args.qualification, args.facts, args.failures,
                 ROOT / "workloads/EXECUTED_OPERATORS.md"):
        add(path)
    for receipt in (args.facts, args.failures):
        for path, expected in json.loads(receipt.read_text()).get("input_sha256", {}).items():
            add(path, expected)
    for directory in ("build/workload-small-M-v1", "build/workload-small-M-noop-v1",
                      "build/workload-small-M-admission-v1", "build/workload-source-access-v1",
                      "build/workload-operators-v1", "build/workload-operators-v2",
                      "workloads/iris-mlir-small-m"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                add(path)
    artifacts = {}
    for name, expected in sorted(identities.items()):
        source = Path(name)
        if digest(source) != expected:
            raise ValueError("input changed during freeze: " + name)
        dest = objects / expected
        if not dest.exists():
            shutil.copyfile(source, dest)
        if digest(dest) != expected:
            raise ValueError("archive byte identity mismatch")
        artifacts[name] = dict(sha256=expected, bytes=source.stat().st_size,
                               object="objects/" + expected)
    unique = list(objects.iterdir())
    report = dict(schema="iris.model_operator_execution_closure.v1", **{"pass": True},
                  qualification_sha256=digest(args.qualification), source_facts_sha256=digest(args.facts),
                  preserved_failures_sha256=digest(args.failures), files=len(artifacts),
                  content_objects=len(unique), stored_bytes=sum(path.stat().st_size for path in unique),
                  artifacts=artifacts, all_declared_input_bytes_archived=True,
                  compiler_system_header_reconstruction_qualified=False,
                  absolute_path_receipts_rewritten=False, relocatable_executable_claimed=False,
                  all_new_cases_fit_eligible=False, TinyLlama_validation_only=True,
                  original_bound_target_modified=False, primary_native_modified=False,
                  hardware_contacted=False, whole_model_qualified=False,
                  timing_accuracy_for_new_shapes_qualified=False)
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(**{"pass": True}, files=len(artifacts), content_objects=len(unique),
                         stored_bytes=report["stored_bytes"], report_sha256=digest(out / "report.json"))))


if __name__ == "__main__":
    main()
