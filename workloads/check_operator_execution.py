#!/usr/bin/env python3
"""Independently qualify the finite, source-bound operator execution receipts.

This verifies completed executions; it does not fit timing or admit a model's
weights. All labels and source inputs remain separate from the calibration set.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def numerical_oracle(m, n, k):
    # Separate iterative modular matrix implementation; never import the
    # generator's golden or scalar/VME implementation as the numeric oracle.
    result = [0] * (m * n)
    producer = 14695981039346656037
    for i in range(m):
        for q in range(k):
            b = (17 * i + 11 * q + 3) % 256
            producer = ((producer ^ b) * 1099511628211) % (1 << 64)
    for q in range(k):
        for j in range(n):
            b = (13 * q + 7 * j + 5) % 256
            producer = ((producer ^ b) * 1099511628211) % (1 << 64)
        for i in range(m):
            a = (17 * i + 11 * q + 3) % 256
            a -= 256 if a >= 128 else 0
            for j in range(n):
                b = (13 * q + 7 * j + 5) % 256
                b -= 256 if b >= 128 else 0
                index = i * n + j
                result[index] = (result[index] + a * b) % (1 << 32)
    quantized = []
    for word in result:
        signed = word if word < (1 << 31) else word - (1 << 32)
        quantized.append(struct.unpack("<I", struct.pack("<f", max(-128, min(127, (signed + 512) // 1024))))[0])
    return {"accumulator_u32": result, "w8a8_f32_words": quantized, "producer_fnv1a64": producer}


def console(text, expected, workers):
    lines = text.splitlines()
    for tag, name in (("ACC_I32", "accumulator_u32"), ("OUT", "w8a8_f32_words")):
        rows = [line.split() for line in lines if line.startswith(tag + " ")]
        require(len(rows) == 1, "missing/duplicate full numerical output")
        row = rows[0]
        require(int(row[1]) == len(expected[name]) and list(map(int, row[2:])) == expected[name], "independent numerical mismatch")
    require(lines.count("DONE") == 1 and lines.count("ERRORS 0") == 1, "unique successful completion required")
    rows = [line.split() for line in lines if line.startswith("PRODUCER ")]
    require(rows == [["PRODUCER", "2", str(expected["producer_fnv1a64"])]], "actual hart2 producer checksum required")
    regions = [list(map(int, line.split()[1:])) for line in lines if line.startswith("REGION ")]
    require(len(regions) == workers and {r[0] for r in regions} == set(range(workers)), "active hart coverage")
    require(all(len(r) == 5 and r[2] > r[1] and r[3] > 0 for r in regions), "invalid counter ROI")
    return regions


def roi_projection(frames, regions, m, n, k, kind):
    require(all(f.get("hart") in (0, 1, 2) for f in frames), "unexpected physical hart")
    require(not any(any(name.startswith("vme.") and value.get("instructions", 0) for name, value in f.get("features", {}).items()) for f in frames if f["hart"] == 2), "VME execution on producer hart")
    require(not any(any(name.startswith("vme.") and value.get("instructions", 0) for name, value in f.get("features", {}).items()) for f in frames) if kind == "twin" else True, "scalar twin used VME")
    rows = []
    for hart, begin, end, retired, _heap in regions:
        left = [f for f in frames if f["hart"] == hart and f.get("csr") == 0xB00 and f.get("value") == begin]
        right = [f for f in frames if f["hart"] == hart and f.get("csr") == 0xB00 and f.get("value") == end]
        require(len(left) == len(right) == 1, "ambiguous/missing modeled mcycle codepoint")
        a, b = left[0], right[0]
        require(b["sequence"] > a["sequence"] and b["read_cycle"] > a["read_cycle"], "counter order")
        require(b.get("async_compute_pending") is False and b.get("async_pending_count") == 0, "ROI ends before compute drain")
        af, bf = a["features"].get("vme.int8", {}), b["features"].get("vme.int8", {})
        macs = bf.get("macs", 0) - af.get("macs", 0)
        operations = bf.get("instructions", 0) - af.get("instructions", 0)
        expected_macs = m // len(regions) * n * k if kind == "shipped" else 0
        require(macs == expected_macs, "actual ROI VME MAC count differs from contraction")
        require(operations == k // 4 if kind == "shipped" else operations == 0, "actual INT8 microkernel instruction count")
        rows.append(dict(hart=hart, begin_mcycle=begin, end_mcycle=end, modeled_mcycle_delta=end-begin,
                         global_modeled_elapsed=b["read_cycle"]-a["read_cycle"], guest_instret_delta=retired,
                         int8_vme_instructions=operations, int8_macs=macs,
                         actual_csr_boundaries=[dict(pc=f["pc"], raw=f["raw"], sequence=f["sequence"], read_cycle=f["read_cycle"]) for f in (a,b)],
                         compute_drained_at_end=True, timing_accuracy_qualified=False))
    return rows


def executable_instructions(path):
    data = Path(path).read_bytes()
    require(data[:6] == b"\x7fELF\x02\x01", "ELF64 little-endian required")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    shsize, count = struct.unpack_from("<HH", data, 58)
    words = []
    for i in range(count):
        fields = struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shsize)
        _name, _type, flags, address, offset, size, *_ = fields
        if not flags & 4:
            continue
        pos, limit = offset, offset + size
        while pos + 2 <= limit:
            low = struct.unpack_from("<H", data, pos)[0]
            width = 4 if low & 3 == 3 else 2
            if width == 4:
                require(pos + 4 <= limit, "truncated executable instruction")
                words.append((address + pos - offset, struct.unpack_from("<I", data, pos)[0]))
            pos += width
    return words


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--runs", type=Path, default=ROOT / "build/workload-small-M-v1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    identities, cache = {}, {}

    def bind(path, expected=None):
        p = Path(path)
        p = p if p.is_absolute() else ROOT / p
        p = p.resolve()
        key = str(p)
        if key not in cache:
            cache[key] = digest(p)
        observed = cache[key]
        require(expected is None or observed == expected, "input changed: " + key)
        require(key not in identities or identities[key] == observed, "conflicting source digest")
        identities[key] = observed
        return observed

    bind(__file__)
    parent = json.loads((ROOT / "workloads/iris-mlir-small-m/small-m-companion.json").read_text())
    bind(ROOT / "workloads/iris-mlir-small-m/small-m-companion.json")
    differences = []
    for relative, expected in parent["parent_source_sha256"].items():
        bind(Path(parent["parent_target"]) / relative, expected)
        p = ROOT / "workloads/iris-mlir-small-m" / relative
        if bind(p) != expected:
            differences.append(relative)
    require(differences == ["matrix_lowering.py"], "private companion scope changed")
    admission = ROOT / "build/workload-small-M-admission-v1/report.json"
    require(json.loads(admission.read_text())["pass"], "admission controls did not pass")
    bind(admission)
    reports = sorted(args.runs.glob("*/results.json"))
    require(len(reports) == 8, "all four finite cases at both hart counts required")
    cases, seen, mutation_inputs = [], set(), None
    for report in reports:
        r = json.loads(report.read_text())
        bind(report)
        c = r["case"]
        m, n, k = c["shape_mnk"]
        key = (c["case_id"], c["workers"])
        require(key not in seen and c["workers"] in (1,2), "duplicate execution identity")
        seen.add(key)
        require(r["pass"] and not r["calibration_or_fit_inputs"] and not r["hardware_contacted"], "execution or exclusion policy")
        require(c["physical_harts"] == 3 and c["cpu_producer_hart"] == 2 and m == 2 and n == 32, "finite domain")
        require(not c["fit_eligible"] and r["validation_only"] == (c["case_id"] == "tinyllama-base"), "validation-only split")
        for p, expected in r["input_sha256"].items():
            bind(p, expected)
        expected = numerical_oracle(m,n,k)
        require(json.loads((report.parent / "golden.json").read_text()) == expected, "stored golden differs from independent oracle")
        artifact_path = report.parent / "compiled/artifacts.json"
        artifact = json.loads(artifact_path.read_text())
        bind(artifact_path)
        require(artifact["local_shape_mnk"] == [m//c["workers"],n,k] and artifact["routing"]["count"] == 1, "actual compiler route")
        require(artifact["routing"]["routing_rule"]["fills_default_tile_rule"] is False, "small-M route proof")
        enc_path = report.parent / "compiled/matrix/encodings.json"
        enc = json.loads(enc_path.read_text())
        bind(enc_path)
        for p, expected_digest in enc["sources"].items():
            bind(p, expected_digest)
        outputs = []
        for run in r["runs"]:
            kind = run["kind"]
            require(kind in ("shipped", "twin") and run["returncode"] == 0, "successful actual run required")
            for p, expected_digest in run["execution_input_sha256"].items():
                bind(p, expected_digest)
            require(run["argv"][0].endswith("empirical-28a0-fatal-launcher-v2/spike") and "-p3" in run["argv"], "selected guard and actual three-hart launch")
            require(run["simulator"]["native_binary_sha256"] == "28a0a52ba04ca05aec01b1c1a9ca86becbd47336d4eec112873695cdb7ea6c50", "selected native pair")
            require(run["simulator"]["binary_sha256"] == "831c2e6ca8ce55d683b3b743ed2cb087e3d5b2dec6d56be5ccc867657109b280", "selected fail-fast launcher")
            require(not run["simulator"]["accuracy_2percent_certified"], "shape accuracy unavailable")
            elf = report.parent / (kind + ".elf")
            bind(elf, run["elf_sha256"])
            text_path, error_path, prefix_path = (report.parent / (kind + suffix) for suffix in (".stdout", ".stderr", ".prefix.jsonl"))
            bind(text_path, run["stdout_sha256"])
            bind(error_path, run["stderr_sha256"])
            bind(prefix_path, run["prefix_sha256"])
            bind(report.parent / (kind + ".run.json"))
            regions = console(text_path.read_text(), expected, c["workers"])
            require(regions == run["regions"], "console/receipt ROI binding")
            frames = [json.loads(line) for line in prefix_path.read_text().splitlines()]
            projection = roi_projection(frames, regions, m,n,k,kind)
            raw_mm = enc["encodings"]["SF_MM_INT"]
            static_mm = [pc for pc, raw in executable_instructions(elf) if raw & raw_mm["mask"] == raw_mm["match"]]
            require(bool(static_mm) == (kind == "shipped"), "actual executable VME/twin distinction")
            outputs.append(dict(kind=kind, elf_sha256=run["elf_sha256"], host_seconds=run["host_seconds"], int32_words=len(expected["accumulator_u32"]), W8A8_words=len(expected["w8a8_f32_words"]), actual_INT8_VME_instruction_pcs=static_mm, regions=projection))
            if mutation_inputs is None and kind == "shipped":
                mutation_inputs = (text_path.read_text(), expected, c["workers"], frames, regions, m,n,k)
        require({a["kind"] for a in outputs} == {"shipped", "twin"}, "both executed images required")
        cases.append(dict(case=c, receipt=str(report.resolve()), receipt_sha256=digest(report), images=outputs))
    require(seen == {(name,h) for name in ("gpt-oss-20b","gemma4-e4b","tinyllama-base","meta-official-reference") for h in (1,2)}, "case coverage changed")

    text, expected, workers, frames, regions, m,n,k = mutation_inputs
    controls = []
    def reject(name, fn):
        try:
            fn()
        except (ValueError, KeyError, AssertionError):
            controls.append(dict(name=name, rejected=True))
            return
        raise ValueError("corruption accepted: " + name)
    altered = copy.deepcopy(expected)
    altered["accumulator_u32"][0] ^= 1
    reject("wrong full accumulator", lambda: console(text, altered, workers))
    reject("duplicate completion", lambda: console(text + "\nDONE\n", expected, workers))
    changed = copy.deepcopy(frames)
    end = next(f for f in changed if f["hart"] == regions[0][0] and f.get("value") == regions[0][2] and f.get("csr") == 0xB00)
    end["features"]["vme.int8"]["macs"] -= 1
    reject("one missing MAC", lambda: roi_projection(changed,regions,m,n,k,"shipped"))
    changed = copy.deepcopy(frames)
    end = next(f for f in changed if f["hart"] == regions[0][0] and f.get("value") == regions[0][2] and f.get("csr") == 0xB00)
    end["async_compute_pending"] = True
    reject("incomplete unit at ROI end", lambda: roi_projection(changed,regions,m,n,k,"shipped"))
    changed = copy.deepcopy(frames)
    changed.append(copy.deepcopy(next(f for f in changed if f["hart"] == regions[0][0] and f.get("value") == regions[0][2] and f.get("csr") == 0xB00)))
    reject("ambiguous CSR boundary", lambda: roi_projection(changed,regions,m,n,k,"shipped"))
    changed = copy.deepcopy(frames)
    changed.append(dict(hart=2, features={"vme.int8":dict(instructions=1,macs=1)}))
    reject("hart2 VME ownership", lambda: roi_projection(changed,regions,m,n,k,"shipped"))
    noop_path = ROOT / "build/workload-small-M-noop-v1/report.json"
    noop = json.loads(noop_path.read_text())
    bind(noop_path)
    for p,d in noop["input_sha256"].items(): bind(p,d)
    for p,d in noop["actual_run"]["execution_input_sha256"].items(): bind(p,d)
    for name in ("stdout","stderr","prefix.jsonl","build.log"): bind(noop_path.parent/name)
    require(noop["pass"] and noop["actual_run"]["returncode"] != 0 and noop["poisoned_accumulator_words"] == 64 and noop["kernel_omission_detected"], "real no-op counterfactual failed")
    gpt = numerical_oracle(2,32,2880)
    require(noop["actual_accumulator_words"] == [w ^ 0xffffffff for w in gpt["accumulator_u32"]], "actual poisoned words")
    controls.append(dict(name="actual compiled omitted-kernel negative", rejected=True, poisoned_words=64, exit_status=noop["actual_run"]["returncode"]))
    result = dict(schema="iris.source_bound_model_operator_qualification.v1", **{"pass":True}, cases=cases,
                  successful_images=16, independently_compared_int32_words=1024, independently_compared_W8A8_words=1024,
                  source_model_families_executed=["openai/gpt-oss-20b","google/gemma-4-E4B-it","TinyLlama/TinyLlama-1.1B-intermediate-step-1431k-3T"],
                  exact_Llama2_checkpoint_admitted=False, official_Meta_reference_only=True,
                  original_bound_target_unchanged=True, private_target_differences=differences,
                  numerical_controls=controls, all_new_cases_fit_eligible=False, TinyLlama_validation_only=True,
                  full_operator_or_model_qualified=False, checkpoint_weights_executed=False, checkpoint_quantization_qualified=False,
                  new_operator_shapes_on_Zephyr_qualified=False, timing_accuracy_for_new_shapes_qualified=False,
                  hardware_contacted=False, input_sha256=identities,
                  archive_scope="Direct build/ELF/output/MLIR/target/config artifacts are frozen separately; selected28 native/source closure and calibration/image evidence remain hash-bound referenced immutable packages. No complete compiler system-header reconstruction claim.")
    (out/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(dict(**{"pass":True},cases=len(cases),images=16,verified_unique_inputs=len(identities),report_sha256=digest(out/"report.json"))))


if __name__ == "__main__":
    main()
