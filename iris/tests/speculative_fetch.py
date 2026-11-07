#!/usr/bin/env python3
"""Check speculative versus architectural instruction-definedness boundaries.

Four fresh ELFs exercise both unknown first parcels and missing second parcels.
Positive programs return around the gap; negative programs actually jump into
it and must still terminate with IRIS_UNDEFINED_STATE. All three harts exist;
harts 1/2 explicitly park. This is not a timing-accuracy test.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
IRIS = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def layout(elf, partial):
    data = elf.read_bytes()
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    assert header[0][:7] == b"\x7fELF\x02\x01\x01" and header[2] == 243
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, header[6] + i * header[11])
                for i in range(header[12])]
    names = sections[header[13]]
    strings = data[names[4]:names[4] + names[5]]
    text = next(row for row in sections
                if strings[row[0]:].split(b"\0", 1)[0] == b".text")
    end = text[3] + text[5]
    tail_size = 4 if partial else 2
    assert data[text[4] + text[5] - tail_size:text[4] + text[5] - tail_size + 2] == b"\x82\x80"
    if partial:
        assert data[text[4] + text[5] - 2:text[4] + text[5]] == b"\x13\x00"
    loads = [struct.unpack_from("<IIQQQQQQ", data, header[5] + i * header[9])
             for i in range(header[10])]
    assert not any(p[0] == 1 and p[3] <= end < p[3] + p[6] for p in loads), "Gap must not be ELF/BSS-defined"
    return dict(text_end=end, return_pc=end - tail_size,
                undefined_instruction_pc=end - (2 if partial else 0))


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--baseline-build", type=Path)
    parser.add_argument("--riscv-gcc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for partial in (False, True):
        for negative in (False, True):
            name = ("partial32" if partial else "text_end") + ("_demand" if negative else "_return")
            elf = output / (name + ".elf")
            argv = [str(args.riscv_gcc.resolve()), "-march=rv64gc", "-mabi=lp64d", "-mno-relax",
                    "-nostdlib", "-nostartfiles", "-static", "-Wl,--no-relax",
                    "-Wl,-T," + str(HERE / "speculative_fetch.ld"),
                    "-DNEGATIVE=" + str(int(negative)), "-DPARTIAL=" + str(int(partial)),
                    str(HERE / "speculative_fetch.S"), "-o", str(elf)]
            subprocess.run(argv, check=True, capture_output=True)
            geometry = layout(elf, partial)
            for kind, build in (("fixed", args.build), ("baseline", args.baseline_build)):
                if build is None:
                    continue
                run = output / (name + "_" + kind)
                result = subprocess.run([sys.executable, str(IRIS / "run.py"),
                    "--build", str(build.resolve()), "--profile", "source_os", "--elf", str(elf),
                    "--output", str(run), "--timeout", "30"], text=True, capture_output=True)
                (output / (name + "_" + kind + ".launcher.stdout")).write_text(result.stdout)
                (output / (name + "_" + kind + ".launcher.stderr")).write_text(result.stderr)
                record = json.loads((run / "run.json").read_text())
                stderr = (run / "stderr").read_text()
                should_refuse = negative or kind == "baseline"
                refused = (record.get("exit_status") == 1 and not record.get("timed_out")
                           and "IRIS_UNDEFINED_STATE hart=0" in stderr and "unit=instruction" in stderr
                           and ("pc=" + hex(geometry["undefined_instruction_pc"])) in stderr)
                passed = refused if should_refuse else record.get("pass") is True and record.get("exit_status") == 0
                rows.append(dict(name=name, kind=kind, expected_refusal=should_refuse,
                                 **geometry, **{"pass": passed}, exit_status=record.get("exit_status"),
                                 ELF_sha256=sha(elf), receipt_sha256=sha(run / "run.json"),
                                 stderr_sha256=sha(run / "stderr")))
    report = dict(schema="iris.speculative_fetch_definedness_regression.v1",
                  **{"pass": all(r["pass"] for r in rows)}, rows=rows,
                  physical_harts=3, parked_harts=[1, 2], hardware_contacted=False,
                  timing_accuracy_certified=False,
                  source_sha256={str(p): sha(p) for p in
                      (Path(__file__).resolve(), HERE / "speculative_fetch.S", HERE / "speculative_fetch.ld")})
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pass": report["pass"], "cases": len(rows)}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
