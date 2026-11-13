#!/usr/bin/env python3
"""Replay frozen graphs/IRQ/Zephyr without enabling the new fabric flags."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-rocket-fabric-v1/spike');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=a.binary.resolve();plugin=binary.with_name('libsifive_uart.so');identity=sha(binary),sha(plugin);rows=[];inputs={str(Path(__file__).resolve()):sha(__file__)}
    parents=['rocket-source-legacy-v3','rocket-source-irq-v2','rocket-source-zephyr-scalar-v3','rocket-source-zephyr-mixed-v3']
    for name in parents:
        receipt=ROOT/'build'/name/'results.json';old=json.loads(receipt.read_text());inputs[str(receipt)]=sha(receipt)
        for i,original in enumerate(old.get('rows',[old])):
            label=name+'-'+str(i);folder=out/label;folder.mkdir();graph=folder/'graph.json';argv=[str(binary),*['--extlib='+str(plugin)if x.startswith('--extlib=')else'--iris-timing-trace='+str(graph)if x.startswith('--iris-timing-trace=')else x for x in original['argv'][1:]]]
            if sha(argv[-1])!=original['elf_sha256']:raise ValueError('frozen ELF changed')
            env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
            if original.get('fatal_handler_pcs'):env['IRIS_FATAL_PCS']=','.join(original['fatal_handler_pcs'])
            start=time.perf_counter();r=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=180);(folder/'stdout').write_text(r.stdout);(folder/'stderr').write_text(r.stderr);expected_graph=original.get('graph_sha256')or original.get('live_fixture',{}).get('graph_sha256')
            passed=r.returncode==original.get('exit_status',0)and sha(folder/'stdout')==original['stdout_sha256']and graph.exists()and sha(graph)==expected_graph
            rows.append(dict(name=label,argv=argv,exit_status=r.returncode,pass_=passed,elf_sha256=sha(argv[-1]),graph_sha256=sha(graph)if graph.exists()else None,parent_graph_sha256=expected_graph,stdout_sha256=sha(folder/'stdout'),stderr_sha256=sha(folder/'stderr'),host_seconds=time.perf_counter()-start));print(label,passed,flush=True)
    if identity!=(sha(binary),sha(plugin)):raise ValueError('native pair changed')
    report=dict(schema='iris.rocket.fabric_parent_graph_replay.v1',status='passed_legacy_IRQ_Zephyr_exact_graphs'if all(r['pass_']for r in rows)else'failed_parent_graph_replay',binary_sha256=identity[0],uart_sha256=identity[1],input_sha256=inputs,rows=rows,new_fabric_enabled=False,source_IRQ_and_Zephyr_memory_not_new_fabric_qualified=True,calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0if report['status'].startswith('passed')else 1)
if __name__=='__main__':main()
