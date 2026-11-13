#!/usr/bin/env python3
"""Actual Spike guest with early-retired load, independent work, store/reload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command,symbols
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-rocket-fabric-v1/spike');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=a.binary.resolve();plugin=binary.with_name('libsifive_uart.so');compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');source=ROOT/'pipeline/rocket_fabric_load_guest.S';elf=out/'load.elf'
    rom_word=int.from_bytes((ROOT/'board/evidence/bootrom.rv64.img').read_bytes()[:8],'little')
    build=[str(compiler),'-nostdlib','-static','-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-mcmodel=medany','-DIRIS_ROM_WORD='+hex(rom_word),'-T',str(ROOT/'benchmarks/link.ld'),str(source),'-o',str(elf)];r=subprocess.run(build,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('source load guest failed to build')
    inputs=[Path(__file__).resolve(),binary,plugin,source,elf,ROOT/'benchmarks/link.ld',ROOT/'pipeline/rocket-source-synthetic.fixture',ROOT/'spike/run_functional.py',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',compiler];before={str(x):sha(x)for x in inputs}
    fixture=out/'explicit.fixture';fixture.write_text((ROOT/'pipeline/rocket-source-synthetic.fixture').read_text().replace('max_cycles 100000000','max_cycles 200000')+'\nrocket_fabric explicit-synthetic-external-service 2 3 1 '+str(elf)+' explicit-functional-test-service-not-Iris-latency uncore_edges\nrocket_scalar_memory source-cache-M-mode\n')
    graph=out/'graph.json';argv=command(binary,elf);argv=['--extlib='+str(plugin)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graph)]
    start=time.perf_counter();r=subprocess.run(argv,text=True,capture_output=True,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']),timeout=120);elapsed=time.perf_counter()-start;(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr);passed=r.returncode==0;findings={}
    if graph.exists():
        g=json.loads(graph.read_text());sym=symbols(elf);loads=[e for e in g['events']if e.get('physical_acceptance')and e['pc']==sym['source_load_rom']];ins=g['rocket_pipeline']['instructions'];retired=[u for u in ins if u['retired']];findings=dict(cycles=g['cycles'],retired=len(retired),source_load_actors=len(loads),source_load_actor_spans=[dict(start=e['start'],end=e['end'],completed=e['completed'])for e in loads])
        if not loads:passed=False
        else:
            loadrow=next((u for u in retired if u['pc']==sym['source_load_rom']),None);events={e['id']:e for e in g['events']};wb=events[loadrow['WB_node']]['end']if loadrow else None;later=[u for u in retired if wb is not None and events[u['WB_node']]['end']>wb and events[u['WB_node']]['end']<loads[-1]['end']];findings.update(load_wb=wb,other_retired_before_data=len(later));passed &= wb is not None and loads[-1]['completed']and loads[-1]['end']>wb and len(later)>=1
    else:passed=False
    if before!={str(x):sha(x)for x in inputs}:raise ValueError('load gate inputs changed during execution')
    report=dict(schema='iris.rocket.live_fabric_scalar_load.v1',status='passed_live_early_load_retire_and_late_RF'if passed else 'preserved_failed_live_scalar_load_attempt',binary_sha256=sha(binary),uart_sha256=sha(plugin),input_sha256=before,build_command=build,argv=argv,exit_status=r.returncode,host_seconds=elapsed,findings=findings,fixture_sha256=sha(fixture),graph_sha256=sha(graph)if graph.exists()else None,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),guest_completion_pass=r.returncode==0,calibrated=False,rtl_certified=False,held_out_2pct=False,full_soc_timing=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],findings=findings,stderr=r.stderr[-2000:])));raise SystemExit(0if passed else 1)
if __name__=='__main__':main()
