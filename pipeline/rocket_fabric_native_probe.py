#!/usr/bin/env python3
"""Verify live coupled fetch and fail-closed data-scope boundaries separately."""
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
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-rocket-fabric-v1/spike');p.add_argument('--elf',type=Path,default=ROOT/'benchmarks/build/smoke.elf');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=a.binary.resolve();elf=a.elf.resolve();plugin=binary.with_name('libsifive_uart.so')
    inputs=[Path(__file__).resolve(),binary,plugin,elf,ROOT/'pipeline/rocket-source-synthetic.fixture',ROOT/'spike/run_functional.py',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];before={str(x):sha(x)for x in inputs}
    fixture=out/'explicit.fixture';fixture.write_text((ROOT/'pipeline/rocket-source-synthetic.fixture').read_text().replace('max_cycles 100000000','max_cycles 50000')+'\nrocket_fabric explicit-synthetic-external-service 2 3 1 '+str(elf)+' explicit-functional-test-service-not-Iris-latency uncore_edges\n')
    graph=out/'graph.json';argv=command(binary,elf);argv=['--extlib='+str(plugin)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graph)]
    start=time.perf_counter();r=subprocess.run(argv,text=True,capture_output=True,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']),timeout=120);elapsed=time.perf_counter()-start;(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    expected='IRIS_ROCKET_FABRIC_SCALAR_DATA_CPU_PHASE_NOT_INTEGRATED';passed=r.returncode!=0 and expected in r.stderr
    findings={}
    if graph.exists():
        g=json.loads(graph.read_text());meta=g.get('rocket_source_memory_fabric',{});physical=[e for e in g['events']if e.get('physical_acceptance')];completed=[e for e in physical if e['completed']];instructions=[u for u in g.get('rocket_pipeline',{}).get('instructions',[])if u['retired']]
        findings=dict(cycles=g['cycles'],rocket_source_retired=len(instructions),physical_actors=len(physical),completed_physical_actors=len(completed),external_transactions=len(meta.get('external_transactions',[])),uncore_edges=meta.get('uncore_edges'))
        passed &= len(instructions)>0 and len(completed)>0 and any(t['port']==4 and t['address']==0x10000 for t in meta.get('external_transactions',[]))
        passed &= all(e.get('pc_known')is False and e['pc']==0 and e.get('physical_source')for e in physical)
    else:passed=False
    if before!={str(x):sha(x)for x in inputs}:raise ValueError('native probe inputs changed during execution')
    report=dict(schema='iris.rocket.live_fabric_fetch_probe.v1',status='passed_live_fetch_and_explicit_data_refusal'if passed else 'preserved_failed_live_fabric_attempt',binary_sha256=sha(binary),uart_sha256=sha(plugin),input_sha256=before,argv=argv,exit_status=r.returncode,expected_diagnostic=expected,host_seconds=elapsed,findings=findings,fixture_sha256=sha(fixture),graph_sha256=sha(graph)if graph.exists()else None,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),native_instruction_fetch_integrated=passed,native_scalar_data_integrated=False,guest_completion_pass=False,calibrated=False,rtl_certified=False,held_out_2pct=False,full_soc_timing=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],findings=findings,stderr=r.stderr[-1800:])));raise SystemExit(0if passed else 1)
if __name__=='__main__':main()
