#!/usr/bin/env python3
"""Compare every private scalar ROI; debugger stop is explicitly not guest exit."""
import argparse
import collections
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "timing"))
from compare_pow2_native import sha, load, need, inventory, metrics, grouped


def compare(run, hardware, output):
    run, hardware, output = [p.resolve() for p in (run, hardware, output)]
    need(not output.exists(), "Fresh output required")
    rr, hr = load(run / "run.json"), load(hardware / "report.json")
    need(rr["schema"] == "iris.pow2_scalar_private_intentional_readback.v2"
         and rr["status"] == "passed" and rr["debugger_process_exit_status"] == 0
         and rr["timed_out"] is False
         and rr["intentional_postmeasurement_debugger_stop"] is True
         and rr["normal_guest_exit_verified"] is False
         and rr["whole_run_timing_claim"] is False,
         "Complete explicitly scoped postmeasurement observation required")
    need(hr["pass"] is True and hr["archive_verified"] is True
         and hr["normal_completion"] is True, "Strict complete archived hardware run required")
    inventory(rr["input_sha256"])
    inventory(rr["output_sha256"])
    inventory(hr["input_sha256"])
    elf = hardware / "observed.elf"
    need(sha(elf) == hr["ELF_sha256"], "Archived ELF identity")
    need(rr["input_sha256"].get(rr["argv"][-1]) == sha(elf), "Same hardware/native ELF")
    source = ROOT / "benchmarks/pow2_scalar_private_v2"
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location("private_readback", source / "readback.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    corpus = load(hardware / "corpus.json")
    # Independently decode the preserved debugger bytes and recheck every actual
    # CSR endpoint against the ELF; cached JSON success flags are insufficient.
    layout_path = next(Path(p) for p in rr["input_sha256"] if p.endswith("/layout.json"))
    native = reader.decode((run / "stderr").read_text(), corpus, load(layout_path))
    proof = reader.prefix_proof(run / "features.jsonl", native, elf,
                                ROOT / "board/evidence/bootrom.rv64.img")
    saved = [json.loads(s) for s in (run / "regions.jsonl").read_text().splitlines()]
    need(native == saved, "Recomputed native rows must match saved observation")
    measured = [json.loads(s) for s in (hardware / "regions.jsonl").read_text().splitlines()]
    need(len(native) == len(measured) == 576, "Every declared region required")
    rows = []
    for s, h, c in zip(native, measured, corpus["cases"]):
        need(s["case_id"] == h["case_id"] == c["id"] and s["hart"] == h["hart"], "Ordered identity")
        for key in ("kind", "n", "trial_id", "internal_split", "values"):
            need(s[key] == h[key], "Matching metadata/golden: " + key)
        need(h["pass"] is True and s["values"] == c["expected_values"], "All actual word goldens")
        sc, hc = s["end_cycle"] - s["start_cycle"], h["end_cycle"] - h["start_cycle"]
        need(sc > 0 and hc > 0, "Positive regions")
        row = {k: h[k] for k in ("case_id", "hart", "kind", "n", "trial_id", "internal_split")}
        row.update(native_cycles=sc, hardware_cycles=hc, signed_error_percent=100 * (sc-hc)/hc,
                   native_instret=s["instret_delta"], hardware_instret=h["instret_delta"],
                   instret_equal=s["instret_delta"] == h["instret_delta"],
                   begin_pc=s["begin_pc"], end_pc=s["end_pc"])
        for label, record in (("native", s), ("hardware", h)):
            ticks = record["mtime_after"] - record["mtime_before"]
            need(ticks >= 0, "Forward CLINT")
            row[label + "_CLINT_enclosing_ticks"] = ticks
        rows.append(row)
    groups = {"by_partition": grouped(rows, ["internal_split"]),
              "by_hart": grouped(rows, ["hart"]), "by_kind": grouped(rows, ["kind"]),
              "by_length": grouped(rows, ["n"]),
              "by_shape_hart": grouped(rows, ["kind", "hart", "n"])}
    output.mkdir(parents=True)
    (output / "regions.jsonl").write_text("".join(json.dumps(r, sort_keys=True)+"\n" for r in rows))
    (output / "groups.json").write_text(json.dumps(groups, indent=2)+"\n")
    inputs = [Path(__file__).resolve(), source / "readback.py", source / "validate.py",
              run / "run.json", run / "stderr", run / "features.jsonl", run / "regions.jsonl",
              hardware / "report.json", hardware / "corpus.json", hardware / "regions.jsonl", elf]
    report = dict(schema="iris.private_scalar_postmeasurement_comparison.v1", passed=True,
                  all_regions_retained=True, regions=576, overall=metrics(rows),
                  partitions=groups["by_partition"], actual_CSR_proof=proof,
                  native_normal_guest_exit_verified=False, hardware_normal_completion_verified=True,
                  intentional_native_postmeasurement_stop=True, whole_run_timing_claim=False,
                  accuracy_2percent_certified=False, source_image_association_verified=False,
                  parameters_refit=False, reserved_labels_consumed_by="root validation only",
                  actual_native_host_seconds=rr["host_seconds"],
                  input_sha256={str(p): sha(p) for p in inputs},
                  output_sha256={p.name: sha(p) for p in output.iterdir()})
    (output / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k: report[k] for k in ("passed", "overall", "partitions")}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(__doc__)
    for key in ("run", "hardware", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    compare(a.run, a.hardware, a.output)
