#!/usr/bin/env python3
"""Audit existing four-format FPGA functional coverage; never export timing labels."""
import argparse
import collections
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ELF_SHA = "9d6f692c98d955276e0ac7d941afefa3551a240f2f8ce39cd2a6f1ab57f44942"
ARCHIVE_SHA = "ac4445271bf781b10e4b09e1bafa86ded73470279a63f4ac3ef898ad641fcaeb"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


class Elf:
    def __init__(self, path):
        self.raw = Path(path).read_bytes()
        h = struct.unpack_from("<16sHHIQQQIHHHHHH", self.raw)
        require(h[0][:7] == b"\x7fELF\x02\x01\x01" and h[1:4] == (2, 243, 1), "Static RV64 ELF")
        self.loads = []
        for i in range(h[10]):
            t, _, off, va, pa, fs, ms, _ = struct.unpack_from("<IIQQQQQQ", self.raw, h[5] + i * 56)
            if t == 1:
                require(va == pa and fs <= ms and off + fs <= len(self.raw), "ELF load bounds")
                self.loads.append((pa, off, fs))
        sections = [struct.unpack_from("<IIQQQQIIQQ", self.raw, h[6] + i * 64) for i in range(h[12])]
        self.symbols = collections.defaultdict(list)
        for s in sections:
            if s[1] != 2:
                continue
            require(s[9] == 24 and s[5] % 24 == 0, "Symbol table geometry")
            ns = sections[s[6]]
            names = self.raw[ns[4]:ns[4] + ns[5]]
            for p in range(s[4], s[4] + s[5], 24):
                n, info, _, index, value, size = struct.unpack_from("<IBBHQQ", self.raw, p)
                if n and index and info & 15 in (0, 1, 2):
                    end = names.find(b"\0", n)
                    require(end >= 0, "Symbol name termination")
                    self.symbols[names[n:end].decode()].append((value, size))

    def read(self, a, n):
        for base, pos, size in self.loads:
            if base <= a and a + n <= base + size:
                return self.raw[pos + a - base:pos + a - base + n]
        raise ValueError("Required ELF bytes not file backed")

    def string(self, a):
        b = bytearray()
        for i in range(256):
            c = self.read(a + i, 1)
            if c == b"\0":
                return b.decode()
            b.extend(c)
        raise ValueError("Unterminated case identity")


def fp8_normal(byte, exponent_bits, fraction_bits):
    e = (byte >> fraction_bits) & ((1 << exponent_bits) - 1)
    require(0 < e < (1 << exponent_bits) - 1, "Only finite normal test operands")
    f = byte & ((1 << fraction_bits) - 1)
    return (-1 if byte & 128 else 1) * Fraction((1 << fraction_bits) + f, 1 << fraction_bits) * Fraction(2) ** (e - ((1 << (exponent_bits - 1)) - 1))


