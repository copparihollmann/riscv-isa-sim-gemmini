"""Validate saved evidence before consuming architecture facts or calibration."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha256_file(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify(manifest_path):
    manifest_path = Path(manifest_path)
    base = manifest_path.parent.resolve()
    manifest = json.loads(manifest_path.read_text())
    for name, repository in manifest["repositories"].items():
        if not re.fullmatch(r"[0-9a-f]{40}", repository["commit"]):
            raise ValueError("full commit identity missing: " + name)
        patch = (base / repository["tracked_diff"]).resolve()
        if base not in patch.parents:
            raise ValueError("patch outside evidence directory")
        if hashlib.sha256(patch.read_bytes()).hexdigest() != repository["tracked_diff_sha256"]:
            raise ValueError("source patch digest mismatch: " + name)
    source_paths, line_counts, external = {}, {}, []
    for name, source in manifest["sources"].items():
        if "snapshot" in source:
            snapshot = (base / source["snapshot"]).resolve()
            if base not in snapshot.parents:
                raise ValueError("snapshot outside evidence directory")
        else:
            root = Path(manifest["repositories"][source["repository"]]["local_path"]).resolve()
            snapshot = (root / source["path"]).resolve()
            if root not in snapshot.parents:
                raise ValueError("external artifact outside repository")
            external.append(name)
        source_paths[name] = snapshot
        if sha256_file(snapshot) != source["sha256"]:
            raise ValueError("evidence digest mismatch: " + name)
        if source["repository_commit"] != manifest["repositories"][source["repository"]]["commit"]:
            raise ValueError("source repository identity mismatch: " + name)

    def fact(value):
        if isinstance(value, list):
            for item in value: fact(item)
        elif isinstance(value, dict) and "evidence" in value:
            evidence = value["evidence"]
            source = manifest["sources"][evidence["source"]]
            name = evidence["source"]
            if name not in line_counts:
                with source_paths[name].open() as handle:
                    line_counts[name] = sum(1 for _ in handle)
            start, end = evidence["lines"]
            if type(start) is not int or type(end) is not int or start < 1 or end < start or end > line_counts[name]:
                raise ValueError("invalid source line reference: " + evidence["source"])
        else:
            raise ValueError("fact without provenance")
    for value in manifest["facts"].values(): fact(value)
    return {"schema_version": 1, "evidence_integrity": "pass",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "repositories": len(manifest["repositories"]), "sources": len(manifest["sources"]),
            "external_artifacts_verified": external,
            "hardware_certified": manifest["certified"],
            "calibration_usable": manifest["calibration_usable"]}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.manifest), indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, "provenance verification failed: " + str(error) + "\n")


if __name__ == "__main__": main()
