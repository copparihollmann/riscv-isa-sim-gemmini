#!/usr/bin/env python3
"""Independent CSR-result, back-to-back, EX hold and fallback pipeline checks."""
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
MASK=(1<<64)-1


def validate(graph,elf,rows,forms,rocket=False):
    code=Instructions(elf);table=symbols(elf);reads=observations(graph,code);nodes={n['id']:n for n in graph['events']}
    meta=graph['shuttle_pipeline'];ops=meta['instructions'];checked=0;overlap=0;bypass=0;holds=0;rocket_checked=0
    if not meta['counter_reads_enabled']:raise ValueError('counter overlap domain disabled')
    for row in rows:
        h,index=row['hart'],row['case'];form=forms[index];d=row['data'];pair=[]
        for tag in ('begin','end'):
            selected=[r for r in reads if r['hart']==h and r['pc']==table[f'case_{index}_{tag}']]
            if len(selected)!=1 or selected[0]['value']!=d[len(pair)]:raise ValueError('CSR result not equal to actual guest value')
            pair.append(selected[0])
        if d[2]!=(d[1]+17)&MASK or d[3]!=(77 if form['independent'] else 0):raise ValueError('independent CSR-result arithmetic mismatch')
        writeback=h<2 and form['csr']<0xc00
        if form['csr'] in (0xb00,0xc00):expected=(pair[1]['read_cycle']-pair[0]['read_cycle'])//graph['hart_cycle_dividers'][h]-int(writeback)
        else:expected=int(form['independent'])+(not writeback)
        if (d[1]-d[0])&MASK!=expected:raise ValueError('visible counter source policy mismatch')
        if h>=2:
            if any(r['hart']==h and r['pc'] in (table[f'case_{index}_begin'],table[f'case_{index}_end']) for r in ops):raise ValueError('Rocket entered Shuttle path')
            if rocket:
                metadata=graph['rocket_pipeline'];r_ops=metadata['instructions']
                if not metadata['enabled'] or metadata['peak_packets']!=3:raise ValueError('Rocket did not overlap3 single-issue pipeline stages')
                def operation(tag):
                    selected=[r for r in r_ops if r['pc']==table[f'case_{index}_{tag}']]
                    if len(selected)!=1:raise ValueError('Rocket directed operation missing')
                    return selected[0]
                begin,end,dependent=map(operation,('begin','end','dependent'));divider=graph['hart_cycle_dividers'][h]
                for record in (begin,end):
                    ex,mem,wb=[nodes[record[key]] for key in ('EX_node','MEM_node','WB_node')]
                    if record['result_node']!=record['WB_node'] or record['result_stage']!='WB' or not record['counter_read']:
                        raise ValueError('Rocket CSR was bypassed before source WB')
                    if (ex['start'],ex['end'],mem['start'],mem['end'],wb['start'],wb['end'])!=tuple(record['ID']+n*divider for n in (0,1,1,2,2,3)):
                        raise ValueError('Rocket EX/MEM/WB source phases changed')
                if dependent['ID']!=nodes[end['WB_node']]['end'] or end['sequence'] not in dependent['raw_producers']:
                    raise ValueError('Rocket CSR RAW did not wait for WB write-through')
                if form['independent']:
                    independent=operation('independent')
                    if independent['ID']!=begin['ID']+divider or independent['ID']>=nodes[begin['WB_node']]['end']:
                        raise ValueError('Rocket independent ALU did not overlap CSR')
                elif end['ID']!=begin['ID']+divider or nodes[end['WB_node']]['end']-nodes[begin['WB_node']]['end']!=divider:
                    raise ValueError('Rocket inherited an incorrect global CSR drain')
                rocket_checked+=1
            continue
        def operation(tag):
            result=[r for r in ops if r['hart']==h and r['pc']==table[f'case_{index}_{tag}']]
            if len(result)!=1:raise ValueError('pipeline operation coverage changed')
            return result[0]
        begin,end,dependent=map(operation,('begin','end','dependent'));divider=graph['hart_cycle_dividers'][h]
        for record in (begin,end):
            com,wb,ex=[nodes[record[key]] for key in ('COM_node','WB_node','CSR_EX_node')]
            if not record['counter_read'] or record['lane'] or record['result_stage']!='COM' or record['result_node']!=record['COM_node']:
                raise ValueError('CSR result made ready before actual COM source')
            if com['end']!=record['EX_release']+2*divider or ex['start']!=record['RRD'] or ex['end']!=record['EX_release'] or wb['end']!=com['end']+divider:
                raise ValueError('CSR source stages/EX hold/WB distinction changed')
            if any(n['end']<=n['start'] for n in (com,wb,ex)):raise ValueError('nonpositive pipeline event')
            if not record['retired'] or not record['released']:raise ValueError('CSR did not retire/release')
        endcom,endwb=nodes[end['COM_node']],nodes[end['WB_node']]
        if dependent['RRD']!=endcom['end'] or dependent['RRD']>=endwb['end'] or end['sequence'] not in dependent['raw_producers']:
            raise ValueError('CSR dependent did not use actual COM bypass before WB')
        bypass+=1
        if not form['independent']:
            if end['RRD']!=begin['RRD']+divider or endcom['end']-nodes[begin['COM_node']]['end']!=3*divider:
                raise ValueError('back-to-back read did not obey source EX hold')
            if end['EX_release']-end['RRD']!=3*divider:raise ValueError('back-to-back CSR EX hold missing')
            holds+=1
        else:
            independent=operation('independent')
            if independent['RRD']!=begin['RRD']+divider or independent['RRD']>=nodes[begin['COM_node']]['end']:
                raise ValueError('independent scalar work did not overlap CSR')
            overlap+=1
        # Source csr_en is youngest and pipe0; no instruction shares its packet.
        for record in (begin,end):
            if sum(r['hart']==h and r['packet']==record['packet'] for r in ops)!=1:raise ValueError('CSR shared forbidden packet lane')
        # No younger instruction may enter RRD on a held EX edge, even when
        # the older COM completion callback already ran at that timestamp.
        for record in (begin,end):
            if any(r['hart']==h and record['sequence']<r['sequence'] and record['RRD']<r['RRD']<record['EX_release'] for r in ops):
                raise ValueError('RRD advanced while source CSR EX was stalled')
        checked+=1
    if checked!=64 or overlap!=32 or bypass!=64 or holds!=32:raise ValueError('directed CSR coverage changed')
    if rocket and rocket_checked!=32:raise ValueError('Rocket directed coverage changed')
    return dict(checked_Shuttle_cases=checked,independent_overlap_witnesses=overlap,COM_bypass_witnesses=bypass,back_to_back_hold_witnesses=holds,observations=len(reads),Rocket_cases=rocket_checked)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-counter-pipeline-v1/spike')
    p.add_argument('--uart',type=Path,default=ROOT/'build/spike-counter-pipeline-v1/libsifive_uart.so')
    p.add_argument('--fixture',type=Path,default=ROOT/'pipeline/counter.fixture')
    p.add_argument('--rocket',action='store_true')
    p.add_argument('--output',type=Path,default=ROOT/'build/counter-pipeline-v1-directed');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=True,parents=True)
    (out/'results.json').write_text('{"status":"in_progress"}\n');forms=[]
    for independent in (False,True):
        for csr in (0xb00,0xb02,0xc00,0xc02):
            for funct in (2,3,6,7):forms.append(dict(csr=csr,funct3=funct,independent=independent))
    asm=['.option push','.option norvc','.text']
    for index,form in enumerate(forms):
        raw=(form['csr']<<20)|(form['funct3']<<12)|0x73
        asm += [f'.global case_{index}',f'case_{index}:',f'.global case_{index}_begin',f'case_{index}_begin:',f'.word 0x{raw|(5<<7):08x}']
        if form['independent']:asm += [f'.global case_{index}_independent',f'case_{index}_independent:','addi t4,zero,77']
        asm += [f'.global case_{index}_end',f'case_{index}_end:',f'.word 0x{raw|(6<<7):08x}',
                f'.global case_{index}_dependent',f'case_{index}_dependent:','addi t3,t1,17','sd t0,0(a0)','sd t1,8(a0)','sd t3,16(a0)',
                'sd t4,24(a0)' if form['independent'] else 'sd zero,24(a0)','ret']
    asm+=['.option pop'];assembly=out/'cases.S';assembly.write_text('\n'.join(asm)+'\n')
    decl='\n'.join(f'extern void case_{i}(uint64_t*);' for i in range(32));calls=','.join(f'case_{i}' for i in range(32))
    source=out/'guest.c';source.write_text('#include "runtime.h"\n'+decl+'\nstatic uint64_t data[3][32][4];\nstatic void(*cases[])(uint64_t*)={'+calls+'};\n'+'''
void benchmark_main(unsigned hart){barrier();for(unsigned i=0;i<32;++i)cases[i](data[hart][i]);barrier();if(hart)for(;;)__asm__ volatile("wfi");
for(unsigned h=0;h<3;++h){for(unsigned i=0;i<32;++i){putstr("COUNTER_PIPELINE {\\"hart\\":");putuint(h);putstr(",\\"case\\":");putuint(i);putstr(",\\"data\\":[");for(unsigned j=0;j<4;++j){if(j)putstr(",");putuint(data[h][i][j]);}putstr("]}\\n");}}putstr("COUNTER_PIPELINE_DONE\\n");finish(0);}
''')
    compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc');elf=out/'cases.elf'
    build=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-mcmodel=medany','-mabi=lp64d',
           '-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-I'+str(ROOT/'benchmarks'),'-T',str(ROOT/'benchmarks/link.ld'),
           str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(source),str(assembly),'-lgcc','-o',str(elf)]
    b=subprocess.run(build,text=True,capture_output=True);(out/'build.log').write_text(b.stdout+b.stderr)
    if b.returncode:raise RuntimeError('directed CSR guest build failed: '+b.stderr)
    fixture=a.fixture.resolve();argv=command(a.binary.resolve(),elf);argv=['--extlib='+str(a.uart.resolve()) if x.startswith('--extlib=') else x for x in argv]
    argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(out/'graph.json')];env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    started=time.perf_counter();r=subprocess.run(argv,text=True,capture_output=True,env=env,timeout=90);elapsed=time.perf_counter()-started
    (out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode or 'COUNTER_PIPELINE_DONE' not in r.stdout:raise RuntimeError('directed CSR guest failed: '+r.stderr)
    rows=[json.loads(s.split(' ',1)[1]) for s in r.stdout.splitlines() if s.startswith('COUNTER_PIPELINE ')]
    if len(rows)!=96:raise RuntimeError('all3hart directed CSR coverage missing')
    graph=json.loads((out/'graph.json').read_text());checks=validate(graph,elf,rows,forms,a.rocket)
    # Corrupt actual data and graph witnesses; the independent checker must
    # reject both functional and scheduling errors, not merely count records.
    import copy
    badrows=copy.deepcopy(rows);badrows[0]['data'][2]^=1
    corrupt=copy.deepcopy(graph);first=next(r for r in corrupt['shuttle_pipeline']['instructions'] if r['counter_read']);first['result_node']=first['CSR_EX_node']
    for g,rr in ((graph,badrows),(corrupt,rows)):
        try:validate(g,elf,rr,forms,a.rocket)
        except ValueError:pass
        else:raise RuntimeError('corrupted CSR result/schedule was accepted')
    inputs=[Path(__file__).resolve(),source,assembly,fixture,ROOT/'spike/run_functional.py',ROOT/'iris_model/counter_regions.py',ROOT/'iris_model/guest_regions.py',
            ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/uart_drain.h',ROOT/'benchmarks/link.ld']
    report=dict(schema='iris.shuttle.counter_pipeline.v1',status='passed_directed_source_counter_overlap',binary_sha256=sha(a.binary),uart_sha256=sha(a.uart),
                argv=argv,build_command=build,elf_sha256=sha(elf),graph_sha256=sha(out/'graph.json'),stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),
                source_sha256={str(p.relative_to(ROOT)):sha(p) for p in inputs},forms=forms,checks=checks,negative_controls=2,host_seconds=elapsed,
                calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],checks=checks)))


if __name__=='__main__':main()
