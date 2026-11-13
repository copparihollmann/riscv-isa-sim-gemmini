#!/usr/bin/env python3
"""Consumer controls using complete owners copied from the frozen35a journal."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from iris_model.source_event_profile_v2 import (Instructions, bound_execution,
    capacity_records, clocks, conditional_fraction, parse_journal, region_bounds, sha, validate_prefixes)

OUT = ROOT / "build/source-event-profile-v2-controls-v7"
RUN = ROOT / "build/rvv-compute-asm-C12-VADD-EG-ON-v1"
ELF = ROOT / "build/rvv-compute-asm-v5/guest.elf"
ROM = ROOT / "board/evidence/bootrom.rv64.img"


def main():
    OUT.mkdir()
    frozen_sources={str(p):sha(p) for p in (ROOT/"iris_model/source_event_profile_v2.py",Path(__file__).resolve())}
    code = Instructions(ELF, ROM)
    selected, end = {}, {}
    canceled = None
    for line in (RUN / "async.jsonl").open("rb"):
        if not line.endswith(b"\n"):
            break
        e = json.loads(line)
        kind = e["event"]
        if kind in ("vadd_EG_functional_COM", "fadd_EG_functional_COM"):
            unit = "VADD" if kind.startswith("vadd") else "FADD"
            selected.setdefault(unit, (e["hart"], e["generation"]))
        elif kind == "vadd_EG_wrongpath_cancel" and canceled is None:
            canceled = e["hart"], e["generation"]
        elif kind == "opu_functional_COM" and e["TK"] == 4:
            selected.setdefault("OPU", (e["hart"], e["instruction"]))
        for unit, key in selected.items():
            if ((unit in ("VADD", "FADD") and kind == unit.lower()+"_EG_physical_write" and
                 (e["hart"], e["generation"]) == key) or
                (unit == "OPU" and kind == "opu_K_write_owner" and (e["hart"], e["instruction"]) == key)):
                end[unit] = e["cycle"]
    assert set(selected) == {"VADD", "FADD", "OPU"} and canceled is not None
    records = []
    for line in (RUN / "async.jsonl").open("rb"):
        if not line.endswith(b"\n"):
            break
        e = json.loads(line)
        k = e["event"]
        keep = False
        if k.startswith(("vadd_EG_", "fadd_EG_")) and "generation" in e:
            unit = "VADD" if k.startswith("vadd") else "FADD"
            key = e["hart"], e["generation"]
            keep = key == selected[unit] or (unit == "VADD" and key == canceled)
        elif k.startswith("opu_") and "instruction" in e:
            keep = (e["hart"], e["instruction"]) == selected["OPU"]
        if keep:
            records.append(e)
    path = OUT / "complete-real-owners.jsonl"

    def write(p, rows):
        p.write_text("".join(json.dumps(e, separators=(",", ":"))+"\n" for e in rows))

    write(path, records)
    baseline = parse_journal(path, code, [1, 1, 1])
    assert len(baseline["commands"]) == 3 and baseline["canceled"] == 1
    tests = []

    def index(rows, event, condition=lambda e: True):
        return next(i for i,e in enumerate(rows) if e["event"] == event and condition(e))

    def corruption(name, mutate):
        rows = copy.deepcopy(records)
        mutate(rows)
        p = OUT / (name+".jsonl")
        write(p, rows)
        try:
            parse_journal(p, code, [1, 1, 1])
        except (ValueError, KeyError, TypeError) as error:
            tests.append(dict(name=name, refused=True, reason=str(error), input_sha256=sha(p)))
        else:
            raise AssertionError("Accepted corrupted source journal: " + name)

    def change(event, field, value, condition=lambda e: True):
        return lambda rows: rows[index(rows, event, condition)].__setitem__(field, value)

    corruption("missing-COM", lambda r: r.pop(index(r, "vadd_EG_functional_COM")))
    corruption("missing-VADD-write", lambda r: r.pop(index(r, "vadd_EG_physical_write")))
    corruption("duplicate-VADD-write", lambda r: r.append(copy.deepcopy(r[index(r, "vadd_EG_physical_write")])))
    corruption("duplicate-OPU-COM", lambda r: r.append(copy.deepcopy(r[index(r, "opu_functional_COM")])))
    def wrong_depth(rows):
        e=rows[index(rows,"vadd_EG_physical_write")]
        e["cycle"]+=3
    corruption("wrong-VADD-depth", wrong_depth)
    corruption("wrong-VADD-publication-bytes", change("vadd_EG_physical_write", "bytes", 32))
    corruption("wrong-VADD-geometry", change("vadd_EG_functional_COM", "VL", 1))
    corruption("wrong-VADD-ELF-raw", change("vadd_EG_functional_COM", "raw", 0))
    def canceled_COM(rows):
        e = copy.deepcopy(rows[index(rows, "vadd_EG_functional_COM")])
        e["hart"], e["generation"] = canceled
        rows.append(e)
    corruption("canceled-owner-actual-COM", canceled_COM)
    corruption("missing-K-write", lambda r: r.pop(index(r, "opu_K_write_owner")))
    corruption("wrong-K-index", change("opu_K_write_owner", "k", 7))
    corruption("wrong-K-last-flag", change("opu_K_write_owner", "last_k", True, lambda e: not e["last_k"]))
    corruption("intermediate-K-final-MRF-projection", change("opu_K_write_owner", "projected_MRF_published", True, lambda e: not e["last_k"]))
    corruption("missing-final-MRF-publication", lambda r: r.pop(index(r, "opu_entry_publish")))
    corruption("missing-K-callback", lambda r: r.pop(index(r, "opu_K_completion")))
    corruption("double-MAC-credit", change("opu_K_write_owner", "macs", 512))
    corruption("float-MAC-credit", change("opu_K_write_owner", "macs", 256.0))
    def wrong_shape(rows):
        e=rows[index(rows,"opu_functional_COM")]
        e["TM"]=32 if e["TM"]==16 else 16
    corruption("wrong-OPU-shape", wrong_shape)
    corruption("wrong-OPU-tile", change("opu_functional_COM", "tile", 2))
    def wrong_family(rows):
        e=rows[index(rows,"opu_functional_COM")]
        e["family"]="vme.fp8" if e["family"]=="vme.int8" else "vme.int8"
    corruption("wrong-OPU-family", wrong_family)
    corruption("unknown-publication-event-namespace",change("vadd_EG_physical_write","event","vadd_EG_unqualified_physical_write"))
    corruption("bool-OPU-COM-geometry",change("opu_functional_COM","SEW",True))
    def duplicate_callback_node(rows):
        hits=[e for e in rows if e["event"]=="opu_microissue_reserved"]
        hits[1]["backend_node"]=hits[0]["backend_node"]
    corruption("duplicate-OPU-callback-node",duplicate_callback_node)
    def malformed_pending(rows):
        rows.append(dict(event="vadd_EG_fence_admit",hart=0,cycle=100000000,last_controller_edge=0,last_preedge_busy=False,pending=False,controller_empty=True))
    corruption("bool-FENCE-pending-count",malformed_pending)
    # Counter metadata is allowed on hart2 and receives no compute work credit.
    metadata = dict(event="fadd_EG_counter_read", hart=2, read_cycle=1, architecturally_retired=True)
    p = OUT / "hart2-counter-metadata.jsonl"
    write(p, records+[metadata])
    assert len(parse_journal(p, code, [1,1,1])["commands"]) == 3
    p = OUT / "disclosed-nonauthoritative-tail.jsonl"
    p.write_bytes(path.read_bytes()+b'{"event":"fadd_EG_fence_admit","pending":')
    assert parse_journal(p, code, [1,1,1])["tail"]
    p = OUT / "unterminated-authoritative-write.jsonl"
    p.write_bytes(path.read_bytes()+b'{"event":"opu_K_write_owner","hart":0')
    try:
        parse_journal(p, code, [1,1,1])
    except ValueError as error:
        tests.append(dict(name="unterminated-authoritative-write", refused=True, reason=str(error)))
    else:
        raise AssertionError("Accepted authoritative partial tail")

    future = OUT/"canceled-future-plan-only.jsonl"
    write(future,[dict(event="vadd_EG_front_reservation",hart=0,generation=999999,pc=0,RRD=100,COM=103,available=104),dict(event="vadd_EG_wrongpath_cancel",hart=0,generation=999999,pc=0,cycle=101)])
    observed=parse_journal(future,code,[1,1,1])
    assert observed["max_cycle"]==101 and observed["commands"]==[], "Planned availability is not an observed clock edge/work completion"
    fraction = conditional_fraction(512, 1, 1, 256)
    assert fraction["fraction_of_conditional_source_ceiling"] == 2 and fraction["inconsistency_fraction_above_one"] is True
    for args in ((True,1,1,256), (1,0,1,256), (1,1,0,256), (1,1,1,0)):
        try:
            conditional_fraction(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid units accepted")
    receipt = RUN / "run.json"
    bound_execution(receipt, RUN/"async.jsonl", RUN/"features.jsonl", RUN/"stdout", ELF,
                    ROOT/"build/C12-VADD-EG-inputs-v2/ON.fixture")
    try:
        bound_execution(receipt, path, RUN/"features.jsonl", RUN/"stdout", ELF)
    except ValueError as error:
        tests.append(dict(name="unbound-journal-receipt", refused=True, reason=str(error)))
    else:
        raise AssertionError("Accepted unbound journal")
    limits = ROOT/"build/throughput-limits-source-v3/report.json"
    bad = OUT/"changed-capacity-report.json"
    obj=json.loads(limits.read_text());obj["geometry"]["opu_macs_per_accepted_array_edge"] = 512
    bad.write_text(json.dumps(obj))
    try:
        capacity_records(bad)
    except ValueError as error:
        tests.append(dict(name="changed-capacity-report", refused=True, reason=str(error)))
    else:
        raise AssertionError("Accepted changed source capacity")
    actual = json.loads((RUN/"regions.jsonl").open().readline())
    endpoint_values = {actual["start_cycle"], actual["end_cycle"]}
    prefix = [json.loads(line) for line in (RUN/"features.jsonl").open()
              if json.loads(line)["hart"] == actual["hart"] and json.loads(line)["value"] in endpoint_values]
    assert len(prefix) == 2
    prefix_path = OUT/"actual-CSR-endpoints.jsonl"
    write(prefix_path,prefix)
    region_map = OUT/"actual-ROI-map.json"
    roi = {k:actual[k] for k in ("case_id","hart","start_cycle","end_cycle")}
    region_map.write_text(json.dumps(dict(schema="iris.source_event_region_map.v1",regions=[roi])))
    assert validate_prefixes(prefix_path,code)==2
    joined,_=region_bounds("",prefix_path,code,region_map,"none")
    assert joined[0]["global_begin"]==actual["begin_global_read_cycle"] and joined[0]["global_end"]==actual["drain_global_read_cycle"]
    for name,mutate in (
        ("ROI-missing-endpoint",lambda p:p.pop()),
        ("ROI-duplicate-CSR",lambda p:p.append(copy.deepcopy(p[-1]))),
        ("ROI-changed-ELF-opcode",lambda p:p[0].__setitem__("raw",0)),
        ("ROI-XLEN-overflow",lambda p:p[0].__setitem__("value",1<<64)),
        ("ROI-bool-destination",lambda p:p[0].__setitem__("destination",True)),
    ):
        changed=copy.deepcopy(prefix);mutate(changed);p=OUT/(name+".jsonl");write(p,changed)
        try:
            validate_prefixes(p,code);region_bounds("",p,code,region_map,"none")
        except (ValueError,KeyError,TypeError) as error:
            tests.append(dict(name=name,refused=True,reason=str(error)))
        else:
            raise AssertionError("Accepted corrupted actual CSR endpoint "+name)
    fixture=ROOT/"build/C12-VADD-EG-inputs-v2/ON.fixture"
    bad_clock=OUT/"conflicting-clock-summary.json"
    bad_clock.write_text(json.dumps(dict(base_clock_hz=1,hart_cycle_dividers=[1,1,1],cycles=1)))
    try:
        clocks(bad_clock,fixture)
    except ValueError as error:
        tests.append(dict(name="conflicting-clock-contract",refused=True,reason=str(error)))
    else:
        raise AssertionError("Accepted contradictory clock contracts")
    p=OUT/"incomplete-owner-event-name.jsonl"
    p.write_bytes(path.read_bytes()+b'{"event":"vadd_EG_physical_')
    try:
        parse_journal(p,code,[1,1,1])
    except ValueError as error:
        tests.append(dict(name="incomplete-owner-event-name",refused=True,reason=str(error)))
    else:
        raise AssertionError("Accepted unknown incomplete source event")
    assert all(sha(Path(p))==h for p,h in frozen_sources.items()), "Consumer/test changed during controls"
    report = dict(schema="iris.source_event_profile_v2_controls.v1", **{"pass":True},
                  actual_complete_owner_types=[r["unit"] for r in baseline["commands"]],
                  actual_OPU_TK=next(r["TK"] for r in baseline["commands"] if r["unit"]=="OPU"),
                  corruption_refusals=tests, fraction_above_one_retained_and_flagged=True,
                  invalid_unit_controls=4, actual_hart2_counter_metadata_not_compute_work=True,
                  partial_nonauthoritative_tail_disclosed=True,
                  actual_CSR_ELF_global_endpoint_joins_verified=True,
                  future_COM_availability_deadlines_not_observed_clock_or_work=True,
                  no_hardware_or_labels_or_fit=True,
                  input_sha256={str(p):sha(p) for p in (Path(__file__).resolve(),
                    ROOT/"iris_model/source_event_profile_v2.py", RUN/"run.json",RUN/"async.jsonl",ELF,ROM,limits,path)})
    (OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"pass":True,"refusals":len(tests),"report_sha256":sha(OUT/"report.json")}))


if __name__ == "__main__":
    main()
