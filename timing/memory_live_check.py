#!/usr/bin/env python3
"""Check live address-routed memory causality. All numeric costs are synthetic."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value: raise RuntimeError(message)
def rows(text,prefix):
    return [json.loads(line[len(prefix):]) for line in text.splitlines() if line.startswith(prefix)]


def fixture(dram_latency=10, writer=None, reader=None):
    lines=["purpose uncalibrated-integration-fixture", "source synthetic-address-route-check",
           "base_hz 100000000", "rtc_divider 200", "max_cycles 100000000", "trap_cycles 4"]
    for h in range(3):
        lines += [f"hart {h} 1 1", f"resource scalar{h} 1", f"rule {h} 0 0 scalar{h} 2 1 instruction base_cycles"]
    for port in ("dram","tcm0","tcm1","scratch0","scratch1","io"):
        lines.append(f"memory_port {port} 1 synthetic-test-port")
    for h in range(3):
        path=f"dram{h}";latency=writer if h==0 and writer is not None else reader if h==1 and reader is not None else dram_latency
        lines.append(f"memory_stage {path} response dram {latency} 1 access 8 1 synthetic-test-cost 1 base_cycles")
        lines.append(f"memory_region {h} 0x80000000 0x100000000 0 0 {path}")
        # Public TCMs are visible to all3 harts. Bank bit6 is explicit here.
        for bank in (0,1):
            lines += [f"memory_region {h} 0x70000000 0x40000 0x40 {bank*64} tcm{bank}",
                      f"memory_region {h} 0x580000000 0x20000 0x40 {bank*64} scratch{bank}"]
        for base,size in [("0x10000","0x10000"),("0x1000","0x1000"),("0x2000000","0x10000"),
                          ("0xc000000","0x4000000"),("0x10020000","0x1000")]:
            lines.append(f"memory_region {h} {base} {size} 0 0 io")
    for name,latency,width in [("tcm0",3,32),("tcm1",3,32),("scratch0",5,8),("scratch1",5,8),("io",2,8)]:
        lines.append(f"memory_stage {name} response {name} {latency} 1 access {width} 1 synthetic-test-cost 1 base_cycles")
    return "\n".join(lines)+"\n"


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--uart",type=Path,default=ROOT/"spike/bin/libsifive_uart.so")
    parser.add_argument("--compiler",type=Path,default=Path("/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc"))
    parser.add_argument("--dtc",type=Path,default=Path("/scratch/eygao/iris-cy/.conda-env/bin/dtc"))
    parser.add_argument("--output",type=Path,default=ROOT/"build/memory-live")
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    # A failed rerun cannot retain a previous successful acceptance receipt.
    (out/"results.json").write_text(json.dumps({"status":"in_progress","calibrated":False})+"\n")
    compiler=args.compiler.resolve();binary=args.binary.resolve();uart=args.uart.resolve()
    build=[str(compiler),"-O2","-g","-Wall","-Wextra","-Werror","-ffreestanding","-fno-builtin",
           "-fno-tree-vectorize","-mcmodel=medany","-mabi=lp64d","-march=rv64gcv_zicsr_zifencei",
           "-nostdlib","-static","-Wl,--build-id=none,--gc-sections","-I"+str(ROOT/"benchmarks"),"-T",str(ROOT/"benchmarks/link.ld")]
    commands=[]
    for name,files in [("memory",["benchmarks/start.S","benchmarks/runtime.c","timing/memory_guest.c"]),
                       ("order",["timing/order_guest.S"])]:
        cmd=build+[str(ROOT/f) for f in files]+["-lgcc","-o",str(out/(name+".elf"))]
        proc=subprocess.run(cmd,text=True,capture_output=True);(out/(name+".build.log")).write_text(proc.stdout+proc.stderr)
        require(proc.returncode==0,"guest build failed: "+proc.stderr);commands.append(cmd)
    for name,guard in [("vector",1),("mprv",2)]:
        cmd=build+["-DMEMORY_GUARD="+str(guard),str(ROOT/"timing/memory_guard_guest.S"),"-o",str(out/(name+".elf"))]
        proc=subprocess.run(cmd,text=True,capture_output=True);(out/(name+".build.log")).write_text(proc.stdout+proc.stderr)
        require(proc.returncode==0,"memory guard build failed: "+proc.stderr);commands.append(cmd)
    env=dict(os.environ);env["PATH"]=str(args.dtc.resolve().parent)+os.pathsep+env["PATH"]
    launch=[str(binary),"--iris-vme","--isa=rv64gcv_zfh_zvfh_zvl256b","-p3",
            "-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000",
            "--extlib="+str(uart),"--device=sifive_uart,0x10020000"]
    results=[];negatives=[]
    def run(name,guest,profile,seed=None):
        fp=out/(name+".fixture");fp.write_text(profile);gp=out/(name+".graph.json")
        cmd=launch+["--iris-timing-fixture="+str(fp),"--iris-timing-trace="+str(gp)]
        if seed is not None:cmd.append("--iris-schedule-seed="+str(seed))
        cmd.append(str(out/(guest+".elf")));start=time.perf_counter()
        proc=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=60);elapsed=time.perf_counter()-start
        (out/(name+".stdout")).write_text(proc.stdout);(out/(name+".stderr")).write_text(proc.stderr)
        require(proc.returncode==0,name+" failed: "+proc.stderr)
        graph=json.loads(gp.read_text());nodes={e["id"]:e for e in graph["events"]}
        transfers=graph["memory_transactions"];require(bool(transfers),"no actual memory requests were routed")
        for tx in transfers:
            require(tx["stages"] and tx["access_bytes"] in (1,2,4,8),"invalid routed request")
            for stage in tx["stages"]:
                if stage["included_in_events"] is False:
                    require(stage["node"] not in nodes,"excluded stage was presented as activity")
                    if stage["state"]=="pending":
                        require(stage["scheduled_start"] is None and stage["scheduled_end"] is None,"pending stage has scheduling timestamps")
                    else:
                        require(stage["state"]=="inflight" and stage["scheduled_start"]==graph["cycles"] and
                                stage["scheduled_end"]>graph["cycles"],"excluded inflight stage is not at snapshot frontier")
                    continue
                node=nodes[stage["node"]]
                require(stage["included_in_events"] is True and node.get("completed",True)==(stage["state"]=="completed"),"stage state disagrees with event snapshot")
                require(node["hart"]==tx["hart"] and node["resource"]==stage["resource"],"request attribution changed")
                require(stage["source"]=="synthetic-test-cost" and stage["port_source"]=="synthetic-test-port","unsourced transfer")
                require(stage["issue_period"]==1,"stage clock receipt missing")
        results.append({"name":name,"argv":cmd,"pass":True,"elf_sha256":sha(out/(guest+".elf")),
                        "fixture_sha256":sha(fp),"graph_sha256":sha(gp),"stdout_sha256":sha(out/(name+".stdout")),
                        "stderr_sha256":sha(out/(name+".stderr")),"host_seconds":elapsed,
                        "retired_instructions":graph["retired_instructions"],"memory_transactions":len(transfers),
                        "simulated_mips":sum(graph["retired_instructions"])/elapsed/1e6})
        return proc.stdout,graph
    observations=[]
    for name,cost in [("regions-fast",10),("regions-slow",40)]:
        text,graph=run(name,"memory",fixture(cost));measured=rows(text,"IRIS_MEMORY ")
        require({row["hart"] for row in measured}=={0,1,2} and len(measured)==3,"three-hart evidence missing")
        for row in measured:
            require(row["checksum"]==16*(3*row["hart"]+19)+240 and row["end"]>row["start"],"independent region golden failed")
        require({tx["path"] for tx in graph["memory_transactions"]}>={"tcm0","tcm1","scratch0","dram0","dram1","dram2"},"address-specific paths missing")
        observations.append({row["hart"]:row["end"]-row["start"] for row in measured})
    require(all(observations[1][h]>observations[0][h] for h in range(3)),"latency does not reach guest mcycle")
    for name,writer,reader,expected in [("load-first",40,2,0),("store-first",2,40,99)]:
        text,graph=run(name,"order",fixture(writer=writer,reader=reader))
        require(rows(text,"IRIS_ORDER ")==[{"observed":expected}],"routed completion did not control shared memory visibility")
    a=run("seed17","memory",fixture(),17);b=run("seed17-repeat","memory",fixture(),17)
    require(a==b,"routed seeded schedule is not repeatable")
    for name,expected in [("vector","MEMORY_OPERATION_UNMODELED"),("mprv","TRANSLATED_MEMORY_UNMODELED")]:
        elf=out/(name+".elf")
        functional=subprocess.run(launch+[str(elf)],env=env,text=True,capture_output=True,timeout=10)
        (out/(name+".functional.stdout")).write_text(functional.stdout)
        (out/(name+".functional.stderr")).write_text(functional.stderr)
        require(functional.returncode==0,"legal functional memory guard failed: "+name)
        fp=out/(name+".fixture");fp.write_text(fixture())
        proc=subprocess.run(launch+["--iris-timing-fixture="+str(fp),str(elf)],env=env,text=True,capture_output=True,timeout=10)
        (out/(name+".stderr")).write_text(proc.stderr)
        require(proc.returncode!=0 and expected in proc.stderr,"unmodeled memory semantics silently accepted: "+name)
        negatives.append({"name":name,"pass":True,"functional_exit_status":functional.returncode,
                          "exit_status":proc.returncode,"elf_sha256":sha(elf),"fixture_sha256":sha(fp),
                          "stderr_sha256":sha(out/(name+".stderr")),"functional_stdout_sha256":sha(out/(name+".functional.stdout")),
                          "functional_stderr_sha256":sha(out/(name+".functional.stderr"))})
    for name,text,error in [
            ("missing-port",fixture().replace("memory_port dram 1 synthetic-test-port\n",""),"memory stage port missing"),
            ("ambiguous",fixture()+"memory_region 0 0x80000000 0x100000000 0 0 dram0\n","AMBIGUOUS_MEMORY_ROUTE"),
            ("missing-route",fixture().replace("memory_region 0 0x80000000 0x100000000 0 0 dram0\n",""),"MEMORY_ROUTE_MISSING"),
            ("zero-clock",fixture().replace("synthetic-test-cost 1 base_cycles","synthetic-test-cost 0 base_cycles"),"explicit clock")]:
        fp=out/(name+".fixture");fp.write_text(text)
        cmd=launch+["--iris-timing-fixture="+str(fp),str(out/"memory.elf")]
        proc=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=10)
        (out/(name+".stderr")).write_text(proc.stderr)
        require(proc.returncode!=0 and error in proc.stderr,"invalid route accepted: "+name)
        negatives.append({"name":name,"pass":True,"exit_status":proc.returncode,"fixture_sha256":sha(fp),
                          "stderr_sha256":sha(out/(name+".stderr"))})
    fp=out/"rv32.fixture";fp.write_text(fixture())
    # Iris itself already refuses RV32 in board construction. Omit that mode
    # here to reach and verify the memory decoder's independent RV64 guard.
    cmd=["--isa=rv32gcv_zfh_zvfh_zvl256b" if arg.startswith("--isa=") else arg for arg in launch if arg!="--iris-vme"]
    cmd += ["--iris-timing-fixture="+str(fp),str(out/"memory.elf")]
    proc=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=10)
    (out/"rv32.stderr").write_text(proc.stderr)
    require(proc.returncode!=0 and "SCALAR_MEMORY_REQUIRES_RV64" in proc.stderr,"RV64 timing decoder silently accepted RV32")
    negatives.append({"name":"rv32","pass":True,"exit_status":proc.returncode,"fixture_sha256":sha(fp),
                      "stderr_sha256":sha(out/"rv32.stderr")})
    sources=[Path(__file__).resolve(),ROOT/"timing/memory_guest.c",ROOT/"timing/memory_guard_guest.S",ROOT/"timing/scalar_memory.hpp",ROOT/"timing/scalar_memory.cpp",
             ROOT/"timing/memory_path.hpp",ROOT/"timing/memory_path.cpp",ROOT/"timing/iris_timing.hpp",ROOT/"timing/iris_timing.cpp",
             ROOT/"timing/order_guest.S",ROOT/"benchmarks/start.S",ROOT/"benchmarks/runtime.c",ROOT/"benchmarks/runtime.h",
             ROOT/"benchmarks/uart_drain.h",ROOT/"benchmarks/uart_drain.S",ROOT/"benchmarks/link.ld"]
    receipt={"schema_version":1,"status":"passed_address_routed_live_fixtures","binary_sha256":sha(binary),
             "uart_sha256":sha(uart),"compiler_sha256":sha(compiler),"build_commands":commands,"results":results,
             "negative_results":negatives,"source_sha256":{str(p.relative_to(ROOT)):sha(p) for p in sources},
             "guest_region_cycles":observations,"calibrated":False,"iris_accuracy_certified":False,
             "scope":"Conservative scalar physical M-mode memory routing; synthetic uncached paths, no vector expansion/cache/coherence/pipeline qualification."}
    (out/"results.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({"status":receipt["status"],"checks":len(results),"negative_checks":len(negatives),"receipt":str(out/"results.json")}))

if __name__=="__main__":main()
