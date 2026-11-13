#!/usr/bin/env python3
"""Snapshot Iris source and elaboration evidence without certifying an FPGA image.

No architecture defaults are supplied: missing required evidence raises an error.
Run from any directory; artifacts and local patches are written beside this file.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-c", "safe.directory=" + str(repo), "-C", str(repo), *args]
    )


def node(text, name):
    """Get one complete DTS node with its original line interval."""
    match = re.search(r"\b" + re.escape(name) + r"\s*\{", text)
    if not match:
        raise ValueError("missing DTS node: " + name)
    start = match.start()
    pos, depth = match.end(), 1
    while depth:
        if pos >= len(text):
            raise ValueError("unterminated DTS node: " + name)
        depth += (text[pos] == "{") - (text[pos] == "}")
        pos += 1
    return text[start:pos], [text.count("\n", 0, start) + 1, text.count("\n", 0, pos) + 1]


def numeric(text, key):
    match = re.search(r"\b" + re.escape(key) + r"\s*=\s*<([^>]+)>", text)
    if not match:
        raise ValueError("missing DTS property: " + key)
    values = [int(x, 0) for x in match[1].split()]
    return values[0] if len(values) == 1 else values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/scratch/eygao/iris-cy"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    snapshots, patches = out / "evidence", out / "patches"
    snapshots.mkdir(parents=True, exist_ok=True)
    patches.mkdir(exist_ok=True)
    repositories = {}
    for name, rel in {
        "chipyard": ".", "saturn": "generators/saturn", "rocket-chip": "generators/rocket-chip",
        "shuttle": "generators/shuttle", "testchipip": "generators/testchipip",
        "spike_chipyard_pin": "toolchains/riscv-tools/riscv-isa-sim", "firesim": "sims/firesim",
    }.items():
        repo = root / rel
        commit = git(repo, "rev-parse", "HEAD").decode().strip()
        if not re.fullmatch("[0-9a-f]{40}", commit):
            raise ValueError("invalid full commit for " + name)
        diff = git(repo, "diff", "--binary", "HEAD", "--")
        patch_file = patches / (name + ".patch")
        patch_file.write_bytes(diff)
        repositories[name] = {
            "local_path": str(repo), "commit": commit,
            "tracked_modified": bool(diff), "tracked_diff_sha256": sha256(diff),
            "tracked_diff": str(patch_file.relative_to(out)),
            "untracked_files_included": False,
        }
        if rel != ".":
            declared = git(root, "ls-tree", "HEAD", "--", rel).decode().strip().split()
            if len(declared) >= 3 and declared[0] == "160000":
                repositories[name]["chipyard_declared_commit"] = declared[2]
                repositories[name]["checkout_matches_chipyard_pin"] = commit == declared[2]

    sources = {}

    def source(identity, rel, repo="chipyard", snapshot=True):
        path = root / rel
        content = path.read_bytes()
        record = {
            "path": rel, "repository": repo,
            "repository_commit": repositories[repo]["commit"],
            "sha256": sha256(content),
            "source_state": "local-working-tree" if repositories[repo]["tracked_modified"] else "tracked-clean-repository-or-generated-artifact",
        }
        if snapshot:
            local = snapshots / (identity + path.suffix)
            local.write_bytes(content)
            record["snapshot"] = str(local.relative_to(out))
        sources[identity] = record
        return content.decode()

    config = source("iris-config", "generators/chipyard/src/main/scala/config/IrisConfigs.scala")
    source("firesim-target-config", "generators/firechip/chip/src/main/scala/TargetConfigs.scala")
    source("matrix-config-decode", "generators/rocket-chip/src/main/scala/rocket/Matrix.scala", "rocket-chip")
    source("saturn-decode", "generators/saturn/src/main/scala/insns/Instructions.scala", "saturn")
    source("saturn-parameters", "generators/saturn/src/main/scala/common/Parameters.scala", "saturn")
    source("outer-product-unit", "generators/saturn/src/main/scala/exu/OuterProductUnit.scala", "saturn")
    source("outer-product-sequencer", "generators/saturn/src/main/scala/backend/OuterProductSequencer.scala", "saturn")
    source("shuttle-parameters", "generators/shuttle/src/main/scala/common/Parameters.scala", "shuttle")
    source("shuttle-config", "generators/shuttle/src/main/scala/common/Configs.scala", "shuttle")
    source("boot-config", "generators/chipyard/src/main/scala/config/fragments/PeripheralFragments.scala")
    source("boot-address-register", "generators/testchipip/src/main/scala/boot/BootAddrReg.scala", "testchipip")
    source("boot-rom", "generators/testchipip/bootrom/bootrom.S", "testchipip")
    source("boot-rom-disassembly", "generators/testchipip/bootrom/bootrom.rv64.dump", "testchipip")
    source("memmap-permissions", "generators/rocket-chip/src/main/scala/tilelink/Parameters.scala", "rocket-chip")
    stem = "sims/firesim-staging/generated-src/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig"
    dts = source("firesim-dts", stem + ".dts")
    memmap = json.loads(source("firesim-memmap", stem + ".memmap.json"))
    l2 = json.loads(source("firesim-l2", stem + ".l2.json"))
    source("firesim-clocks", stem + ".firesimRationalClockBridge.freq-summary")

    def fact(value, identity, lines, state="elaboration-evidence"):
        return {"value": value, "evidence": {"source": identity, "lines": lines}, "status": state}

    harts = []
    for hart in range(3):
        text, lines = node(dts, "cpu@" + str(hart))
        isa = re.search(r'riscv,isa\s*=\s*"([^"]+)"', text)
        compatible = re.search(r'compatible\s*=\s*"([^"]+)"', text)
        if not isa or not compatible:
            raise ValueError("missing hart ISA/type")
        data = {"hart_id": numeric(text, "reg"), "compatible": compatible[1], "isa": isa[1]}
        for prefix in ("i", "d"):
            size, sets, block = [numeric(text, prefix + "-cache-" + key) for key in ("size", "sets", "block-size")]
            if size % (sets * block):
                raise ValueError("nonintegral cache associativity")
            data[prefix + "cache"] = {"size_bytes": size, "sets": sets, "block_bytes": block, "ways": size // (sets * block)}
        harts.append(fact(data, "firesim-dts", lines))

    memory_regions = []
    for region in memmap["mapping"]:
        for i, base in enumerate(region["base"]):
            memory_regions.append({"name": region["names"][i], "base": base, "size_bytes": region["size"][i],
                                   **{key: region[key][i] for key in ("r", "w", "x", "c", "a")}})
    if not all(len(bank["setBits"]) == 9 and bank["ways"] == 4 and bank["blockBytes"] == 64 for bank in l2["banks"]):
        raise ValueError("L2 geometry differs from audited design")
    l2_size = sum((1 << len(bank["setBits"])) * bank["ways"] * bank["blockBytes"] for bank in l2["banks"])

    # Locate the constant in generated FIRRTL instead of assuming Rocket's default.
    fir_path = root / (stem + ".fir")
    reset_hits = []
    with fir_path.open() as inp:
        for line_number, line in enumerate(inp, 1):
            match = re.search(r"connect bootROMResetVectorSourceNodeOut, UInt<\d+>\(0h([0-9a-fA-F]+)\)", line)
            if match:
                reset_hits.append((line_number, int(match[1], 16), line.rstrip()))
    if len(reset_hits) != 1:
        raise ValueError("ambiguous or missing elaborated boot reset vector")
    # Large FIRRTL stays external; retain a hash of its full bytes and the exact cited line.
    fir_hash = hashlib.sha256()
    with fir_path.open("rb") as inp:
        for block in iter(lambda: inp.read(1024 * 1024), b""):
            fir_hash.update(block)
    sources["firesim-fir"] = {"path": stem + ".fir", "repository": "chipyard", "repository_commit": repositories["chipyard"]["commit"], "sha256": fir_hash.hexdigest(), "artifact_build_revision": None, "excerpt": reset_hits[0][2]}

    facts = {
        "harts": harts,
        "memory_map": fact(memory_regions, "firesim-memmap", [1, 1]),
        "memory_map_permission_fields": fact({"r": "Get or AcquireB", "w": "PutFull or AcquireT", "x": "executable", "c": "AcquireB", "a": "Arithmetic and Logical atomic support"}, "memmap-permissions", [252, 258], "source-derived"),
        "mtime_hz": fact(numeric(dts, "timebase-frequency"), "firesim-dts", [14, 17]),
        "reset_vector": fact(reset_hits[0][1], "firesim-fir", [reset_hits[0][0], reset_hits[0][0]]),
        "default_program_boot_address": fact(0x80000000, "boot-address-register", [12, 14], "source-derived"),
        "l2": fact({"banks": len(l2["banks"]), "capacity_bytes": l2_size, "ways": 4, "block_bytes": 64, "sets_per_bank": 512, "subbank_width_bytes": [b["subbanks"]["widthBytes"] for b in l2["banks"]]}, "firesim-l2", [1, 1]),
        "compute_vlen_dlen_bits": fact([256, 128], "iris-config", [284, 290], "source-derived"),
        "rocket_vlen_dlen_bits": fact([256, 256], "iris-config", [277, 279], "source-derived"),
        "tcm_banks": fact(2, "iris-config", [291, 292], "source-derived"),
        "scratchpad_banks": fact(2, "iris-config", [222, 228], "source-derived"),
        "tile_edge_formula": fact("VLEN / 8", "saturn-parameters", [408, 408], "source-derived"),
        "tile_register_count": fact(4, "outer-product-unit", [19, 25], "source-derived"),
        "tile_storage_reset": fact("uninitialized Reg storage; software must initialize before reading", "outer-product-unit", [70, 78], "source-derived"),
        "tile_discard_behavior": fact("no-op", "outer-product-sequencer", [29, 38], "source-derived"),
        "serial_tl_iris_link_bits": fact({"phit": 16, "flit": 16}, "firesim-target-config", [417, 430], "source-derived"),
        "serial_tl_bringup_clock_mhz": fact(100, "firesim-target-config", [458, 466], "source-derived"),
    }
    manifest = {
        "schema_version": 1, "hardware_id": "IrisFiresimNOCflushCombinedConfig-local-elaboration",
        "certified": False, "calibration_usable": False,
        "artifact_source_association": "unverified: elaboration files are local evidence, not proven build inputs for deployed image",
        "repositories": repositories, "sources": sources, "facts": facts,
        "unknowns": {
            "deployed_bitstream_sha256": None, "bitstream_build_input_digests": None,
            "elaboration_build_input_digests": None, "calibrated_timing_parameters": None,
            "shuttle_pipeline_issue_restrictions": None, "branch_predictor_parameters": None,
            "tcm_access_latency": None, "scratchpad_access_latency": None, "dram_model_parameters": None,
            "serial_tl_transaction_latency_and_effective_bandwidth": None,
            "per_hart_clock_assignment": None,
        },
        "notes": [
            "Do not infer target frequency from host FPGA execution throughput (e.g. 60 MHz).",
            "DTS clock-frequency=0 on CPU nodes is not a measured hart frequency.",
            "Scratchpad DTS status=disabled prevents automatic OS RAM use; memmap still declares addressable R/W/X storage.",
            "Source-dependent facts are provisional until bound to exact image build inputs.",
            "Global patch digests cover tracked modifications only; explicit evidence snapshots bind individual files.",
            "Chipyard Spike pin predates referenced Zvt addition; functional-model Spike revision must be recorded separately.",
        ],
    }
    destination = out / "manifest.json"
    destination.write_text(json.dumps(manifest, indent=2) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
