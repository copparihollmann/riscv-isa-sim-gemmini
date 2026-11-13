#!/usr/bin/env python3
"""Replay strict archive derivation before comparing native measured regions."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "timing"))
from compare_pow2_native import sha, load, need, inventory, main as normal_compare
from compare_private_scalar_readback import compare as private_compare


def verify_reference(kind, hardware):
    hr = load(hardware / "report.json")
    inventory(hr["input_sha256"])
    jobs = [Path(p).parent for p in hr["input_sha256"] if p.endswith("/run.json")]
    need(len(jobs) == 1, "Unique inventory-bound hardware job")
    job = jobs[0]
    with tempfile.TemporaryDirectory(prefix="pow2-reference-rederive-") as tmp:
        fresh, train = Path(tmp) / "reference", Path(tmp) / "train"
        if kind == "private_scalar":
            command = [sys.executable, str(ROOT / "firesim/pow2_scalar_private_v2_campaign.py"),
                       "analyze", str(job), "--output", str(fresh), "--training-export", str(train)]
        else:
            command = [sys.executable, str(ROOT / "firesim/analyze_pow2_packets_v2.py"),
                       "--kind", kind, str(job), "--output", str(fresh), "--training-export", str(train)]
        checked = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        need(checked.returncode == 0, "Strict archive rederivation failed: " + checked.stderr.decode()[-1000:])
        newly = load(fresh / "report.json")
        need(newly["archive_verified"] is True
             and newly["archive_sha256"] == hr["archive_sha256"], "Same verified archive")
        names = ["corpus.json", "observed.elf", "regions.jsonl"]
        for name in names:
            need((fresh / name).read_bytes() == (hardware / name).read_bytes(),
                 "Derived hardware output differs from strict archive replay: " + name)
        return dict(archive_rederivation_verified=True, analyzer_command=command,
                    analyzer_stdout=checked.stdout.decode(),
                    exact_derived_sha256={name: sha(hardware / name) for name in names},
                    archive_sha256=hr["archive_sha256"], hardware_contacted=False)


def main(a):
    a.hardware, a.run, a.output = [p.resolve() for p in (a.hardware, a.run, a.output)]
    need(not a.output.exists(), "Fresh output required")
    proof = verify_reference(a.kind, a.hardware)
    if a.kind == "private_scalar":
        private_compare(a.run, a.hardware, a.output)
    else:
        normal_compare(a)
    report_path = a.output / "report.json"
    report = load(report_path)
    report["verified_reference_adapter"] = proof
    report["input_sha256"][str(Path(__file__).resolve())] = sha(__file__)
    report_path.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--kind", choices=["memory", "matrix", "private_scalar"], required=True)
    for key in ("run", "hardware", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    main(p.parse_args())
