#!/usr/bin/env python3
"""Check real native counter captures across writes, wrap, inhibit and traps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.run_functional import command,symbols
from iris_model.guest_regions import Instructions,fixture_clocks
from iris_model.counter_regions import observations,annotate,region_metrics
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--binary',type=Path,default=ROOT/'build/spike-counter-observe/spike')
    parser.add_argument('--uart',type=Path,default=ROOT/'build/spike-counter-observe/libsifive_uart.so')
    parser.add_argument('--output',type=Path,default=ROOT/'build/counter-observe-nonlinear')
    parser.add_argument('--edge-policy',action='store_true')
    parser.add_argument('--fixture',type=Path,default=ROOT/'pipeline/rvc.fixture')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
    (out/'results.json').write_text('{"status":"in_progress","calibrated":false}\n')
    binary=args.binary.resolve();uart=args.uart.resolve();identity=(sha(binary),sha(uart))
    compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');elf=out/'counter.elf'
    sources=['benchmarks/start.S','benchmarks/runtime.c','pipeline/counter_observe_guest.c']
    build=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize',
           '-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks'),
           '-T',str(ROOT/'benchmarks/link.ld')]+[str(ROOT/p) for p in sources]+['-lgcc','-o',str(elf)]
    p=subprocess.run(build,capture_output=True,text=True);(out/'build.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise RuntimeError('counter guest build failed: '+p.stderr)
    argv=command(binary,elf);argv=['--extlib='+str(uart) if a.startswith('--extlib=') else a for a in argv]
    fixture=args.fixture.resolve();graphfile=out/'graph.json'
    argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graphfile)]
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    start=time.perf_counter();p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=60);elapsed=time.perf_counter()-start
    (out/'stdout').write_text(p.stdout);(out/'stderr').write_text(p.stderr)
    if p.returncode or 'COUNTER_OBSERVE_DONE 0' not in p.stdout:raise RuntimeError('counter guest failed: '+p.stdout+p.stderr)
    graph=json.loads(graphfile.read_text());reader=Instructions(elf)
    reads=observations(graph,reader)
    phase='model_retirement_edge_pre_update' if args.edge_policy else 'model_instruction_completion_get_csr'
    if any(r['read_phase']!=phase for r in reads):raise RuntimeError('unexpected modeled read phase')
    if len(reads)!=45 or {r['hart'] for r in reads}!={0,1,2}:raise RuntimeError('counter observations missing or internal reads leaked')
    if sum(r['result_discarded'] for r in reads)!=9:raise RuntimeError('rd0 counter writes were not recorded/discarded distinctly')
    illegal_pc=symbols(elf)['iris_counter_observe_illegal']
    if any(r['pc']==illegal_pc for r in reads):raise RuntimeError('trapped counter operation emitted a successful read')
    marked=annotate(graph,p.stdout,reader);metrics=region_metrics(marked)
    if len(metrics)!=9:raise RuntimeError('actual non-linear counter regions were not joined')
    checks=[]
    for h in range(3):
        regions={r['region'].split('::')[-1]:r for r in metrics if r['hart']==h}
        if set(regions)!={'offset','rollover','inhibit'}:raise RuntimeError('per-hart region coverage missing')
        boundaries={r['region'].split('::')[-1]:r for r in marked['region_boundaries'] if r['hart']==h}
        if boundaries['rollover']['guest_end_cycle']>=boundaries['rollover']['guest_start_cycle']:
            raise RuntimeError('actual counter did not wrap')
        # A CY-inhibited body takes positive model time but no corresponding
        # public mcycle increments. The profile must retain both quantities.
        span=boundaries['inhibit']['end']-boundaries['inhibit']['start']
        if span//graph['hart_cycle_dividers'][h]<=boundaries['inhibit']['guest_mcycle_delta']:
            raise RuntimeError('inhibit did not invalidate the constant-clock read proof')
        checks.append(dict(hart=h,inhibit_elapsed_base_cycles=span,inhibit_guest_mcycle_delta=boundaries['inhibit']['guest_mcycle_delta']))
    try:
        fixture_clocks(fixture.read_text(),graph,constant_counter_proof=True)
        # Clock parameter parsing alone succeeds; native capture, not that
        # parameter table, supplies the actual nonlinear values above.
    except ValueError as e:raise RuntimeError('fixture parameters changed') from e
    (out/'regions.json').write_text(json.dumps(marked['region_boundaries'],indent=2)+'\n')
    (out/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    if (sha(binary),sha(uart))!=identity:raise RuntimeError('native/plugin changed while running')
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/counter_observe_guest.c',ROOT/'spike/run_functional.py',ROOT/'iris_model/counter_regions.py',
            ROOT/'iris_model/guest_regions.py',ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',
            ROOT/'benchmarks/uart_drain.h',ROOT/'benchmarks/link.ld',fixture]
    report=dict(schema='iris.native_counter_observations.v1',status='passed_actual_nonlinear_counter_capture',argv=argv,build_command=build,
                exit_status=p.returncode,binary_sha256=identity[0],uart_sha256=identity[1],elf_sha256=sha(elf),
                source_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},graph_sha256=sha(graphfile),stdout_sha256=sha(out/'stdout'),
                stderr_sha256=sha(out/'stderr'),observations=len(reads),regions=len(metrics),discarded_results=9,checks=checks,
                host_seconds=elapsed,read_phase=phase,counter_policy_changed=args.edge_policy,
                hardware_phase_validated=False,calibrated=False,rtl_certified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],observations=len(reads),regions=len(metrics),receipt=str(out/'results.json'))))


if __name__=='__main__':main()
