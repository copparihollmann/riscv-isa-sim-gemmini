#!/usr/bin/env python3
"""Check precise IRQ/trap behavior with the live compiled source frontend."""
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
    p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    binary=a.binary.resolve();uart=a.uart.resolve();compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');identity=sha(binary),sha(uart)
    original=(ROOT/'pipeline/irq_guest.c').read_text();new=(ROOT/'pipeline/frontend_irq_guest.c').read_text()
    inserted='''  // The source I-cache fetches complete64B lines. Define every byte of
  // this executable last-TCM line before testing the unchanged boundary
  // fault oracle; model unknown-refill refusal must not fabricate padding.
  for(unsigned word=0;word<16;++word)((volatile uint32_t*)0x7003ffc0UL)[word]=0x00000013;
'''
    if new.replace(inserted,'')!=original:raise ValueError('precision guest delta extends beyond defining the source refill line')
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/irq_guest.c',ROOT/'pipeline/frontend_irq_guest.c',ROOT/'pipeline/irq_streams.S',ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/uart_drain.S',ROOT/'benchmarks/uart_drain.h',ROOT/'benchmarks/link.ld',ROOT/'pipeline/rocket-source-synthetic.fixture',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',ROOT/'spike/run_functional.py',compiler]
    hashes={str(p):sha(p)for p in inputs}
    flags=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks')]
    elf=out/'precision.elf';commands=[flags+['-Dtrap_dispatch=base_trap_dispatch','-c',str(ROOT/'benchmarks/runtime.c'),'-o',str(out/'runtime.o')],flags+['-DIRIS_ROCKET_PULSE=1','-nostdlib','-static','-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(out/'runtime.o'),str(ROOT/'pipeline/frontend_irq_guest.c'),str(ROOT/'pipeline/irq_streams.S'),'-lgcc','-o',str(elf)]]
    for i,argv in enumerate(commands):
        r=subprocess.run(argv,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('source frontend precision ELF failed to build')
    fixture=out/'precision.fixture'
    base_fixture=(ROOT/'pipeline/rocket-source-synthetic.fixture').read_text()
    fixture.write_text(base_fixture.replace('rule 2 0 0 scalar2 3 1 Rocket-fixture base_cycles', '# Test-only peer clear stimulus; synthetic operation duration, never an Iris latency.\nrule 2 0xffffffff 0x0002a023 scalar2 1 1 synthetic-precision-peer-clear base_cycles\nrule 2 0 0 scalar2 3 1 Rocket-fixture base_cycles'))
    hashes[str(fixture)]=sha(fixture)
    graph=out/'graph.json';argv=command(binary,elf);argv=['--extlib='+str(uart)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graph)]
    start=time.perf_counter();r=subprocess.run(argv,text=True,capture_output=True,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']),timeout=90);elapsed=time.perf_counter()-start
    (out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    rows=[json.loads(line[len('PIPELINE_PRECISION '):])for line in r.stdout.splitlines()if line.startswith('PIPELINE_PRECISION ')]
    if r.returncode or len(rows)!=1 or rows[0]['failed']:raise ValueError('source frontend precision guest failed: '+r.stderr)
    row=rows[0];table=symbols(elf)
    for key,value in dict(ipi_seen=1,timer_seen=1,pending_in_handler=0,fetch_seen=1,fetch_pc=0x70040000,fetch_tval=0x70040000,edge_result=42,illegal_count=1,illegal_pc=table['illegal_pc'],illegal_tval=11,illegal_result=21,failed=0).items():
        if row[key]!=value:raise ValueError('unchanged precision oracle failed: '+key)
    for key in ('ipi_pc','timer_pc'):
        if not table['irq_stream_begin']<=row[key]<table['irq_stream_end']:raise ValueError('interrupt not taken in actual qualified stream')
    g=json.loads(graph.read_text());events={x['id']:x for x in g['events']}
    latched=[x for x in g['shuttle_pipeline']['instructions']if x['hart']==0 and x['latched_exception'] and x['pc']==row['ipi_pc']]
    clears=[x for x in g['events']if x['hart']==2 and x['pc']==table['pulse_clear'] and x['completed']]
    if len(latched)!=1 or len(clears)!=1:raise ValueError('precise IPI capture/peer clear evidence absent')
    irq=latched[0];commit=events[irq['COM_node']]
    if not irq['RRD']<commit['end'] or irq['retired'] or irq['squashed'] or not commit['completed']:raise ValueError('IPI was not preserved after source line cleared before COM')
    if identity!=(sha(binary),sha(uart)) or hashes!={str(p):sha(p)for p in inputs+[fixture]}:raise ValueError('precision source/native changed during run')
    report=dict(schema='iris.rocket.all_three_source_IRQ_guest_goldens.v1',status='passed_actual_three_hart_IRQ_trap_guest_goldens',binary_sha256=identity[0],uart_sha256=identity[1],input_sha256=hashes,build_commands=commands,argv=argv,elf_sha256=sha(elf),graph_sha256=sha(graph),stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),host_seconds=elapsed,guest=rows[0],ipi_capture=irq['RRD'],peer_clear=clears[0]['end'],ipi_com=commit['end'],all_goldens_unchanged=True,early_clear_before_COM_witness=irq['RRD']<clears[0]['end']<commit['end'],native_captured_after_clear_context_receipt_sha256=sha(ROOT/'build/rocket-source-context-v3/results.json'),source_interrupt_crossing_timing_qualified=False,
                test_stimulus='New owned fixture shortens exact peer-clear sw-zero operation only; synthetic precision stimulus, not a source or fitted latency.',source_guest_delta='Only explicit64B initialization of executable last-TCM line; previous unknown padding refusal is preserved, never silently backed with defined RAM.',calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],capture=irq['RRD'],clear=clears[0]['end'],com=commit['end'])))
if __name__=='__main__':main()
