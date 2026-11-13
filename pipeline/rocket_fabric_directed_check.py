#!/usr/bin/env python3
"""Guarded source-native cache, dependency, replay and capability corpus."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-rocket-fabric-v1/spike');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=a.binary.resolve();plugin=binary.with_name('libsifive_uart.so');compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');source=ROOT/'pipeline/rocket_fabric_directed_guest.S';identity=sha(binary),sha(plugin);rows=[]
    inputs=[Path(__file__).resolve(),source,ROOT/'benchmarks/link.ld',ROOT/'pipeline/rocket-source-synthetic.fixture',ROOT/'spike/run_functional.py',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',compiler];before={str(x):sha(x)for x in inputs}
    cases=[('widths','CASE_WIDTHS',None),('fast-dependencies','CASE_FAST_DEPENDENCIES',None),('waw-replay','CASE_WAW_REPLAY',None),('atomic-refusal','CASE_ATOMIC_REFUSAL','IRIS_ROCKET_FABRIC_DATA_OPCODE_OUTSIDE_QUALIFIED_SCALAR_SUBSET'),('load-zero-refusal','CASE_LOAD_ZERO_REFUSAL','IRIS_ROCKET_SOURCE_LOAD_X0_NO_RESP_POLICY_UNMODELED'),('unaligned-refusal','CASE_UNALIGNED_REFUSAL','IRIS_ROCKET_SOURCE_CACHE_FAULT_ARCHITECTURAL_TRAP_NOT_INTEGRATED'),('shuttle-ram-refusal','CASE_SHUTTLE_RAM','IRIS_SOURCE_FABRIC_SHUTTLE_DATA_PEER_NOT_CONNECTED')]
    cases.extend([('rvc-memory','CASE_RVC_MEMORY',None),('rvc-cold-dependent-guard','CASE_RVC_COLD_GUARD','IRIS_ROCKET_SOURCE_DEPENDENT_MEMORY_MISS_ADDRESS_KNOWNNESS_UNMODELED'),('unknown-backing-refusal','CASE_UNKNOWN_BACKING_REFUSAL','IRIS_ROCKET_FABRIC_UNINITIALIZED_EXTERNAL_MEMORY'),('tcm-service-refusal','CASE_TCM_SERVICE_REFUSAL','IRIS_ROCKET_SOURCE_EXTERNAL_TCM_OR_SCRATCH_SERVICE_UNMODELED'),('mprv-refusal','CASE_MPRV_REFUSAL','IRIS_ROCKET_SOURCE_TRANSLATED_DATA_PRIVILEGE_UNMODELED')])
    for name,macro,expected in cases:
        folder=out/name;folder.mkdir();elf=folder/'guest.elf';build=[str(compiler),'-nostdlib','-static','-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-mcmodel=medany','-D'+macro,'-T',str(ROOT/'benchmarks/link.ld'),str(source),'-o',str(elf)];r=subprocess.run(build,text=True,capture_output=True);(folder/'build.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('directed guest build failed: '+name)
        fixture=folder/'explicit.fixture';fixture.write_text((ROOT/'pipeline/rocket-source-synthetic.fixture').read_text().replace('max_cycles 100000000','max_cycles 200000')+'\nrocket_fabric explicit-synthetic-external-service 2 3 1 '+str(elf)+' explicit-functional-test-service-not-Iris-latency uncore_edges\nrocket_scalar_memory source-cache-M-mode\n');graph=folder/'graph.json';argv=command(binary,elf);argv=['--extlib='+str(plugin)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graph)];start=time.perf_counter();r=subprocess.run(argv,text=True,capture_output=True,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']),timeout=120);(folder/'stdout').write_text(r.stdout);(folder/'stderr').write_text(r.stderr)
        passed=(r.returncode!=0 and expected in r.stderr)if expected else r.returncode==0
        findings={}
        if graph.exists():
            g=json.loads(graph.read_text());meta=g['rocket_source_memory_fabric'];findings={k:meta[k]for k in ('source_memory_replays','early_load_retirements','late_RF_writes')};findings['cycles']=g['cycles']
            if name=='waw-replay':passed &= meta['source_memory_replays']>=1 and meta['late_RF_writes']>=1
        row=dict(name=name,build_command=build,argv=argv,exit_status=r.returncode,expected_diagnostic=expected,pass_=passed,host_seconds=time.perf_counter()-start,elf_sha256=sha(elf),fixture_sha256=sha(fixture),graph_sha256=sha(graph)if graph.exists()else None,stdout_sha256=sha(folder/'stdout'),stderr_sha256=sha(folder/'stderr'),findings=findings);rows.append(row);print(json.dumps(dict(name=name,pass_=passed,stderr=r.stderr[-1000:],findings=findings)),flush=True)
    if identity!=(sha(binary),sha(plugin))or before!={str(x):sha(x)for x in inputs}:raise ValueError('directed inputs changed')
    report=dict(schema='iris.rocket.source_memory_directed.v1',status='passed_source_memory_dependencies_and_guards'if all(r['pass_']for r in rows)else'failed_source_memory_directed',binary_sha256=identity[0],uart_sha256=identity[1],input_sha256=before,rows=rows,full_three_hart_memory_coherence=False,full_internal_knownness_certified=False,calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0if report['status'].startswith('passed')else 1)
if __name__=='__main__':main()
