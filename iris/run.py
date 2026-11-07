#!/usr/bin/env python3
"""Run or profile the Iris model built from this fork (no FPGA access)."""

import argparse
import json
from pathlib import Path
import sys

IRIS = Path(__file__).resolve().parent
sys.path.insert(0, str(IRIS))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--profile", choices=("source_compute", "source_os"), required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--source-profile", action="store_true", help="JSON and Perfetto accounting (compute profile)")
    args = parser.parse_args()
    if args.source_profile and args.profile != "source_compute":
        parser.error("Source utilization qualification is limited to the compute profile")
    if args.source_profile:
        from iris_model.source_profile_run_v3 import run
    else:
        from iris_model.empirical_run import run
    try:
        result = run(args.elf, args.build.resolve() / args.profile / "manifest.json",
                     args.output, args.timeout, args.seed)
    except (OSError, ValueError) as error:
        parser.exit(1, "Iris native run: " + str(error) + "\n")
    print(json.dumps({k: result.get(k) for k in ("pass", "status", "exit_status", "error", "profile_pass")}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
