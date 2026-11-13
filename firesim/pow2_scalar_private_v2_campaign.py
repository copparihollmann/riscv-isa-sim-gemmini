#!/usr/bin/env python3
"""Exact scalar-packet admission, managed preparation and archived analysis."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shlex
import struct
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"firesim"))
from batch_runner import digest,prepare,save_manifest,validate_cases
from prepare_managed_campaign import add_observer,snapshot_inputs
from memory_footprints_wfi_groups_review_v1 import Elf as BaseElf
from run_prepared import verify
ROLE="single_active_pow2_scalar_private_train_reserved_v2"

class Elf(BaseElf):
    """Reuse bounded segment reads, retaining the scalar packet's own symbols."""
    def __init__(self,raw):
        super().__init__(raw)
        so=self.unpack("<Q",40)[0];ss,sn=self.unpack("<HH",58)
        sections=[self.unpack("<IIQQQQIIQQ",so+i*ss)for i in range(sn)]
        self.syms={}
        for s in sections:
            if s[1]!=2:continue
            need(s[9]==24 and s[5]%24==0 and s[6]<sn,"Bounded scalar ELF symbol table")
            strings=sections[s[6]];names=raw[strings[4]:strings[4]+strings[5]]
            for pos in range(s[4],s[4]+s[5],24):
                name,info,other,index,address,size=self.unpack("<IBBHQQ",pos)
                if not name or not index:continue
                end=names.find(b"\0",name);need(0<name<len(names)and end>=name,"Bounded scalar symbol name")
                key=names[name:end].decode()
                if key.startswith("scalar_")or key in("experiments","benchmark_main","result_values","done"):
                    value=(address,size)
                    need(key not in self.syms or self.syms[key]==value,"Ambiguous scalar symbol")
                    self.syms[key]=value

def load(path):return json.loads(Path(path).read_text())
def need(x,why):
    if not x:raise ValueError(why)
def validator():
    p=ROOT/"benchmarks/pow2_scalar_private_v2/validate.py"
    s=importlib.util.spec_from_file_location("pow2_scalar_validator",p)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    original=m.validate
    def typed(text,corpus,negative=False):
        result=original(text,corpus,negative)
        for line in text.splitlines():
            if line.startswith('IRIS_BATCH_DONE '):
                need(all(type(x)is int for x in json.loads(line.split(' ',1)[1]).values()),'Typed completion integers')
            elif line.startswith('IRIS_REGION '):
                need(all(type(x)is int and 0<=x<2**64 for x in json.loads(line.split(' ',1)[1])['values']),'Typed every output word')
        return result
    m.validate=typed
    return m
def inventory(ids):
    for name,h in ids.items():need(digest(name)==h,"Changed bound input "+name)
