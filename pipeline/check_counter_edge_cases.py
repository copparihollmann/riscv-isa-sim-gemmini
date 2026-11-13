#!/usr/bin/env python3
"""Check source inhibit ordering and CSR edges after asynchronous memory responses."""
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
from iris_model.counter_regions import observations
from iris_model.guest_regions import Instructions
from timing.memory_live_check import fixture as memory_fixture
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--binary',type=Path,default=ROOT/'build/spike-counter-policy-v2/spike')
    p.add_argument('--uart',type=Path,default=ROOT/'build/spike-counter-policy-v2/libsifive_uart.so')
    p.add_argument('--output',type=Path,default=ROOT/'build/counter-policy-v2-edge-cases')
    p.add_argument('--counter-pipeline',action='store_true');p.add_argument('--rocket-pipeline',action='store_true');a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=True,parents=True);(out/'results.json').write_text('{"status":"in_progress"}\n')
    asm=['.option push','.option norvc','.text','.global edge_probe','edge_probe:',
         'li t2,4','li t3,0','csrr t0,instret','csrw mcountinhibit,t2',
         '.rept 16','addi t3,t3,1','.endr','csrr t1,instret','csrw mcountinhibit,zero','csrr t2,instret',
         'sd t0,0(a0)','sd t1,8(a0)','sd t2,16(a0)','sd t3,24(a0)',
         'li t2,4','csrw mcountinhibit,t2','li t3,12345','csrw minstret,t3',
         'csrr t0,instret','csrw mcountinhibit,zero','csrr t1,instret','sd t0,32(a0)','sd t1,40(a0)',
         'li t2,1','.global cy_begin','cy_begin:','csrr t0,cycle',
         '.global cy_set','cy_set:','csrw mcountinhibit,t2','.rept 16','addi t3,t3,1','.endr',
         '.global cy_held','cy_held:','csrr t1,cycle','.global cy_clear','cy_clear:','csrw mcountinhibit,zero',
         '.global cy_end','cy_end:','csrr t2,cycle','sd t0,48(a0)','sd t1,56(a0)','sd t2,64(a0)']
    for i in range(16):
        asm += [f'.global route_load_{i}',f'route_load_{i}:','ld t0,0(a1)',
                f'.global route_read_{i}',f'route_read_{i}:','csrr t1,mcycle',f'sd t0,{72+i*16}(a0)',f'sd t1,{80+i*16}(a0)']
    asm += ['ret','.option pop'];assembly=out/'edges.S';assembly.write_text('\n'.join(asm)+'\n')
    source=out/'guest.c';source.write_text('''#include "runtime.h"
extern void edge_probe(uint64_t*,const uint64_t*);
static uint64_t data[3][41];
static const uint64_t expected[3]={0x123456789abcdef0ULL,0x3141592653589793ULL,0xfedcba9876543210ULL};
void benchmark_main(unsigned hart){barrier();edge_probe(data[hart],&expected[hart]);barrier();if(hart)for(;;)__asm__ volatile("wfi");
for(unsigned h=0;h<3;++h){putstr("COUNTER_EDGE {\\"hart\\":");putuint(h);putstr(",\\"data\\":[");for(unsigned i=0;i<41;++i){if(i)putstr(",");putuint(data[h][i]);}putstr("]}\\n");}putstr("EDGE_DONE\\n");finish(0);}
''')
    compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');elf=out/'edges.elf'
    build=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize',
           '-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-I'+str(ROOT/'benchmarks'),
           '-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(source),str(assembly),'-lgcc','-o',str(elf)]
    b=subprocess.run(build,text=True,capture_output=True);(out/'build.log').write_text(b.stdout+b.stderr)
    if b.returncode:raise RuntimeError('edge guest build failed: '+b.stderr)
    # Response stage is on a deliberately different clock. Hart2 receives
    # responses on odd base ticks too; its following CSR must use a fresh
    # snapshot of its own even retirement edge, never the preceding snapshot.
    text=memory_fixture().replace('hart 2 1 1','hart 2 2 1')
    text=text.replace('response dram 10 1','response dram 7 1')
    text=text.replace('synthetic-test-cost 1 base_cycles','synthetic-test-cost 3 base_cycles')
    mode='pure-integer-rvc-counter-sequential-frontend' if a.counter_pipeline or a.rocket_pipeline else 'pure-integer-rvc-sequential-frontend'
    text+='shuttle_pipeline '+mode+'\n'+('rocket_pipeline '+mode+'\n' if a.rocket_pipeline else '');fixture=out/'edges.fixture';fixture.write_text(text)
    base=command(a.binary.resolve(),elf);base=['--extlib='+str(a.uart.resolve()) if x.startswith('--extlib=') else x for x in base]
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);table=symbols(elf);reports=[]
    for timed in (False,True):
        tag='timed' if timed else 'functional';argv=list(base);graphpath=out/(tag+'.graph.json')
        if timed:argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graphpath)]
        started=time.perf_counter();r=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=90);elapsed=time.perf_counter()-started
        (out/(tag+'.stdout')).write_text(r.stdout);(out/(tag+'.stderr')).write_text(r.stderr)
        if r.returncode or 'EDGE_DONE' not in r.stdout:raise RuntimeError('edge guest failed: '+r.stdout+r.stderr)
        rows=[json.loads(s.split(' ',1)[1]) for s in r.stdout.splitlines() if s.startswith('COUNTER_EDGE ')]
        if len(rows)!=3 or {r['hart'] for r in rows}!={0,1,2}:raise RuntimeError('edge multicore coverage changed')
        for row in rows:
            d=row['data'];expected=(0x123456789abcdef0,0x3141592653589793,0xfedcba9876543210)[row['hart']]
            if d[1]-d[0]!=2 or d[2]-d[1]!=0 or d[3]!=16 or d[4:6]!=[12345,12345]:
                raise RuntimeError('pre-edge inhibit/write priority mismatch: '+str(row))
            if any(d[9+i*2]!=expected for i in range(16)):raise RuntimeError('routed load value mismatch')
            if not timed and (d[7]-d[6]!=2 or d[8]-d[7]!=0):raise RuntimeError('functional CY edge ordering mismatch')
        report=dict(mode=tag,argv=argv,host_seconds=elapsed,stdout_sha256=sha(out/(tag+'.stdout')),stderr_sha256=sha(out/(tag+'.stderr')))
        if timed:
            graph=json.loads(graphpath.read_text());reads=observations(graph,Instructions(elf));nodes={n['id']:n for n in graph['events']};offedge=[]
            for row in rows:
                h=row['hart'];divider=graph['hart_cycle_dividers'][h];d=row['data']
                def read(label):
                    selected=[x for x in reads if x['hart']==h and x['pc']==table[label]]
                    if len(selected)!=1:raise RuntimeError('missing edge observation '+label)
                    return selected[0]
                begin,held,end=map(read,('cy_begin','cy_held','cy_end'))
                def event(label):
                    selected=[n for n in graph['events'] if n['hart']==h and n['pc']==table[label] and n['completed']]
                    if len(selected)!=1:raise RuntimeError('inhibit edge event coverage changed')
                    return selected[0]
                setedge,clearedge=event('cy_set')['end'],event('cy_clear')['end']
                if d[7]-d[6]!=(setedge-begin['read_cycle'])//divider+1 or d[8]-d[7]!=(end['read_cycle']-clearedge)//divider-1:
                    raise RuntimeError('timed CY pre-edge inhibit ordering mismatch')
                for i in range(16):
                    captured=read('route_read_'+str(i));owner=nodes[captured['node']]
                    load=[n for n in graph['events'] if n['hart']==h and n['pc']==table['route_load_'+str(i)] and n['name'].endswith('.response')]
                    if len(load)!=1 or captured['value']!=d[10+i*2] or captured['read_cycle']!=owner['end'] or owner['end']%divider:
                        raise RuntimeError('response→CSR phase/architectural value mismatch')
                    if load[0]['end']%divider:
                        if owner['submitted']!=load[0]['end'] or owner['start']<=load[0]['end'] or owner['start']%divider:
                            raise RuntimeError('off-hart response did not wait for receiving CSR edge')
                        offedge.append(dict(hart=h,index=i,response_end=load[0]['end'],CSR_start=owner['start'],CSR_end=owner['end']))
            if not offedge or {r['hart'] for r in offedge}!={2}:raise RuntimeError('actual off-hart response witness absent')
            report.update(graph_sha256=sha(graphpath),observations=len(reads),off_hart_response_witnesses=offedge)
        reports.append(report)
    inputs=[Path(__file__).resolve(),source,assembly,fixture,ROOT/'timing/memory_live_check.py',ROOT/'iris_model/counter_regions.py',ROOT/'iris_model/guest_regions.py',
            ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/uart_drain.h',ROOT/'benchmarks/link.ld']
    report=dict(schema='iris.counter_edge.cases.v1',status='passed_native_inhibit_and_memory_edges',binary_sha256=sha(a.binary),uart_sha256=sha(a.uart),
                build_command=build,compiler_sha256=sha(compiler),elf_sha256=sha(elf),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},
                cases=reports,calibrated=False,held_out_2pct=False,hardware_clock_equivalence=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],receipt=str(out/'results.json'))))


if __name__=='__main__':main()
