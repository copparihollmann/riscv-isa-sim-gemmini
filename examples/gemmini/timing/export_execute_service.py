"""Export a distinct row-service evaluator, preserving the retained legacy release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from merlin_timing import provider_bundle as B

LEGACY_BRIDGE = "fc4f69d6fbfc70790efd686ad4001d96712cb547f6a47cc3e3a54d50180e55e5"


def specialize_bridge(raw):
    if hashlib.sha256(raw).hexdigest() != LEGACY_BRIDGE:
        raise ValueError(
            "row-service specialization requires the exact reviewed legacy bridge"
        )
    text = raw.decode()
    substitutions = (
        (
            '#include "staged.hpp"',
            '#include "staged.hpp"\n#include "execute_service.hpp"',
        ),
        (
            "std::make_unique<G::StagedObserver>(services_.engine, *inputs.staged,",
            "std::make_unique<G::ExecuteServiceObserver>(G::read_execute_input_service(services_), services_.engine, *inputs.staged,",
        ),
        (
            "std::unique_ptr<G::StagedObserver> staged_;",
            "std::unique_ptr<G::ExecuteServiceObserver> staged_;",
        ),
    )
    for before, after in substitutions:
        if text.count(before) != 1:
            raise ValueError("row-service bridge specialization is ambiguous")
        text = text.replace(before, after)
    return text.encode()


def export(legacy_bundle, destination):
    legacy_bundle, destination = Path(legacy_bundle), Path(destination)
    receipt = B.verify_bundle(legacy_bundle)
    root = Path(__file__).resolve().parent
    payloads = {
        name: (legacy_bundle / name).read_bytes()
        for name in ("provider.hpp", "staged.hpp", "README.md")
    }
    original = (legacy_bundle / "bridge.cpp").read_bytes()
    payloads["legacy_bridge.cpp"] = original
    payloads["bridge.cpp"] = specialize_bridge(original)
    payloads["execute_service.hpp"] = (root / "execute_service.hpp").read_bytes()
    metadata = {
        "schema": "gemmini.execute_service_export.v1",
        "legacy_bundle_manifest_sha256": receipt["manifest_sha256"],
        "legacy_bridge_sha256": LEGACY_BRIDGE,
        "exporter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": "Explicit operand-sensitive WS input rows; legacy counts/dependencies, whole-command resource holds and other prices preserved. No qualification issued.",
    }
    payloads["execute-service-export.json"] = (
        json.dumps(metadata, sort_keys=True, indent=2) + "\n"
    ).encode()
    return B.export_bundle(
        payloads,
        destination,
        entrypoint="bridge.cpp",
        runtime_headers=tuple(receipt["runtime_headers"]),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.legacy_bundle, args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