def inspect(raw,corpus,layout):
    e=Elf(raw);cs=corpus["cases"];table,size=e.syms["experiments"]
    need(len(cs)==576 and size==576*56,"Exact compiled scalar table size")
    need(layout["elf_sha256"]==__import__("hashlib").sha256(raw).hexdigest(),"Actual ELF/layout identity")
    for i,c in enumerate(cs):
        ptr,ki,n,h,t,*words=struct.unpack("<Q4I4Q",e.read(table+i*56,56))
        name=bytearray()
        for k in range(256):
            b=e.read(ptr+k,1)
            if b==b"\0":break
            name+=b
        need(name.decode()==c["id"] and (ki,n,h,t)==tuple(c[k]for k in("kind_index","n","hart","trial_id"))
             and words==c["expected_values"],"Actual compiled case/golden mismatch")
    need(layout["record_bytes"]==88 and layout["records"]==576,"Actual record layout declaration")
    for name,expected in layout["objects"].items():
        need(e.syms[name]==(expected["address"],expected["size"]),"Actual symbol layout "+name)
    need(e.syms["scalar_records"][1]==576*88 and e.syms["scalar_record_count"][1]==8
         and e.syms["scalar_measurements_done"][1]==8,"Compiled output storage")
    need(e.read(e.syms["scalar_measurements_done"][0],8)==b"\xff"*8,"Initialized completion sentinel")
    kernels={}
    for kind,d in layout["kernel_symbols"].items():
        address,length=e.syms["scalar_pow2_"+kind]
        need((address,length)==(d["address"],d["size"])and address%64==0 and length%4==0,"Actual aligned kernel")
        words=list(struct.unpack("<"+"I"*(length//4),e.read(address,length)))
        branches=[(i,w)for i,w in enumerate(words)if w&127==0x63]
        need(len(branches)==1,"One bounded actual kernel branch")
        bi,bw=branches[0]
        need((bw>>12)&7==1 and (bw>>15)&31==7 and (bw>>20)&31==0,"Actual BNE t2,zero")
        imm=((bw>>31)<<12)|(((bw>>7)&1)<<11)|(((bw>>25)&63)<<5)|(((bw>>8)&15)<<1)
        if imm&4096:imm-=8192
        body=bi+imm//4
        need(imm<0 and imm%4==0 and 0<=body<bi,"Backward exact kernel loop")
        count=4 if kind.endswith("independent4")else 1
        need(bi-body==count+1,"Actual unroll/loop control")
        need(words[bi-1]==0xfff38393,"Actual ADDI t2,t2,-1")
        need(words[0]==0x00050393 and words[-1]==0x00008067,"Actual count input and return")
        ops=words[body:bi-1]
        if kind.startswith("integer"):
            need(all((w&0x707f)==0x13 for w in ops),"Actual integer-add body")
        else:
            fmt={"16":2,"32":0,"64":1}[kind[2:4]]
            need(all((w&0xfe00007f)==((fmt<<25)|0x53)for w in ops),"Actual selected FADD width")
        kernels[kind]=dict(address=address,bytes=length,body_address=address+4*body,
            arithmetic_instructions_per_iteration=count,loop_control_instructions=2)
    # Fresh actual compiled sampling order, retaining the compressed JALR explicitly.
    exact={0x80000654:0x0200c7b7,0x80000658:0xff87b603,0x8000065e:0xb0002873,0x80000664:0xb02028f3,0x80000684:0x0330000f,0x80000688:0xb0202773,0x8000068c:0xb00026f3,0x80000692:0x0200c7b7,0x80000696:0xff87b583}
    for pc,word in exact.items():need(e.read(pc,4)==struct.pack('<I',word),'Actual privateCLINT/CSR instruction')
    need(e.read(0x80000682,2)==b'\x02\x97','Actual private indirect kernel call')
    address,size=e.syms['result_values'];flag,flagsize=e.syms['done'];need(address%64==0 and size==192 and flag%64==0 and flagsize==64 and not(address<=flag<address+size),'Three padded64Bresultslots +dedicated64Bpollflag')
    parent=ROOT/'build/pow2-scalar-fit-v1/scalar.elf';old=Elf(parent.read_bytes());same=[]
    for kind in kernels:
        a,n=e.syms['scalar_pow2_'+kind];pa,pn=old.syms['scalar_pow2_'+kind];need(n==pn and e.read(a,n)==old.read(pa,pn),'Original8kernel ASM bytes unchanged');same.append(dict(kind=kind,bytes=n,parent_address=pa,new_address=a,sha256=__import__('hashlib').sha256(e.read(a,n)).hexdigest()))
    return dict(schema='iris.pow2_scalar_private_compiled_admission.v2',cases=576,record_bytes=88,kernels=kernels,all8_kernel_bytes_equal_original_shared_v1=same,private_result_slots=[address+64*h for h in range(3)],private_slot_bytes=64,poll_flag=dict(address=flag,bytes=64),no_result_slot_poll_flag_false_sharing=True,parent_shared_workload_preserved=True,CLINT=dict(address=0x200bff8,before_pc=0x80000658,begin_cycle_pc=0x8000065e,begin_instret_pc=0x80000664,kernel_call_pc=0x80000682,end_instret_pc=0x80000688,end_cycle_pc=0x8000068c,after_pc=0x80000696,sampling_outside_CSR_ROI=True,mtime_hz=500000,quantization_core_cycles=1000),all_measurements_before_UART=True,physical_cache_or_traffic_observed=False)

def host_cases(corpus):
    return [dict(id=c["id"],active_harts=c["active_harts"],parent_case_id=c["parent_case_id"],
        semantic_parent_case_id=c["semantic_parent_case_id"],internal_split=c["internal_split"],
        trial_id=c["trial_id"],suite="pow2_scalar_private_v2",region="kernel",
        expected_checksums_by_hart=[c["expected_values"][0]if h==c["hart"]else 0 for h in range(3)])
        for c in corpus["cases"]]

def qualify(build,positive,negative,output):
    output.mkdir(parents=True,exist_ok=False);b=build;built=load(b/"build.json")
    corpus=load(b/"corpus.json");layout=load(b/"layout.json");elf=b/"scalar.elf"
    need(built["pass"]is True and built["negative_skip_kernel"]is False and digest(elf)==built["elf_sha256"],"Exact positive build")
    ids={**built["input_sha256"],**{str(p):digest(p)for p in
        [ROOT/"build/pow2-scalar-fit-v1/scalar.elf",ROOT/"calibration/pow2-scalar-private-v2/split.json",Path(__file__).resolve(),ROOT/"firesim/memory_footprints_wfi_groups_review_v1.py",
         b/"build.json",b/"corpus.json",b/"layout.json",elf]}}
    proof=inspect(elf.read_bytes(),corpus,layout);functional=[]
    need(len(positive)==2,"Two actual functional schedules required")
    for p in positive:
        r=load(p/"run.json");need(r["pass"]is True and r["status"]=="passed_guest_exit"
            and r["normal_guest_exit_verified"]is True and r["exit_status"]==0
            and r["timed_out"]is False and r["ELF_sha256"]==digest(elf),"Actual normal positive execution")
        inventory(r["input_sha256"]);inventory(r["output_sha256"])
        need(not any(x.startswith("--iris-timing-")for x in r["argv"]),"Functional proof cannot use fitted timing")
        validator().validate((p/"stdout").read_text(),corpus)
        ids.update(r["input_sha256"]);ids.update(r["output_sha256"]);ids[str(p/"run.json")]=digest(p/"run.json")
        functional.append(dict(seed=r["seed"],report=str(p/"run.json"),sha256=digest(p/"run.json")))
    need({x["seed"]for x in functional}=={0,17},"Actual distinct recorded seeds")
    nr=load(negative/"run.json");need(nr["pass"]is True and nr["expect_negative"]is True
        and nr["status"]=="validated_omission_negative" and type(nr["exit_status"])is int
        and nr["exit_status"]!=0 and nr["proof"]["omitted_kernel_detected"]is True,"Actual omitted-kernel rejection")
    inventory(nr["input_sha256"]);inventory(nr["output_sha256"])
    validator().validate((negative/"stdout").read_text(),corpus,True)
    ids.update(nr["input_sha256"]);ids.update(nr["output_sha256"]);ids[str(negative/"run.json")]=digest(negative/"run.json")
    controls=[];normal=(positive[0]/"stdout").read_text()
    for key,value in [("hart",True),("n",32),("checksum",0),("pass",1),("values",[0]*4),("mtime_after",0),("values",[16,False,False,False])]:
        lines=normal.splitlines();i=next(i for i,l in enumerate(lines)if l.startswith("IRIS_REGION "))
        row=json.loads(lines[i].split(" ",1)[1]);row[key]=value;lines[i]="IRIS_REGION "+json.dumps(row)
        try:validator().validate("\n".join(lines)+"\n",corpus)
        except(ValueError,KeyError,TypeError):controls.append(dict(field=key,rejected=True))
        else:raise ValueError("Actual corrupted row admitted: "+key)
    lines=normal.splitlines();j=next(i for i,l in enumerate(lines)if l.startswith('IRIS_BATCH_DONE '));row=json.loads(lines[j].split(' ',1)[1]);row['failed']=False;lines[j]='IRIS_BATCH_DONE '+json.dumps(row)
    try:validator().validate('\n'.join(lines)+'\n',corpus)
    except(ValueError,KeyError,TypeError):controls.append(dict(field='terminal-boolean',rejected=True))
    else:raise ValueError('Boolean completion accepted')
    inventory(ids)
    for name in ["build.json","corpus.json","layout.json","scalar.elf"]:
        (output/name).write_bytes((b/name).read_bytes())
    q=dict(schema="iris.pow2_scalar_private_qualification.v2",**{"pass":True},elf_sha256=digest(elf),
        functional=functional,actual_omission_report=str(negative/"run.json"),
        controls=controls,compiled_proof=proof,input_sha256=ids,hardware_contacted=False,timing_certified=False)
    (output/"qualification.json").write_text(json.dumps(q,indent=2)+"\n")
    (output/"host-cases.json").write_text(json.dumps(host_cases(corpus),indent=2)+"\n")
    ready=dict(schema="iris.pow2_scalar_private_ready.v2",status="ready_for_root_managed_preparation",
        source_frozen=True,private_per_hart_results=True,all576_before_UART=True,completion_sentinel_before_UART=True,shared_parent_preserved=True,regions=576,reserved_regions=216,train_regions=360,
        new_reference_required=True,source_image_association_verified=False,
        files={n:digest(output/n)for n in ["build.json","corpus.json","layout.json","scalar.elf","qualification.json","host-cases.json"]})
    (output/"ready.json").write_text(json.dumps(ready,indent=2)+"\n")
    return ready

def freeze(build,expected_ready,authorization,observer,output):
    import yaml
    b=build;ready=load(b/"ready.json");need(digest(b/"ready.json")==expected_ready
        and ready["schema"]=="iris.pow2_scalar_private_ready.v2"and ready["source_frozen"]is True,"Exact frozen ready")
    for n,h in ready["files"].items():need(digest(b/n)==h,"Ready artifact changed")
    q=load(b/"qualification.json");inventory(q["input_sha256"])
    corpus=load(b/"corpus.json");layout=load(b/"layout.json")
    need(q["pass"]is True and q["compiled_proof"]==inspect((b/"scalar.elf").read_bytes(),corpus,layout),"Actual source/compiled proof")
    cases=host_cases(corpus);need(cases==load(b/"host-cases.json"),"Actual canonical host cases");validate_cases(cases,True)
    grant=load(authorization);need(grant["schema"]=="iris.remote_user_launch_authorization_receipt.v1","Real user receipt")
    fs=Path("/scratch/eygao/iris-cy/sims/firesim");deploy=fs/"deploy"
    manager,m=prepare(deploy,output,b/"scalar.elf",cases,deploy/"config_runtime.yaml",deploy/"config_hwdb.yaml",
        ROOT/"firesim/artifacts/archived-build-driver-v1/driver-bundle.tar.gz",
        observability_report=ROOT/"build/firesim-observability-archived-driver-v3/report.json",profile_interval=1000000)
    from memory_observation import freeze as freeze_memory
    freeze_memory(observer,output,m);add_observer(manager)
    watch=manager/"iris_workload_watchdog.py";text=watch.read_text()
    need(text.count("SECONDS=1500")==1,"Reviewed owned watchdog template")
    watch.write_text(text.replace("SECONDS=1500","SECONDS=600",1))
    runtime=manager/"config_runtime.yaml";r=yaml.safe_load(runtime.read_text())
    old=r["target_config"].get("plusarg_passthrough","")
    need("+fesvr-step-size"not in old and "+max-cycles"not in old,"No conflicting or unsafe target bounds")
    r["target_config"]["plusarg_passthrough"]=(old+" +fesvr-step-size=128").strip()
    runtime.write_text(yaml.safe_dump(r,sort_keys=False))
    for n in ["ready.json","build.json","corpus.json","layout.json","qualification.json","host-cases.json"]:
        (output/n).write_bytes((b/n).read_bytes())
    (output/"launch-authorization.json").write_bytes(authorization.read_bytes())
    checklist=dict(schema="iris.pow2_scalar_private_capture_checklist.v2",frozen_before_flash=True,
        regions=576,full_words=2304,all_three_harts_individually=True,required_regions=True,
        private_results_64B_per_hart=True,poll_flag_dedicated_64B=True,all576_measurements_before_UART=True,shared_parent_v1_preserved=True,new_ELF_new_reference_required=True,trials=3,powers_of_two_iterations=list(corpus["lengths"]),reserved_N=[32,256,1024],
        reserved_timings_root_only=True,CLINT_scope=corpus["CLINT_scope"],
        raw_streams_and_UART=True,all_four_lifecycle_timings=True,exact_source_ELF_toolchain_image_driver_config_digests=True,
        unavailable_instrumentation=["TracerV","AutoCounter","SynthPrint"],physical_traffic_measured=False,
        watchdog_wall_seconds=600,phase_timeout_seconds=780,target_max_cycles=None,source_image_association_verified=False)
    (output/"capture-checklist.json").write_text(json.dumps(checklist,indent=2)+"\n")
    launch=["#!/usr/bin/env bash","export PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH",
        "cd "+shlex.quote(str(fs))+" || exit 1",
        "source ./sourceme-manager.sh --skip-ssh-setup > "+shlex.quote(str(output/"launch-environment.stdout"))+" 2> "+shlex.quote(str(output/"launch-environment.stderr")),
        "exec "+shlex.join(["/scratch/eygao/iris-cy/.conda-env/bin/python3",str(ROOT/"firesim/run_prepared.py"),
            str(output),"--execute","--authorization-id",grant["authorization"]["authorization_id"],"--timeout","780"])]
    (output/"launch.sh").write_text("\n".join(launch)+"\n");(output/"launch.sh").chmod(0o700)
    env=[fs/"sourceme-manager.sh",fs/"env.sh",fs.parent.parent/"env.sh"]
    ids={**q["input_sha256"],**{str(p):digest(p)for p in [Path(__file__).resolve(),authorization,
        b/"ready.json",b/"qualification.json",ROOT/"firesim/analyze_campaign.py",
        ROOT/"firesim/run_prepared.py",ROOT/"firesim/prepare_managed_campaign.py",*env]}}
    m["input_sha256"].update(ids);snapshot_inputs(output,m["input_sha256"])
    m.update(require_regions=True,require_goldens=True,campaign_role=ROLE,new_exact_reference_required=True,
        old_campaign_timings_applicable=False,expected_regions=576,reserved_regions=216,train_regions=360,
        reserved_timing_labels_root_only=True,launch_authorization_receipt=grant,
        corpus_sha256=digest(output/"corpus.json"),reviewed_ready_sha256=digest(output/"ready.json"),
        timing_perturbed=True,calibration_usable=False,hardware_source_association_verified=False,
        prepared_manager_sha256=digest(manager/"firesim"),prepared_runtime_sha256=digest(runtime),
        frozen_capture_checklist_sha256=digest(output/"capture-checklist.json"),
        environment_source_sha256={str(p):digest(p)for p in env},
        loader_override=dict(fesvr_step_size_target_cycles=128,target_cycle_bound=None,
            remote_wall_watchdog_seconds=600,foreground=True,driver_binary_unchanged=True))
    m["prepared_file_sha256"]={str(p.relative_to(output)):digest(p)for p in sorted(output.rglob("*"))
        if p.is_file()and p.name!="run.json"and not p.is_symlink()
        and not any(x.is_symlink()for x in p.parents if x!=output)}
    save_manifest(output,m);verify(output)
    return dict(status="prepared",regions=576,hardware_contacted=False)

def analyze(job,output,training_export):
    from analyze_campaign import read_archive,select_guest_uart
    need(not output.exists()and not training_export.exists(),"Fresh analysis/export destinations")
    m=load(job/"run.json");cap=m["capture"];archive=Path(cap["archive"])
    need(m["status"]=="completed_uncertified"and m["cleanup_status"]=="passed"
        and m.get("error")is None and m.get("cleanup_error")is None
        and cap["status"]=="captured"and cap["returncode"]==0,"Normal four-phase owned cleanup/capture required")
    need(digest(archive)==cap["archive_sha256"],"Exact captured bytes")
    data,ids=read_archive(archive,cap["captured_run_manifest_sha256"]);old=json.loads(data["job/run.json"])
    need(old["campaign_role"]==ROLE and old["require_goldens"]is True and old["require_regions"]is True,"Exact new scalar contract")
    need([(x["task"],x["status"])for x in old["commands"]]==[("kill","passed"),("infrasetup","passed"),("runworkload","passed"),("kill","passed")],"All four managed phases")
    need(all(x["returncode"]==0 and x["timed_out"]is False for x in old["commands"]),"All bounded phase successes")
    for p in [Path(__file__).resolve(),ROOT/"benchmarks/pow2_scalar_private_v2/validate.py"]:
        need(old["input_sha256"][str(p)]==digest(p)and digest(p)in ids.values(),"Frozen archived executed analysis source")
    corpus=json.loads(data["job/corpus.json"]);need(ids["job/corpus.json"]==old["corpus_sha256"],"Actual corpus identity")
    with tarfile.open(archive,"r:gz")as t:
        raw=t.extractfile("job/manager/workloads/iris-batch/batch.elf").read()
        layout=json.load(t.extractfile("job/layout.json"))
        q=json.load(t.extractfile("job/qualification.json"))
        ready=json.load(t.extractfile('job/ready.json'))
        for name in ['ready.json','build.json','corpus.json','layout.json','qualification.json','host-cases.json']:
            need(ids['job/'+name]==old['prepared_file_sha256'][name],'Immutable prepared admission record '+name)
        for name,wanted in ready['files'].items():
            member='job/manager/workloads/iris-batch/batch.elf'if name=='scalar.elf'else'job/'+name
            need(ids[member]==wanted,'Actual ready artifact '+name)
        need(ids['job/ready.json']==old['reviewed_ready_sha256'],'Actual frozen ready identity')
    need(__import__("hashlib").sha256(raw).hexdigest()==old["elf_sha256"],"Actual compiled ELF")
    proof=inspect(raw,corpus,layout);need(proof==q["compiled_proof"],"Actual independent compiled proof")
    member,uart=select_guest_uart(data,ids);text=data[member].decode("utf-8","strict")
    numeric=validator().validate(text,corpus);rows=[json.loads(l.split(" ",1)[1])for l in text.splitlines()if l.startswith("IRIS_REGION ")]
    output.mkdir(parents=True);training_export.mkdir(parents=True)
    (output/"uartlog").write_bytes(data[member]);(output/"observed.elf").write_bytes(raw)
    (output/"corpus.json").write_bytes(data["job/corpus.json"])
    for r,c in zip(rows,corpus["cases"]):
        r.update(cycles=r["end_cycle"]-r["start_cycle"],internal_split=c["internal_split"],kind=c["kind"])
    (output/"regions.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n"for r in rows))
    train=[{k:v for k,v in r.items()if k not in("start_cycle","end_cycle","mtime_before","mtime_after")}
        for r in rows if r["internal_split"]=="train"]
    need(len(train)==360,"Exact TRAIN-only export")
    (training_export/"regions.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n"for r in train))
    report=dict(schema="iris.pow2_scalar_private_managed_archive_analysis.v2",**{"pass":True},regions=576,
        train_regions=360,reserved_regions=216,normal_completion=True,archive_verified=True,
        archive_sha256=cap["archive_sha256"],ELF_sha256=old["elf_sha256"],numeric=numeric,
        compiled_proof=proof,lifecycle=old["commands"],guest_uart=uart,hardware_contacted=False,
        calibration_usable=False,accuracy_2percent_certified=False,source_image_association_verified=False,
        input_sha256={str(p):digest(p)for p in [Path(__file__).resolve(),job/"run.json",archive]})
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    tr=dict(schema="iris.pow2_scalar_private_TRAIN_only_export.v2",**{"pass":True},regions=360,
        reserved_rows_excluded=216,absolute_counter_and_mtime_removed=True,ELF_sha256=old["elf_sha256"],
        rows_sha256=digest(training_export/"regions.jsonl"),hardware_contacted=False)
    (training_export/"report.json").write_text(json.dumps(tr,indent=2)+"\n")
    return dict(pass_=True,regions=576,train_regions=360,reserved_regions=216)

if __name__=="__main__":
    p=argparse.ArgumentParser(__doc__);sub=p.add_subparsers(dest="command",required=True)
    q=sub.add_parser("qualify");q.add_argument("--build",type=Path,required=True)
    q.add_argument("--positive",type=Path,action="append",required=True);q.add_argument("--negative",type=Path,required=True)
    q.add_argument("--output",type=Path,required=True)
    f=sub.add_parser("prepare");f.add_argument("--build",type=Path,required=True);f.add_argument("--expected-ready-sha256",required=True)
    f.add_argument("--authorization",type=Path,required=True);f.add_argument("--observer",type=Path,required=True)
    f.add_argument("--output",type=Path,required=True)
    a=sub.add_parser("analyze");a.add_argument("job",type=Path);a.add_argument("--output",type=Path,required=True)
    a.add_argument("--training-export",type=Path,required=True)
    args=p.parse_args()
    if args.command=="qualify":r=qualify(args.build.resolve(),[x.resolve()for x in args.positive],args.negative.resolve(),args.output.resolve())
    elif args.command=="prepare":r=freeze(args.build.resolve(),args.expected_ready_sha256,args.authorization.resolve(),args.observer.resolve(),args.output.resolve())
    else:r=analyze(args.job.resolve(),args.output.resolve(),args.training_export.resolve())
    print(json.dumps(r))
