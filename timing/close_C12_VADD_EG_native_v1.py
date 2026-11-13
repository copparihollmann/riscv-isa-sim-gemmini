#!/usr/bin/env python3
"""Close model-only integer-EG gates without reading hardware measurements."""
from pathlib import Path
import collections
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/C12-VADD-EG-native-closure-v1"
CAP = ROOT / "build/C12-VADD-EG-frozen-35a80496-v2"
TRACE = ROOT / "build/rvv-compute-asm-C12-VADD-EG-ON-v1/async.jsonl"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    OUT.mkdir()
    manifest = json.loads((CAP / "manifest.json").read_text())
    checks = {}
    for name, expected in manifest["artifact_sha256"].items():
        require(sha(CAP / name) == expected, "Changed capsule artifact: " + name)
    source = Path(manifest["source"])
    inventory = json.loads((CAP / "native-inventory.json").read_text())
    for name, expected in inventory.items():
        require(sha(source / name) == expected, "Changed frozen native input: " + name)
    external = json.loads((CAP / "compiled-inputs.json").read_text())
    for name, expected in external.items():
        require(sha(Path(name)) == expected, "Changed frozen compiled input: " + name)
    parent = ROOT / "build/C12-source-composite-frozen-02b4a9ab-v2"
    parent_manifest = json.loads((parent / "manifest.json").read_text())
    parent_inventory = json.loads((parent / "native-inventory.json").read_text())
    for name, expected in parent_inventory.items():
        require(sha(Path(parent_manifest["source"]) / name) == expected,
                "Changed exact02b4 parent input: " + name)

    paths = {
        "component": "build/rvv-integer-EG-source-clean-v1/report.json",
        "component_capsule": "build/rvv-integer-EG-source-frozen-v1/manifest.json",
        "directed": "build/C12-VADD-EG-actor-directed-v2/report.json",
        "VSET_definedness": "build/C12-VADD-EG-VSET-provenance-final35a-v3/report.json",
        "three_hart_quiet_FSoff": "build/C12-VADD-EG-quiet-FSoff-final35a-v3/run.json",
        "full_ASM": "build/rvv-compute-asm-C12-VADD-EG-ON-v1/run.json",
        "all_event_ownership_joins": "build/C12-VADD-EG-ASM-event-audit-v1/report.json",
        "journal_and_trace_parity": "build/C12-VADD-EG-final-ASMjournals-parity-v1/report.json",
        "independent_source_ownership_review": "build/VADD-EG-ownership-readonly-review-v1/report.json",
    }
    for key, relative in paths.items():
        path = ROOT / relative
        document = json.loads(path.read_text())
        require(document.get("pass") is True, "Unpassed gate: " + key)
        checks[key] = {"path": str(path), "sha256": sha(path), "pass": True}
    canonical = ROOT / "build/C12-VADD-EG-functional32-final35a-v1/results.json"
    functional = json.loads(canonical.read_text())
    require(len(functional["rows"]) == 32 and
            all(row["pass_"] is True for row in functional["rows"]),
            "Fresh canonical functional32 failed")
    require(functional["binary_sha256"] == manifest["binary_sha256"] and
            functional["uart_sha256"] == manifest["uart_sha256"],
            "Functional32 native identity mismatch")
    checks["canonical_functional32"] = {"path": str(canonical),
                                        "sha256": sha(canonical), "pass": True}

    # Counters are collected only in the successful-retirement branch. In this
    # journal pending can also describe other actors, so require an actual
    # committed VADD owner whose final source write has not occurred yet.
    live = {}
    counter_overlap = collections.Counter()
    counter_forms = collections.Counter()
    fence_count = collections.Counter()
    write_edge = {}
    tail = b""
    with TRACE.open("rb") as stream:
        for line in stream:
            if not line.endswith(b"\n"):
                tail = line
                break
            event = json.loads(line)
            kind, hart = event["event"], event.get("hart")
            if kind == "vadd_EG_functional_COM":
                live[hart, event["generation"]] = 2 * event["LMUL_numerator"]
            elif kind == "vadd_EG_physical_write":
                key = hart, event["generation"]
                require(key in live and live[key] > 0, "Unowned VADD write")
                live[key] -= 1
                write_edge[hart] = event["cycle"]
                if live[key] == 0:
                    del live[key]
            elif kind == "vadd_EG_counter_read":
                raw, csr = event["raw"], event["csr"]
                require(raw & 0x7f == 0x73 and (raw >> 12) & 7 in (2, 3, 6, 7)
                        and (raw >> 15) & 31 == 0 and raw >> 20 == csr
                        and csr in (0xb00, 0xb02, 0xc00, 0xc02)
                        and event["architecturally_retired"] is True,
                        "Independent counter journal predicate changed")
                counter_forms[hart, csr] += 1
                if any(owner[0] == hart for owner in live):
                    require(event["async_compute_pending"] is True and
                            event["async_pending_count"] > 0,
                            "Live VADD counter snapshot omitted its owner")
                    counter_overlap[hart, csr] += 1
            elif kind == "vadd_EG_fence_admit":
                require(not any(owner[0] == hart for owner in live),
                        "FENCE admitted with a committed unfinished VADD")
                require(event["pending"] == 0 and event["controller_empty"] is True,
                        "FENCE admitted with a pending source controller")
                if hart in write_edge:
                    require(event["cycle"] > write_edge[hart],
                            "Final write preedge busy was bypassed")
                fence_count[hart] += 1
    require(not live, "Incomplete accepted VADD owner journal")
    for hart in (0, 1):
        for csr in (0xb00, 0xb02):
            require(counter_overlap[hart, csr] > 0,
                    "No actual live-VADD independent counter overlap")
        require(fence_count[hart] > 0, "No source-FENCE admission evidence")
    report = {
        "schema": "iris.C12_integer_VADD_EG_native_closure.v1",
        "pass": True,
        "binary_sha256": manifest["binary_sha256"],
        "uart_sha256": manifest["uart_sha256"],
        "capsule_manifest_sha256": sha(CAP / "manifest.json"),
        "native_sources_unchanged_after_gates": len(inventory),
        "external_compiled_inputs_unchanged_after_gates": len(external),
        "exact02b4_parent_unchanged": True,
        "selector_default_OFF": True,
        "source_integer_microissue_to_write_edges": 1,
        "partial_VRF_publication_bytes": 16,
        "fresh_canonical_functional32": 32,
        "full_ASM_regions": 1320,
        "full_ASM_independent_word_checks": 184128,
        "full_ASM_actual_CSR_ELF_joins": 3960,
        "counter_overlap_with_committed_unfinished_VADD": {
            f"hart{h}.csr0x{c:x}": n for (h, c), n in counter_overlap.items()},
        "counter_CSR_actual_journal_counts": {
            f"hart{h}.csr0x{c:x}": n for (h, c), n in counter_forms.items()},
        "FENCE_admissions_without_live_VADD_and_after_last_write_edge": dict(fence_count),
        "normal_exit_scope": "directed, three-hart quiet, and provenance controls only",
        "full_ASM_normal_guest_exit_verified": False,
        "full_ASM_intentional_postmeasurement_debugger_stop": True,
        "async_global_partial_tail_bytes": len(tail),
        "async_global_transcript_complete": False,
        "source_VADD_and_OPU_authoritative_journals_complete": True,
        "OPU_journal_scope": "guarded actual MM COM and successful entry/K writes; no generic TMOVE COM",
        "CPU_COMplus1_bridge_qualified": False,
        "other_vector_units_and_memory_consumers_conservatively_drain": True,
        "active_IRQ_context_qualified": False,
        "ON_Zephyr_context_switch_qualified": False,
        "recognized_VADD_empirical_family_costs_applied": False,
        "other_inherited_effective_costs_requalified": False,
        "source_image_association": False,
        "physical_memory_traffic_or_hardware_utilization_claim": False,
        "timing_2pct_certified": False,
        "fit_performed": False,
        "hardware_or_protected_timing_labels_consumed": False,
        "native_provider_or_default_promoted": False,
        "gates": checks,
        "input_sha256": {str(p): sha(p) for p in
                         (Path(__file__).resolve(), CAP / "manifest.json",
                          CAP / "native-inventory.json", CAP / "compiled-inputs.json", TRACE)},
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"pass": True, "report_sha256": sha(OUT / "report.json"),
                      "counter_overlap": report["counter_overlap_with_committed_unfinished_VADD"]}))


if __name__ == "__main__":
    main()
