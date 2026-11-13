"""Additive checked-publication profiler; execution delegates unchanged v1.

Use an explicit existing guarded model manifest. This module does not create a
provider, weaken a refusal, select a model, or certify numerical output.
"""
import argparse
import datetime
import json
from pathlib import Path
import signal
import sys

from . import source_profile_run_v1 as execution_v1
from . import source_event_profile_v2 as consumer_v2

ROOT = Path(__file__).resolve().parents[1]


def run(elf, manifest, output, timeout=600, seed=0, region_map=None,
        region_format="iris-json"):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(schema="iris.source_profile_ELF_execution.v2", status="preflight",
                   **{"pass": False}, profile_pass=False, error=None,
                   hardware_contacted=False, native_model_or_provider_changed=False,
                   independent_numeric_validation=None, timing_accuracy_certified=False,
                   started_at_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat())
    inputs = {str(p): consumer_v2.sha(p) for p in
              (Path(__file__).resolve(), Path(execution_v1.__file__).resolve(),
               Path(consumer_v2.__file__).resolve(), Path(elf).resolve(), Path(manifest).resolve())}

    def save():
        (output / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")

    save()
    try:
        # v1 owns descriptor validation, fatal-aware launch, timeout/owned
        # cleanup, all ISA/device/fixture arguments and the immutable receipt.
        executed = execution_v1.run(elf, manifest, output / "execution-v1", timeout,
                                    seed, "source-events.jsonl", region_map, region_format)
        receipt["execution_receipt"] = str(output / "execution-v1/run.json")
        receipt["v1_execution_pass"] = executed.get("pass")
        receipt["v1_observer_result_preserved"] = executed.get("source_profile")
        consumer_v2.need(executed.get("pass") is True and
                         executed.get("unchanged_inputs_after_execution") is True,
                         "Unchanged guarded v1 execution did not pass: " + str(executed.get("error")))
        execution_v1.checked_inputs(executed["input_sha256"])
        fixture = [arg.split("=", 1)[1] for arg in executed["argv"]
                   if arg.startswith("--iris-timing-fixture=")]
        rom = [arg.split("=", 1)[1] for arg in executed["argv"]
               if arg.startswith("--iris-bootrom=")]
        consumer_v2.need(len(fixture) == len(rom) == 1, "Unique bound fixture and ROM required")
        nm = Path("/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm")
        result = consumer_v2.profile(
            output / "execution-v1/source-events.jsonl", output / "execution-v1/features.jsonl",
            output / "execution-v1/stdout", output / "execution-v1/native-summary.json",
            Path(elf).resolve(), rom[0], output / "source-profile-v2", nm,
            region_map, region_format, True, fixture[0], output / "execution-v1/run.json")
        consumer_v2.need(all(consumer_v2.sha(Path(p)) == h for p,h in inputs.items()),
                         "Frontend, ELF or model changed during execution/profile")
        receipt.update(status="passed_guarded_execution_and_source_profile", profile_pass=True,
                       **{"pass": True}, independent_numeric_validation=None,
                       source_profile=dict(summary=str(output / "source-profile-v2/summary.json"),
                                           trace=str(output / "source-profile-v2/trace.json"),
                                           commands=str(output / "source-profile-v2/commands.jsonl"),
                                           journal_complete=result["journal_complete"],
                                           regions=len(result["regions"])),
                       guest_exit_pass_is_not_independent_numeric_or_timing_certification=True)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        receipt.update(status="refused_or_failed", error=str(error), **{"pass": False})
    finally:
        receipt["input_sha256"] = inputs
        receipt["finished_at_UTC"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        receipt["output_sha256"] = {str(p): consumer_v2.sha(p) for p in output.rglob("*")
                                    if p.is_file() and p != output / "run.json"}
        save()
    return receipt


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Interrupted by signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True,
                        help="Explicit guarded provider manifest; no implicit-current selection")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--region-map", type=Path)
    parser.add_argument("--region-format", choices=("none", "iris-json", "merlin-kernel-v1"), default="iris-json")
    args = parser.parse_args()
    try:
        result = run(args.elf, args.model, args.output, args.timeout, args.seed,
                     args.region_map, args.region_format)
    except (OSError, ValueError) as error:
        parser.exit(1, "iris-source-profile-v2: " + str(error) + "\n")
    print(json.dumps({k:result.get(k) for k in ("pass", "profile_pass", "status", "error", "source_profile")}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
