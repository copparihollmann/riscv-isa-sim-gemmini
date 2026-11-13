#!/usr/bin/env python3
"""Actual guarded v1 delegation and independent v2 observer checks."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from iris_model.source_profile_run_v2 import run
from iris_model.source_event_profile_v2 import sha


def main():
    out = ROOT/"build/source-profile-v2-frontend-controls-v1"
    out.mkdir()
    model = ROOT/"build/C12-source-composite-Merlin-adapter-package-v1/source_compute/manifest.json"
    elf = ROOT/"build/source-profile-smoke-guest-v1/guest.elf"
    old = ROOT/"build/source-profile-frontend-controls-v2/ON"
    files = [Path(__file__).resolve(), model, elf, ROOT/"iris_model/source_profile_run_v1.py",
             ROOT/"iris_model/source_event_profile_v1.py", ROOT/"iris_model/source_profile_run_v2.py",
             ROOT/"iris_model/source_event_profile_v2.py"]
    inputs = {str(p):sha(p) for p in files}
    checks = []

    def check(name, condition):
        if not condition:
            raise ValueError(name)
        checks.append(dict(name=name, **{"pass":True}))

    normal = run(elf,model,out/"normal",90,0)
    check("actual normal guarded threehart execution and v2 profile", normal["pass"] and normal["profile_pass"])
    new = out/"normal/execution-v1"
    for name in ("stdout","stderr","features.jsonl","native-summary.json","source-events.jsonl"):
        check("frozen v1 actual sameELF byte parity "+name, (new/name).read_bytes()==(old/name).read_bytes())
    text=(new/"stdout").read_text()
    rows=[json.loads(l.split(" ",1)[1]) for l in text.splitlines() if l.startswith("IRIS_REGION ")]
    check("independent all136words and full footer",len(rows)==3 and all(r["pass"] is True and r["failed"]==0 and r["hart"]==h and r["vl"]==(64 if h<2 else 8) and r["checksum"]==(64*0x42000000 if h<2 else 8*35) for h,r in enumerate(rows)) and text.endswith("IRIS_SOURCE_PROFILE_DONE 0\n"))
    summary=json.loads((out/"normal/source-profile-v2/summary.json").read_text())
    fadd=[r for r in summary["whole_program"] if r["unit"]=="FADD"]
    check("64authoritativeCOM and1024actualsourcewrites",sum(r["checked_COM_commands"]for r in fadd)==64 and sum(r["complete_publication_groups"]for r in fadd)==1024 and sum(r["actual_completed_logical_work"]for r in fadd)==4096)
    check("sourceperfunction without physical inference",len(summary["per_function"])==2 and all(r["function"]=="source_fadd_body" and r["complete_publication_groups"]==512 and r["physical_utilization"]is False for r in summary["per_function"]))
    check("threeactualCSRregions",len(summary["regions"])==3 and [sum(v["complete_publication_groups"]for v in r["source_completed_work"])for r in summary["regions"]]==[512,512,0])
    check("unknown physical quantities staynull",summary["physical_bandwidth"]is None and summary["physical_roofline"]is None and summary["busy_and_age"]["OPU_numeric_pipe_valid_union_global_cycles"]is None and summary["source_image_attested"]is False)
    prior=ROOT/"build/C12-source-composite-compute-launcher-gates-v1"
    fatal=run(prior/"fatal1.elf",model,out/"fatal-h1",15,0)
    check("delegated actual fatal-aware refusal",not fatal["pass"] and not fatal["v1_execution_pass"] and "IRIS_FATAL hart=1" in(out/"fatal-h1/execution-v1/stderr").read_text())
    bad=out/"changed-model.json"
    record=json.loads(model.read_text());record["native_binary_sha256"]="0"*64;bad.write_text(json.dumps(record))
    refusal=run(elf,bad,out/"bad-model",15,0)
    checked=json.loads((out/"bad-model/execution-v1/run.json").read_text())
    check("changed model refused before launch",not refusal["pass"] and "pid"not in checked)
    timeout=run(elf,model,out/"timeout",.05,0)
    timed=json.loads((out/"timeout/execution-v1/run.json").read_text())
    check("v1ownedtimeout remainsfailed",not timeout["pass"] and timed["timed_out"] is True)
    try:
        os.killpg(timed["pid"],0)
    except ProcessLookupError:
        check("ownedprocessgroupabsent",True)
    else:
        raise ValueError("Timed out native group remains alive")
    check("frozen v1/provider/model/ELF bytesunchanged",all(sha(Path(p))==h for p,h in inputs.items()))
    report=dict(schema="iris.source_profile_v2_frontend_checks.v1",**{"pass":True},checks=checks,
                native_execution_delegates_unchanged_v1=True,independent_words=136,
                newprofile_does_not_change_execution=True,source_native_policy_changed=False,
                hardware_or_labels_or_fit_used=False,input_sha256=inputs,
                output_sha256={str(p):sha(p) for p in out.rglob("*") if p.is_file()})
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"pass":True,"checks":len(checks),"report_sha256":sha(out/"report.json")}))


if __name__=="__main__":
    main()
