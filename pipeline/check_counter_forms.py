#!/usr/bin/env python3
"""Check actual CSRRS/RC/register/immediate and writable/alias edge behavior."""
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
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-counter-policy-v1/spike')
    p.add_argument('--uart',type=Path,default=ROOT/'build/spike-counter-policy-v1/libsifive_uart.so')
    p.add_argument('--fixture',type=Path,default=ROOT/'pipeline/rvc.fixture')
    p.add_argument('--output',type=Path,default=ROOT/'build/counter-policy-v1-forms');a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=True,parents=True);(out/'results.json').write_text('{"status":"in_progress"}\n')
    cases=[]
    for csr in (0xb00,0xb02,0xc00,0xc02):
        forms=[('CSRRS_x0',2,0),('CSRRC_x0',3,0),('CSRRSI_0',6,0),('CSRRCI_0',7,0)]
        if csr<0xc00:forms += [('CSRRS_t2_value0',2,7),('CSRRC_t2_value0',3,7)]
        for name,funct,rs1 in forms:cases.append(dict(csr=csr,name=name,funct3=funct,rsfield=rs1))
    asm=['.option push','.option norvc','.text']
    for index,case in enumerate(cases):
        start=(case['csr']<<20)|(case['rsfield']<<15)|(case['funct3']<<12)|(5<<7)|0x73
        end=(start&~(31<<7))|(6<<7)
        case.update(start_raw=start,end_raw=end)
        asm += [f'.global form_{index}',f'form_{index}:','li t3,0','li t2,0',f'.global form_{index}_begin',f'form_{index}_begin:',f'.word 0x{start:08x}',
                '.rept 16','addi t3,t3,1','.endr',f'.global form_{index}_end',f'form_{index}_end:',f'.word 0x{end:08x}',
                'sd t0,0(a0)','sd t1,8(a0)','sd t3,16(a0)','ret']
    asm+=['.option pop'];assembly=out/'forms.S';assembly.write_text('\n'.join(asm)+'\n')
    declarations='\n'.join(f'extern void form_{i}(uint64_t*);' for i in range(len(cases)))
    source=out/'guest.c';source.write_text('#include "runtime.h"\n'+declarations+'\n'+
      'static uint64_t data[3]['+str(len(cases))+'][3];\nstatic void(*forms[])(uint64_t*)={'+','.join('form_'+str(i) for i in range(len(cases)))+'};\n'+
      'void benchmark_main(unsigned h){barrier();for(unsigned i=0;i<sizeof(forms)/sizeof(forms[0]);++i)forms[i](data[h][i]);barrier();if(h)for(;;)__asm__ volatile("wfi");unsigned bad=0;'+
      'for(unsigned hart=0;hart<3;++hart)for(unsigned i=0;i<sizeof(forms)/sizeof(forms[0]);++i){bad+=data[hart][i][2]!=16;putstr("COUNTER_FORM {\\\"hart\\\":");putuint(hart);putstr(",\\\"case\\\":");putuint(i);putstr(",\\\"begin\\\":");putuint(data[hart][i][0]);putstr(",\\\"end\\\":");putuint(data[hart][i][1]);putstr(",\\\"checksum\\\":");putuint(data[hart][i][2]);putstr("}\\n");}putstr("FORMS_DONE ");putuint(bad);putstr("\\n");finish(bad);}\n')
    compiler='/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc';elf=out/'forms.elf'
    build=[compiler,'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-mcmodel=medany','-mabi=lp64d',
           '-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-I'+str(ROOT/'benchmarks'),'-T',str(ROOT/'benchmarks/link.ld'),
           str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(source),str(assembly),'-lgcc','-o',str(elf)]
    b=subprocess.run(build,text=True,capture_output=True);(out/'build.log').write_text(b.stdout+b.stderr)
    if b.returncode:raise RuntimeError('forms build failed: '+b.stderr)
    argv=command(a.binary.resolve(),elf);argv=['--extlib='+str(a.uart.resolve()) if x.startswith('--extlib=') else x for x in argv]
    fixture=a.fixture.resolve();argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(out/'graph.json')]
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);started=time.perf_counter()
    r=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=90);elapsed=time.perf_counter()-started
    (out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode or 'FORMS_DONE 0' not in r.stdout:raise RuntimeError('counter forms guest failed: '+r.stderr)
    rows=[json.loads(s.split(' ',1)[1]) for s in r.stdout.splitlines() if s.startswith('COUNTER_FORM ')]
    graph=json.loads((out/'graph.json').read_text());reads=observations(graph,Instructions(elf));table=symbols(elf)
    if len(rows)!=60 or len(reads)!=120:raise RuntimeError('counter forms coverage changed')
    for row in rows:
        h,index=row['hart'],row['case'];case=cases[index];pair=[]
        for tag in ('begin','end'):
            selected=[x for x in reads if x['hart']==h and x['pc']==table[f'form_{index}_{tag}']]
            if len(selected)!=1 or selected[0]['value']!=row[tag]:raise RuntimeError('counter form capture mismatch')
            pair.append(selected[0])
        delta=(row['end']-row['begin'])&((1<<64)-1)
        writeback=case['csr']<0xc00 and (h<2 or case['rsfield']!=0)
        if case['csr'] in (0xb00,0xc00):expected=(pair[1]['read_cycle']-pair[0]['read_cycle'])//graph['hart_cycle_dividers'][h]-int(writeback)
        else:expected=16+(not writeback)
        if delta!=expected or row['checksum']!=16:raise RuntimeError('source-specific counter form mismatch: '+str(row)+' '+str(case))
    admission=[]
    if graph['shuttle_pipeline'].get('counter_reads_enabled',False):
        operations=graph['shuttle_pipeline']['instructions']+graph.get('rocket_pipeline',{}).get('instructions',[])
        for h in (0,1,2):
            for index,case in enumerate(cases):
                for tag in ('begin','end'):
                    selected=[r for r in operations if r['hart']==h and r['pc']==table[f'form_{index}_{tag}']]
                    expected=(h<2 or graph.get('rocket_pipeline',{}).get('enabled',False)) and case['rsfield']==0
                    if len(selected)!=int(expected) or (selected and not selected[0]['counter_read']):
                        raise RuntimeError('counter source admission/fallback mismatch')
                    admission.append(dict(hart=h,case=index,boundary=tag,pipelined=expected))
    inputs=[Path(__file__).resolve(),source,assembly,fixture,ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/uart_drain.h',ROOT/'benchmarks/link.ld']
    report=dict(schema='iris.counter_edge.forms.v1',status='passed_native_source_counter_forms',binary_sha256=sha(a.binary),uart_sha256=sha(a.uart),
                argv=argv,build_command=build,elf_sha256=sha(elf),source_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},
                graph_sha256=sha(out/'graph.json'),stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),
                forms=cases,checked_intervals=len(rows),observations=len(reads),admission=admission,host_seconds=elapsed,calibrated=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],intervals=len(rows),observations=len(reads))))


if __name__=='__main__':main()
