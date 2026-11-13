#!/usr/bin/env python3
"""Gate live source frontend control, never certify synthetic memory timing."""
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
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--binary',type=Path,default=ROOT/'build/spike-frontend-live-v3/spike')
    p.add_argument('--uart',type=Path,default=ROOT/'build/spike-frontend-live-v3/libsifive_uart.so')
    p.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    binary=a.binary.resolve();uart=a.uart.resolve();compiler=a.compiler.resolve()
    identity=sha(binary),sha(uart)
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/frontend_control.S',ROOT/'pipeline/frontend_control.c',ROOT/'pipeline/frontend-values.fixture',ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/link.ld',ROOT/'benchmarks/uart_drain.S',ROOT/'benchmarks/uart_drain.h',ROOT/'spike/run_functional.py',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',compiler]
    before={str(path):sha(path) for path in inputs}
    elf=out/'control.elf'
    build=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks'),'-nostdlib','-static','-T',str(ROOT/'benchmarks/link.ld'),*[str(ROOT/x)for x in ('benchmarks/start.S','benchmarks/runtime.c','pipeline/frontend_control.S','pipeline/frontend_control.c')],'-lgcc','-o',str(elf)]
    r=subprocess.run(build,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('control guest build failed')
    table=symbols(elf);fixture=(ROOT/'pipeline/frontend-values.fixture').read_text()
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);rows=[];graphs={}
    def run(name,extra,expected=None,physical=True):
        fp=out/(name+'.fixture');fp.write_text(fixture+extra);gp=out/(name+'.graph.json')
        argv=command(binary,elf);argv=['--extlib='+str(uart) if x.startswith('--extlib=') else x for x in argv]
        flags=['--iris-timing-fixture='+str(fp),'--iris-timing-trace='+str(gp)]
        if physical:flags+=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb')]
        argv[-1:-1]=flags;start=time.perf_counter();r=subprocess.run(argv,text=True,capture_output=True,env=env,timeout=90);elapsed=time.perf_counter()-start
        stdout=out/(name+'.stdout');stderr=out/(name+'.stderr');stdout.write_text(r.stdout);stderr.write_text(r.stderr)
        row=dict(name=name,argv=argv,exit_status=r.returncode,expected_diagnostic=expected,host_seconds=elapsed,elf_sha256=sha(elf),fixture_sha256=sha(fp),stdout_sha256=sha(stdout),stderr_sha256=sha(stderr),graph_sha256=sha(gp) if gp.exists() else None)
        rows.append(row)
        if expected:
            if not r.returncode or expected not in r.stderr:raise ValueError('missing source frontend refusal: '+name+' '+r.stderr)
            return
        if r.returncode:raise ValueError('live source frontend failed: '+name+' '+r.stderr)
        actual=[json.loads(line[len('FRONTEND_CASE '):])for line in r.stdout.splitlines()if line.startswith('FRONTEND_CASE ')]
        if [x['hart']for x in actual]!=[0,1,2] or 'FRONTEND_DONE 0\n' not in r.stdout:raise ValueError('missing all-hart independent control results')
        for result in actual:
            for field,value in dict(sfb32=52,sfb16=52,wrongpath=296,jalr_link=table['frontend_jalr_link_pc'],jalr_alias=table['frontend_jalr_alias_pc'],branch_training=104,patched_non_cfi=31,failed=0).items():
                if result[field]!=value:raise ValueError('independent control golden mismatch: '+field)
        g=json.loads(gp.read_text());events={n['id']:n for n in g['events']};instructions=g['shuttle_pipeline']['instructions'];summary=[]
        for h in (0,1):
            ins=[u for u in instructions if u['hart']==h];shadows=[u for u in ins if u['sfb_shadow']];annul=[u for u in shadows if u['squashed']]
            if len(shadows)!=16 or len(annul)!=8:raise ValueError('source SFB shadows/annuls not exercised')
            if any(o['pc']==table['frontend_wrongpath_counter'] for o in g['counter_read_observations']['reads']):raise ValueError('wrong-path CSR became a guest-visible counter observation')
            controls=[u for u in ins if u['MEM_control_node'] is not None]
            trained=[u for u in controls if u['pc']==table['code']+64*h and u['expanded']==0x00050067 and u['MEM_control_resolved']]
            patched=[u for u in ins if u['pc']==table['code']+64*h and u['expanded']==0x01f00513 and u['retired']]
            if len(trained)!=8 or not any(u['MEM_mispredict']for u in trained) or not any(u['source_btb_valid'] and not u['MEM_mispredict'] for u in trained) or len(patched)!=1:
                raise ValueError('JALR source BTB training/patch exercise incomplete')
            # F2 predecode removes a stale BTB prediction from a non-CFI
            # before the parcel reaches RRD (Frontend.scala249,276–290).
            if patched[0]['source_prediction_valid'] or patched[0]['MEM_control_node'] is not None:raise ValueError('source F2 failed to remove stale non-CFI prediction')
            for u in controls:
                if u['squashed']:continue
                n=events.get(u['MEM_control_node'])
                if n and n['completed'] and n['end']!=u['RRD']+2*g['hart_cycle_dividers'][h]:raise ValueError('MEM control moved off source stage edge')
            summary.append(dict(hart=h,shadows=len(shadows),annulled_shadows=len(annul),mem_control_operations=len(controls),trained_jalr=len(trained),patched_non_cfi_f2_corrected=len(patched)))
        cancelled=[n for n in g['events'] if n.get('cancelled')];squashed=[n for n in g['events'] if n.get('squashed')]
        if not cancelled or not squashed:raise ValueError('no real source redirect cancellation/physical squashed work')
        for h in g['source_frontend']['harts']:
            for refill in h['refills']:
                for node in refill['nodes'][:refill['returned_beats']]:
                    event=events[node]
                    if not event['completed'] or event.get('cancelled') or event.get('squashed') or event['bytes']!=8:raise ValueError('accepted instruction refill was canceled or credited incorrectly')
        row.update(pass_=True,cycles=g['cycles'],retired_instructions=g['retired_instructions'],simulated_mips=sum(g['retired_instructions'])/elapsed/1e6,source_control=summary,cancelled_cpu_stages=len(cancelled),completed_squashed_stages=len(squashed),refills=sum(len(h['refills'])for h in g['source_frontend']['harts']))
        graphs[name]=gp
    source='shuttle_frontend saved-rtl-M-mode 1 16\n'
    run('fast',source+'icache_service synthetic 3 1 explicit-synthetic-fast-peer\n')
    run('fast-repeat',source+'icache_service synthetic 3 1 explicit-synthetic-fast-peer\n')
    if sha(graphs['fast'])!=sha(graphs['fast-repeat']):raise ValueError('default source peer run is nondeterministic')
    run('slow',source+'icache_service synthetic 11 2 explicit-synthetic-slow-peer\n')
    run('seed17','shuttle_frontend saved-rtl-M-mode 17 16\nicache_service synthetic 3 1 explicit-synthetic-seeded-peer\n')
    run('missing-service',source,'IRIS_FRONTEND_MISS_SERVICE_UNMODELED')
    run('wrong-reset',source+'icache_service synthetic 3 1 explicit-synthetic-peer\n','IRIS_FRONTEND_REQUIRES_SOURCE_PHYSICAL_RESET_PC_10000',physical=False)
    run('zero-seed','shuttle_frontend saved-rtl-M-mode 0 16\n','explicit source reset edges required')
    if identity!=(sha(binary),sha(uart)) or before!={str(path):sha(path)for path in inputs}:raise ValueError('inputs changed during source frontend gate')
    report=dict(schema='iris.frontend.live_source_control_gate.v1',status='passed_live_source_frontend_control',binary_sha256=identity[0],uart_sha256=identity[1],elf_sha256=sha(elf),input_sha256=before,build_command=build,rows=rows,default_graph_byte_deterministic=True,
                scope='Actual saved Shuttle frontend and live ALU/counter/CFI pipeline on harts0/1; distinct legacy source Rocket pipeline on hart2. Source MEM redirect/SFB/JALR link and real predictor/cache/fetchqueue control. External instruction memory is synthetic; other scalar/vector/VME paths retain explicit conservative fixture costs.',
                calibrated=False,rtl_certified=False,held_out_2pct=False,full_soc_timing=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],runs=len(rows))))
if __name__=='__main__':main()
