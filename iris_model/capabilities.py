"""Query source-backed Iris datatype capabilities without inferring model support."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def load_verified(path):
    path = Path(path)
    base = path.parent.resolve()
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or data.get("scope") != "hardware-source-audit":
        raise ValueError("unsupported capability schema")
    counts = {}
    for name, source in data["sources"].items():
        snapshot = (base / source["snapshot"]).resolve()
        if base not in snapshot.parents:
            raise ValueError("capability evidence outside its directory")
        raw = snapshot.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("capability source digest mismatch: " + name)
        commit = source["commit"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("full source revision required")
        if commit != data["repositories"][source["repository"]]["commit"]:
            raise ValueError("capability repository mismatch: " + name)
        counts[name] = len(raw.splitlines())
    ids = set()
    for row in data["capabilities"]:
        if row["id"] in ids:
            raise ValueError("duplicate capability identity")
        ids.add(row["id"])
        if type(row["hart"]) is not int or row["hart"] not in (0, 1, 2):
            raise ValueError("invalid capability hart")
        if row["unit"] not in ("scalar", "vector", "vme"):
            raise ValueError("invalid unit")
        if row["status"] not in ("configured", "not_configured", "unverified"):
            raise ValueError("invalid capability status")
        if not row["evidence"]:
            raise ValueError("capability without evidence")
        for evidence in row["evidence"]:
            start, end = evidence["lines"]
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= counts[evidence["source"]]:
                raise ValueError("invalid capability evidence lines")
    return data


def query(data, hart, unit=None, dtype=None, operation=None, role="any"):
    if type(hart) is not int or hart not in (0, 1, 2):
        raise ValueError("invalid hart")
    if role not in ("any", "input", "output", "accumulator"):
        raise ValueError("invalid dtype role")
    rows = []
    for row in data["capabilities"]:
        if row["hart"] != hart or (unit is not None and row["unit"] != unit):
            continue
        types = []
        if role in ("input", "any"): types += row["input_types"]
        if role in ("output", "any"): types += row["output_types"]
        if role in ("accumulator", "any") and row["accumulator_type"]:
            types.append(row["accumulator_type"])
        if dtype is not None and dtype not in types:
            continue
        if operation is not None and operation not in row["operations"]:
            continue
        rows.append(row)
    statuses = {row["status"] for row in rows}
    decision = "requires_operation" if operation is None else (
        "configured" if "configured" in statuses else
        "unverified" if "unverified" in statuses else
        "not_configured" if "not_configured" in statuses else "unknown")
    return {"schema_version": 1, "hart": hart, "unit": unit, "dtype": dtype,
            "dtype_role": role, "operation": operation, "matches": rows,
            "configured_match_exists": any(row["status"] == "configured" for row in rows),
            "operation_support_decision": decision,
            "bitstream_match_verified": data["bitstream_match_verified"],
            "simulator_support": "not_inferred; consult simulator certification separately",
            "interpretation": "Capabilities apply only to the listed operation groups; a dtype name is not a blanket arithmetic guarantee."}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "hardware/dtypes.json")
    parser.add_argument("--hart", type=int, choices=(0, 1, 2), required=True)
    parser.add_argument("--unit", choices=("scalar", "vector", "vme"))
    parser.add_argument("--dtype")
    parser.add_argument("--role", choices=("any", "input", "output", "accumulator"), default="any")
    parser.add_argument("--operation")
    args = parser.parse_args()
    try:
        result = query(load_verified(args.manifest), args.hart, args.unit, args.dtype, args.operation, args.role)
        print(json.dumps(result, indent=2))
        return 0 if result["configured_match_exists"] else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, "capability query failed: " + str(error) + "\n")


if __name__ == "__main__": raise SystemExit(main())
