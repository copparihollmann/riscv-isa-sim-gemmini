#!/usr/bin/env python3
"""Export the frozen benchmark corpus to FireSim's case/hart manifest format."""
import argparse
import hashlib
import json
from pathlib import Path


def export(corpus, harts=3, smoke=False):
    if type(harts) is not int or harts not in (1, 2, 3):
        raise ValueError("hart count must be 1, 2 or 3")
    masks = {"all": (1 << harts) - 1, "compute": ((1 << harts) - 1) & 3,
             "1": 1, "4": 4 if harts == 3 else 0}
    output, seen = [], set()
    v2="expected_region_count" in corpus
    if v2 and (harts!=3 or smoke):
        raise ValueError("v2 corpus requires its frozen three-hart ELF; no baseline smoke filter")
    for case in corpus["cases"]:
        if smoke and not case["included_in_smoke"]:
            continue
        name = case["case_id"]
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("invalid or duplicate case identity")
        seen.add(name)
        mask = case["mask"] if v2 else masks[case["active_hart_mask_expression"]]
        if type(mask) is not int or not 0<=mask<8 or (v2 and not mask): raise ValueError("invalid physical hart mask")
        active = [hart for hart in range(harts) if mask & (1 << hart)]
        if active:
            expected=case["expected_checksums"] if v2 else case["expected_checksums_by_hart"]
            if not isinstance(expected,list) or len(expected)!=3 or any(type(v) is not int or not 0<=v<2**64 for v in expected):
                raise ValueError("independent per-hart checksum corpus required")
            output.append({"id": name, "active_harts": active,
                           "region": case["region"], "corpus_split": corpus["split_id"],
                           "expected_checksums_by_hart":expected})
    if not output:
        raise ValueError("no executable cases")
    return output


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--corpus", type=Path, default=Path(__file__).with_name("calibration-corpus.json"))
    parser.add_argument("--harts", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.corpus.read_bytes()
    rows = export(json.loads(raw), args.harts, args.smoke)
    for row in rows:
        row["corpus_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__": main()
