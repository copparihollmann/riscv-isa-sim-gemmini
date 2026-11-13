#!/usr/bin/env python3
"""All-row actual-ELF native/reference comparison; no fitting or row filtering."""
import argparse
import collections
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb")as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()
def load(p):return json.loads(Path(p).read_text())
def need(value,why):
    if not value:raise ValueError(why)
def inventory(ids):
    for name,h in ids.items():need(sha(name)==h,"Changed input/output "+name)
def metrics(rows):
    need(rows,"Empty comparison")
    errors=sorted(abs(r["signed_error_percent"])for r in rows)
    return dict(regions=len(rows),median_absolute_error_percent=statistics.median(errors),
        p90_absolute_error_percent=errors[math.ceil(.9*len(errors))-1],
        maximum_absolute_error_percent=errors[-1],
        median_signed_error_percent=statistics.median(r["signed_error_percent"]for r in rows),
        within_2percent=sum(e<=2 for e in errors),
        instret_mismatches=sum(not r["instret_equal"]for r in rows))
def module(path):
    spec=importlib.util.spec_from_file_location("pow2_reference_validator",path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def grouped(rows,fields):
    buckets=collections.defaultdict(list)
    for r in rows:buckets[tuple(r.get(f)for f in fields)].append(r)
    return[{**dict(zip(fields,key)),**metrics(values)}for key,values in
        sorted(buckets.items(),key=lambda item:str(item[0]))]

def main(a):
    run,hardware,out=[x.resolve()for x in(a.run,a.hardware,a.output)]
    need(not out.exists(),"Fresh comparison output")
    rr=load(run/"run.json");hr=load(hardware/"report.json")
    need(rr.get("pass")is True and rr["status"]=="passed_guest_exit"and rr["exit_status"]==0
        and rr["timed_out"]is False,"Actual complete normal native execution required")
    need(hr.get("pass")is True or hr.get("status")=="passed","Successful strict hardware analysis required")
    need(hr["archive_verified"]is True,"Inventory-verified quiescent hardware archive")
    inventory(rr["input_sha256"]);inventory(rr["output_sha256"])
    raw_native=(run/"stdout").read_text()
    corpus=load(hardware/"corpus.json")
    validator_path=ROOT/"benchmarks"/{"scalar":"pow2_scalar_v1","memory":"pow2_memory_v1",
        "matrix":"pow2_matrix_v1"}[a.kind]/"validate.py"
    validator=module(validator_path);validator.validate(raw_native,corpus)
    sw=[json.loads(l.split(" ",1)[1])for l in raw_native.splitlines()if l.startswith("IRIS_REGION ")]
    hw=[json.loads(l)for l in(hardware/"regions.jsonl").read_text().splitlines()]
    need(len(sw)==len(hw)=={"scalar":576,"memory":234,"matrix":132}[a.kind],"Every declared row, no filtering")
    elf=hardware/"observed.elf";need(sha(elf)==rr["ELF_sha256"],"Exact same hardware/native ELF")
    instructions=Instructions(elf,ROOT/"board/evidence/bootrom.rv64.img")
    prefix=[json.loads(l)for l in(run/"features.jsonl").read_text().splitlines()]
    index=collections.defaultdict(list)
    for r in prefix:
        if r["csr"]in(0xb00,0xc00)and r["result_discarded"]is False:
            index[r["hart"],r["value"]].append(r)
    rows=[];joins=[];used=set()
    for s,h in zip(sw,hw):
        need(s["case_id"]==h["case_id"]and type(s["hart"])is int and s["hart"]==h["hart"],"Ordered case/hart equality")
        need(s["pass"]is True and h["pass"]is True and s["checksum"]==h["checksum"]==h["expected_checksum"],"Independent actual golden")
        pair=[]
        for name in("start_cycle","end_cycle"):
            matches=index[s["hart"],s[name]]
            need(len(matches)==1,"Unique actual cycle-CSR endpoint")
            event=matches[0];key=(event["hart"],event["sequence"])
            need(key not in used and event["raw"]==instructions.read(event["pc"]),"Actual CSR/ELF ownership")
            used.add(key);pair.append(event)
        need(pair[0]["sequence"]<pair[1]["sequence"]and pair[0]["read_cycle"]<pair[1]["read_cycle"],"Forward actual endpoints")
        sc=s["end_cycle"]-s["start_cycle"];hc=h["end_cycle"]-h["start_cycle"]
        need(sc>0 and hc>0,"Positive actual measured region")
        row={k:h[k]for k in("case_id","hart","trial_id","internal_split")}
        for field in("footprint_bytes","pass_index","n","m","k","dtype","kind","kind_index"):
            if field in h:row[field]=h[field]
        row.update(native_cycles=sc,hardware_cycles=hc,signed_error_percent=100*(sc-hc)/hc,
            native_instret=s["instret_delta"],hardware_instret=h["instret_delta"],
            instret_equal=s["instret_delta"]==h["instret_delta"],
            native_global_CSR_read_span=pair[1]["read_cycle"]-pair[0]["read_cycle"])
        for label,source in[("native",s),("hardware",h)]:
            ticks=source["mtime_after"]-source["mtime_before"];need(ticks>=0,"Forward source CLINT")
            row[label+"_CLINT_enclosing_ticks"]=ticks
            row[label+"_CLINT_enclosing_core_cycle_bounds"]=[max(0,ticks*1000-1000),ticks*1000+1000]
        delta={}
        for path in set(pair[0].get("memory",{}))|set(pair[1].get("memory",{})):
            begin=pair[0].get("memory",{}).get(path,{})
            end=pair[1].get("memory",{}).get(path,{})
            delta[path]={k:end.get(k,0)-begin.get(k,0)for k in set(begin)|set(end)}
            need(all(type(v)is int and v>=0 for v in delta[path].values()),"Forward accepted-intent counters")
        row["model_memory_prefix_delta"]=delta
        rows.append(row);joins.append(dict(case_id=s["case_id"],hart=s["hart"],
            begin_sequence=pair[0]["sequence"],end_sequence=pair[1]["sequence"],
            begin_PC=pair[0]["pc"],end_PC=pair[1]["pc"],
            begin_raw=pair[0]["raw"],end_raw=pair[1]["raw"]))
    out.mkdir(parents=True)
    (out/"regions.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n"for r in rows))
    (out/"CSR-joins.json").write_text(json.dumps(joins,indent=2)+"\n")
    groups={"by_hart":grouped(rows,["hart"]),"by_partition":grouped(rows,["internal_split"])}
    fields={"memory":["footprint_bytes","hart","pass_index"],"scalar":["kind","hart","n"],
        "matrix":["m","n","k","dtype","hart"]}[a.kind]
    groups["by_shape_hart"]=grouped(rows,fields)
    if a.kind=="scalar":groups["by_kind"]=grouped(rows,["kind"])
    if a.kind=="memory":groups["by_size"]=grouped(rows,["footprint_bytes"])
    if a.kind=="matrix":groups["by_dtype"]=grouped(rows,["dtype"])
    (out/"groups.json").write_text(json.dumps(groups,indent=2)+"\n")
    files=[Path(__file__).resolve(),validator_path,run/"run.json",run/"stdout",run/"features.jsonl",
        hardware/"report.json",hardware/"corpus.json",hardware/"regions.jsonl",elf]
    report=dict(schema="iris.actual_pow2_native_hardware_comparison.v1",**{"pass":True},
        kind=a.kind,all_regions_retained=True,normal_native_exit_verified=True,ELF_sha256=sha(elf),
        actual_CSR_ELF_endpoints=len(used),overall=metrics(rows),partitions=groups["by_partition"],
        accuracy_2percent_certified=False,parameters_refit=False,
        reserved_hardware_labels_owner="root; no fit or parameter selection on reserved results",
        CLINT_scope="Enclosing windows include sampling overhead; +/-1000 core cycles per window; not exact ROI equality or absolute hart-origin alignment",
        cycle_sums_are_not_end_to_end=True,source_image_association_verified=False,
        actual_native_host_seconds=rr.get("host_seconds"),input_sha256={str(p):sha(p)for p in files},
        output_sha256={p.name:sha(p)for p in out.iterdir()if p.is_file()},hardware_contacted=False)
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"pass":True,"overall":report["overall"],"partitions":report["partitions"]}))

if __name__=="__main__":
    p=argparse.ArgumentParser(__doc__);p.add_argument("--kind",choices=["memory","scalar","matrix"],required=True)
    p.add_argument("--run",type=Path,required=True);p.add_argument("--hardware",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True);main(p.parse_args())