def inspect():
    build = ROOT / "build/campaign-fit-v1"
    report_path = ROOT / "build/fpga-v12-broad-archive-analysis-v2/report.json"
    analysis = json.loads(report_path.read_text())
    corpus = json.loads((build / "corpus.json").read_text())
    metadata = json.loads((build / "build.json").read_text())
    closure_path = ROOT / "build/campaign-fit-v1-closure-v2/report.json"
    closure = json.loads(closure_path.read_text())
    require(analysis["archive_verified"] is True and analysis["managed_run_passed"] is True
            and analysis["functional_checks_passed"] is True, "Actual managed functional run")
    require(analysis["cleanup_status"] == "passed" and analysis["capture_status"] == "captured", "Owned cleanup/capture")
    require(analysis["guest_proof"]["all_independent_checksums_passed"] is True, "Existing independent checksum validation")
    require([(x["task"], x["cleanup_phase"]) for x in analysis["lifecycle"]]
            == [("kill", False), ("infrasetup", False), ("runworkload", False), ("kill", True)], "Four ordered phases")
    require(all(x["status"] == "passed" and type(x["returncode"]) is int and x["returncode"] == 0
                and x["timed_out"] is False for x in analysis["lifecycle"]), "Successful lifecycle")
    require(sha(build / "campaign.elf") == metadata["elf_sha256"] == closure["elf_sha256"] == ELF_SHA, "Exact tested ELF")
    require(sha(build / "corpus.json") == closure["corpus_sha256"], "Exact corpus closure")
    require(closure["pass"] is True, "Closed prior source/functional qualification")
    archive = Path(analysis["archive"])
    require(sha(archive) == analysis["archive_sha256"] == ARCHIVE_SHA, "Exact managed archive bytes")
    archive_members = {}
    # Intentionally never read UART members or any protected timing report.
    with tarfile.open(archive, "r:gz") as tar:
        for member, expected in (("job/manager/workloads/iris-batch/batch.elf", ELF_SHA),
                                 ("job/corpus.json", sha(build / "corpus.json"))):
            matches = [m for m in tar.getmembers() if m.name == member]
            require(len(matches) == 1 and matches[0].isfile(), "Unique captured artifact")
            data = tar.extractfile(matches[0]).read()
            digest = hashlib.sha256(data).hexdigest()
            require(digest == expected, "Captured ELF/corpus equality")
            archive_members[member] = {"sha256": digest, "bytes": len(data)}
    e = Elf(build / "campaign.elf")
    tables = [(a, n) for a, n in e.symbols["experiments"] if n == 1040 * 80]
    require(len(tables) == 1, "Unique compiled distribution table")
    cases = [x for x in corpus["cases"] if x["suite"] == "distribution"]
    require(len(cases) == 1040, "Full compiled distribution coverage")
    selected = {}
    for index, c in enumerate(cases):
        raw = e.read(tables[0][0] + index * 80, 80)
        ptr = struct.unpack_from("<Q", raw)[0]
        require(e.string(ptr) == c["case_id"], "Compiled case order/identity")
        if c["kind"] != "vme_fp8":
            continue
        fields = struct.unpack_from("<11I", raw, 8)
        require(fields == tuple([10] + [c[x] for x in ("n", "mask", "sew", "lmul", "mode", "bytes", "protocol", "edge", "tk", "tiles")]), "Compiled FP8 control fields")
        mode = c["mode"]
        require(type(mode) is int and mode in range(4) and c["edge"] == 32 and c["tk"] == 4 and c["tiles"] == 1, "Qualified FP8 geometry")
        fmt_a, fmt_b = ("e5m2" if mode & 1 else "e4m3"), ("e5m2" if mode & 2 else "e4m3")
        require(c["metadata"]["input_formats"] == [fmt_a, fmt_b], "Format metadata vs selector state")
        a, b = (0x3c if mode & 1 else 0x38), (0x3c if mode & 2 else 0x38)
        decode = lambda x, fmt: fp8_normal(x, 5, 2) if fmt == "e5m2" else fp8_normal(x, 4, 3)
        require(decode(a, fmt_a) == decode(b, fmt_b) == 1, "Independent format decoding")
        # Every output cell is n * TK exactly representable in FP32 for these cases.
        word = struct.unpack("<I", struct.pack("<f", float(c["n"] * c["tk"])))[0]
        expected = 32 * word
        require(c["expected_checksums"] == [expected] * 3 and struct.unpack_from("<3Q", raw, 56) == (expected,) * 3, "Independent checksum / compiled goldens")
        selected[(c["parent_case_id"], c["trial_id"])] = (c, expected)
    require(len(selected) == 80, "All four modes and trials retained")
    # Each sequence is checked directly in ELF, independent of objdump text.
    sequences = {
        0x800065dc: "0d4781465776d7845777d78457f70788",  # widen3, altfmt0, two msetmtype, settn
        0x8000667e: "d84d098b29df0d47930600105776d7845777d78457f70788",  # mode&2 / altfmt256
        0x8000709c: "544c858ae38e0606f71088f2",  # mode&1 and E5 rd0=1
        0x80007722: "5c4c858b638d0718f71088f2",
        0x800078c0: "771088f2", 0x8000791c: "771088f2",  # E4 rd0=0
    }
    for address, data in sequences.items():
        require(e.read(address, len(bytes.fromhex(data))).hex() == data, "Actual ELF format-selection path")
    parents = {c["parent_case_id"] for c, _ in selected.values()}
    actual = {}
    # The existing fitting-analysis file also contains old fitting cycles. Only these
    # four functional fields are accessed; no cycle / retirement values are used.
    for group in analysis["repetitions"]:
        if group["parent_case_id"] not in parents:
            continue
        for sample in group["raw_samples"]:
            key = (group["parent_case_id"], sample["trial_id"], group["hart"])
            require(key not in actual and type(sample["checksum"]) is int, "Unique typed observed checksum")
            actual[key] = sample["checksum"]
    observations = []
    for (parent, trial), (c, expected) in selected.items():
        for hart in range(3):
            if c["mask"] & (1 << hart):
                key = (parent, trial, hart)
                require(actual.get(key) == expected and hart in (0, 1), "Observed independent functional checksum")
                observations.append({"case_id": c["case_id"], "parent_case_id": parent, "trial": trial,
                                     "hart": hart, "mode": c["mode"], "formats": c["metadata"]["input_formats"],
                                     "operand_bytes": [0x3c if c["mode"] & 1 else 0x38, 0x3c if c["mode"] & 2 else 0x38],
                                     "checksum": actual[key], "independent_expected_checksum": expected})
    require(len(actual) == len(observations) == 120, "All 120 active pair/hart/trial observations")
    inputs = {str(p): sha(p) for p in [Path(__file__), report_path, closure_path, build / "build.json", build / "corpus.json", build / "campaign.elf", build / "campaign.disassembly", archive,
              ROOT / "hardware/evidence/outer-product-sequencer.scala", ROOT / "hardware/evidence/outer-product-unit.scala",
              ROOT / "build/rtl-verilator/gen-collateral/OuterProductSequencer.sv", ROOT / "benchmarks/v2/cases.py", ROOT / "benchmarks/v2/validate.py"]}
    for name in ("benchmarks/v2/batch.c", "third_party/saturn/benchmarks/common/vme.h", "build/campaign-fit-v1/distribution.c", "build/campaign-fit-v1/distribution_cases.inc"):
        p = ROOT / name
        require(sha(p) == metadata["input_sha256"][str(p)], "Current source equals actual compiled input")
        inputs[str(p)] = sha(p)
    return {"schema": "iris.fp8_existing_functional_coverage_audit.v1", "pass": True,
            "archive_sha256": ARCHIVE_SHA, "elf_sha256": ELF_SHA, "archive_members": archive_members,
            "pair_counts": dict(sorted(collections.Counter("x".join(x["formats"]) for x in observations).items())),
            "harts": [0, 1], "trials": list(range(5)), "observations": observations,
            "compiled_distribution_rows_checked": 1040, "compiled_fp8_rows_checked": 80,
            "compiled_selector_bytes": {hex(a): b for a, b in sequences.items()},
            "source_decode": {"A": "OuterProductSequencer rd[0] / dis_bits_bits[7]", "B": "vconfig.vtype.altfmt"},
            "scope": "Positive +1 x +1, TK4, edge32, N16/64, row0 tile0 sum of 32 FP32 words; not independent per-word MRF coverage",
            "limitations": ["No negative/special/subnormal/overflow/rounding-mode FP8 coverage inferred", "New ASM and protected ASM packets cover E4M3xE4M3 only", "Macro aliases alone do not select B; callers must set vtype.altfmt", "No new execution or FPGA launch; existing independently validated functional observations audited"],
            "provenance_notice": "An earlier exploratory print incidentally displayed OLD v12 fitting-cycle samples. They were not used, copied into this audit, shared, or fitted. No protected timing labels opened.",
            "new_protected_timing_labels_consumed": False, "timing_analysis_performed": False,
            "new_hardware_contacted": False, "source_image_association_verified": False,
            "additional_four_pair_flash_required_to_establish_this_finite_coverage": False,
            "input_sha256": inputs}


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    require(not args.output.exists(), "Fresh output directory")
    report = inspect()
    args.output.mkdir(parents=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pass": True, "pair_counts": report["pair_counts"], "report_sha256": sha(args.output / "report.json")}))


if __name__ == "__main__":
    main()
