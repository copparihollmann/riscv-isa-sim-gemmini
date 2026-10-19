"""Export pinned public ABI facts and unknown primitive timing parameters."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PARAMS_SHA256 = "3758ae967af3a179497660970201093a7fb624be00173990ce33d3f5c38da924"
ROCC_SHA256 = "08bdaf6f3f6e846125c937f4c19d54ab11efaf3026ffab55aad609e2c6a52eea"
PROFILES = {
    "stock_u250": {
        "libgemmini_revision": "ea8f7ed7afd68e001fb06ddccad9a023c990961d",
        "header_sha256": "e13cde296d0faa650fe558351021628f3e4461525fa85b86bf81d44e66625590",
        "source_sha256": "209c0f4f4bc7c2313655ea36f3742a5eb590988b8ef7958cd74b9f80b5e7fc9f",
        "archive_sha256": "a9a190b9fc26d577b1e8af0e3b46a94c8efaf2976f7fca6650236e0fd6d4eca1",
        "embedded_bitstream_sha256": "6bfb72e3d69d0bed14eaa8db9fd5faf53f82780ef9ecded6b2d49983dfcbc229",
        "rtl_elaboration_source_lineage": "unrecovered_from_archive",
    },
    "fire_aligned_30mhz": {
        "libgemmini_revision": "5b1254a7dc72f757442280e7f28ef30542c78533",
        "header_sha256": "506d6857dd0a02a2921535e1a5725639c0b6374e83a95935426fc9b5c6349ac3",
        "source_sha256": "c468a86deb68cb2e12e3fb1177821075b0eb87e27a37ff835280ee7caf61b13a",
        "archive_sha256": "0af6f26e1cbad1c03f9e5873217505a5100bf2d0d068205cfa486522b24fc603",
        "embedded_bitstream_sha256": None,
        "rtl_elaboration_source_lineage": "009e85b05ca817a15fcd6c3fe4eedd86cc2a3617; historical dirty overlay unproven",
        "chipyard_revision": "009e85b05ca817a15fcd6c3fe4eedd86cc2a3617",
        "gemmini_revision": "63f0b68a68f185a016a2993f2fb32e1661ea9e6c",
        "saturn_revision": "e16a301d261fa4b5a374eb7069b78107a8c9aefb",
        "firesim_revision": "b084672c2f8cf32e55d78f73a001074c23f8a2b8",
        "host_dts_sha256": "c4a2009a405945ea98f731713e0f4e7dc483031ab8cd5156d871e4eb7594f1df",
        "dram_base": 0x80000000,
        "dram_bytes": 16 * (1 << 30),
        "host_isa": "rv64imafdcbzicsr_zifencei_zihpm_zfh_zba_zbb_zbs_xrocket",
    },
}
KINDS = ("config", "preload", "flush", "counter", "fence", "load", "store", "pool_store",
         "normalize1", "normalize2", "normalize3", "normalize4", "normalize5", "normalize6", "normalize7",
         "compute_ws", "compute_os", "compute_ws_relu", "compute_os_relu",
         "store_act1", "store_act2", "store_act3", "store_act4", "pool_store_act1")


def _bound(path: Path, digest: str) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("public source must be an ordinary bounded file")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"public source identity differs: {path.name}")
    return raw


def export(public_library: Path, rocc_header: Path, profile: str = "stock_u250") -> dict:
    selected = PROFILES[profile]
    params = _bound(public_library / "gemmini_params.h", PARAMS_SHA256).decode()
    _bound(public_library / "gemmini.h", selected["header_sha256"])
    source = _bound(public_library / "gemmini.cc", selected["source_sha256"]).decode()
    rocc = _bound(rocc_header, ROCC_SHA256).decode()
    defines = {}
    for line in params.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[0] == "#define":
            defines[fields[1]] = fields[2:]
    for line in rocc.splitlines():
        fields = line.strip().split()
        if len(fields) == 3 and fields[0] == "#define" and fields[1] in {"ROCC_OPCODE3", "ROCC_OPCODE_MASK"}:
            defines[fields[1]] = fields[2:]
    if "push_custom_insn(insns, ROCC_OPCODE3, ROCC_OPCODE_MASK," not in source:
        raise ValueError("public extension dispatch declaration differs")

    def integer(name):
        values = defines[name]
        if len(values) != 1:
            raise ValueError(f"public parameter is not a literal: {name}")
        return int(values[0], 0)

    hardware = {
        "dim": integer("DIM"), "scratchpad_rows": integer("BANK_NUM") * integer("BANK_ROWS"),
        "accumulator_rows": integer("ACC_ROWS"), "element_bytes": 1, "accumulator_bytes": 4,
        "address_bits": integer("ADDR_LEN"),
        "custom_opcode": integer("ROCC_OPCODE3"), "custom_opcode_mask": integer("ROCC_OPCODE_MASK"),
        "first_layer_optimizations": int("HAS_FIRST_LAYER_OPTIMIZATIONS" in defines),
        "full_width_accumulator_readout": int("ACC_READ_FULL_WIDTH" in defines),
        "reset_accumulator_activation": None,
    }
    # The digest binds the exact int8_t/int32_t typedef declarations. These
    # widths describe the selected software ABI, not an unobserved RTL source.
    if "typedef int8_t elem_t;" not in params or "typedef int32_t acc_t;" not in params:
        raise ValueError("public ABI element type declarations differ")
    return {
        "schema": "gemmini.annotated_spike.target.v1",
        "target_config": "FireSimGemminiRocketConfig",
        "provenance": {
            "platform": "xilinx_alveo_u250",
            "archive_sha256": selected["archive_sha256"],
            "embedded_bitstream_sha256": selected["embedded_bitstream_sha256"],
            "generated_params_sha256": PARAMS_SHA256,
            "functional_extension_revision": selected["libgemmini_revision"],
            "public_sources": {"gemmini.h": selected["header_sha256"], "gemmini.cc": selected["source_sha256"]},
            "public_architecture_headers": {"riscv/rocc.h": ROCC_SHA256},
            "hardware_pin_registry": "merlin/contract/hardware_pins.yaml",
            "archive_identity": "operator_verified_pin",
            "rtl_elaboration_source_lineage": selected["rtl_elaboration_source_lineage"],
            **{key: selected[key] for key in ("chipyard_revision", "gemmini_revision", "saturn_revision",
                                              "firesim_revision", "host_dts_sha256", "dram_base",
                                              "dram_bytes", "host_isa") if key in selected},
        },
        "target": {"hardware": hardware,
                   "prices": {**{kind: {"latency_cycles": None, "occupancy_cycles": None,
                                          "latency_per_byte_cycles": None, "occupancy_per_byte_cycles": None,
                                          "latency_per_mac_cycles": None, "occupancy_per_mac_cycles": None}
                                  for kind in KINDS},
                              "dma": {"read_bytes_per_cycle": None, "write_bytes_per_cycle": None}}},
        "resources": {"accelerator." + name: {"capacity": None, "queue_capacity": None}
                      for name in ("config", "load", "store", "execute", "dma_read", "dma_write")},
        "limitations": {
            "local_dependency_granularity": "complete local rows, conservative",
            "physical_queue_capacities": "unknown", "primitive_latencies": "unknown",
            "requested_dma_bytes": "command payload, not physical DRAM transactions",
            "qualification": "unqualified timing until explicit parameters and resources are selected",
        },
    }


def export_bundle(document: dict, destination: Path, profile: str = "stock_u250"):
    from merlin_timing.provider_bundle import RUNTIME_HEADERS, export_bundle as export_sources

    root = Path(__file__).absolute().parent
    payloads = {}
    for name in ("README.md", "bridge.cpp", "provider.hpp", "staged.hpp"):
        path = root / name
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError("provider sources must not be symlinks")
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("provider source must be an ordinary bounded file")
        with path.open("rb") as stream:
            payloads[name] = stream.read(1024 * 1024 + 1)
    payloads[profile + ".json"] = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    return export_sources(payloads, destination, entrypoint="bridge.cpp", runtime_headers=(
        *RUNTIME_HEADERS, "timing/core/include/merlin_timing/reservations.hpp"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-library", type=Path, required=True)
    parser.add_argument("--spike-rocc", type=Path, required=True)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="stock_u250")
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--output", type=Path)
    output.add_argument("--bundle-dir", type=Path)
    args = parser.parse_args()
    document = export(args.public_library, args.spike_rocc, args.profile)
    if args.bundle_dir:
        print(json.dumps(export_bundle(document, args.bundle_dir, args.profile), sort_keys=True))
    else:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("export destination already exists")
        args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
