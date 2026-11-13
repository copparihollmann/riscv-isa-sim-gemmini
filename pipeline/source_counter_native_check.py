#!/usr/bin/env python3
"""Gate source CSR WFI state, preserved wake pulses and scoped CEASE refusal."""
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
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    binary=a.binary.resolve();uart=a.uart.resolve();identity=sha(binary),sha(uart);compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/source_counter_guest.c',ROOT/'pipeline/source_wake_pulse.c',ROOT/'pipeline/source_wake_pulse.S',ROOT/'pipeline/source_cease_guest.c',ROOT/'pipeline/source-counter-synthetic.fixture',ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/link.ld',ROOT/'benchmarks/uart_drain.S',ROOT/'benchmarks/uart_drain.h',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',ROOT/'spike/run_functional.py',compiler]
    hashes={str(p):sha(p)for p in inputs};commands=[]
    def build(name,files,flags=()):
        elf=out/(name+'.elf');argv=[str(compiler),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-DIRIS_HARTS=3','-I'+str(ROOT/'benchmarks'),*flags,'-nostdlib','-static','-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),*[str(ROOT/'pipeline'/x)for x in files],'-lgcc','-o',str(elf)]
        r=subprocess.run(argv,text=True,capture_output=True);(out/(name+'.build.log')).write_text(r.stdout+r.stderr);commands.append(argv)
        if r.returncode:raise RuntimeError('source counter guest build failed: '+name)
        return elf
    wfi=build('wfi',['source_counter_guest.c']);pulse=build('pulse',['source_wake_pulse.c','source_wake_pulse.S']);shuttle=build('cease-shuttle',['source_cease_guest.c'],['-DTEST_HART=0']);rocket=build('cease-rocket',['source_cease_guest.c'])
    fixture=(ROOT/'pipeline/source-counter-synthetic.fixture').read_text().replace('max_cycles 100000000','max_cycles 500000');rows=[]
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    def run(name,elf,text,expected_exit=0,diagnostic=None):
        fp=out/(name+'.fixture');fp.write_text(text);gp=out/(name+'.graph.json');argv=command(binary,elf);argv=['--extlib='+str(uart)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fp),'--iris-timing-trace='+str(gp)]
        start=time.perf_counter();r=subprocess.run(argv,text=True,capture_output=True,env=env,timeout=60);elapsed=time.perf_counter()-start
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        if (r.returncode!=expected_exit if expected_exit is not None else not r.returncode)or(diagnostic and diagnostic not in r.stderr):raise ValueError('source counter run/refusal differs: '+name+' '+r.stderr)
        row=dict(name=name,argv=argv,exit_status=r.returncode,expected_exit_status=expected_exit,expected_diagnostic=diagnostic,host_seconds=elapsed,elf_sha256=sha(elf),fixture_sha256=sha(fp),stdout_sha256=sha(out/(name+'.stdout')),stderr_sha256=sha(out/(name+'.stderr')),graph_sha256=sha(gp)if gp.exists()else None);rows.append(row)
        return r,json.loads(gp.read_text())if gp.exists()else None,row
    r,g,row=run('source-wfi',wfi,fixture)
    data=[json.loads(line[len('SOURCE_WFI '):])for line in r.stdout.splitlines()if line.startswith('SOURCE_WFI ')]
    if len(data)!=3 or {x['hart']for x in data}!={0,1,2}or'SOURCE_WFI_DONE 0\n'not in r.stdout:raise ValueError('source WFI all-hart guest incomplete')
    for result in data:
        if result['failed']or result['t1']-result['t0']<4 or not 0<result['c1']-result['c0']<=300 or not 0<result['pending1']-result['pending0']<=100:raise ValueError('source WFI counter/wall-time distinction failed')
        transitions=[x for x in g['source_counter_clock']['transitions']if x['hart']==result['hart']]
        if not any(x['stall_after']for x in transitions)or not any(x['stall_before']and not x['stall_after']for x in transitions):raise ValueError('source WFI entry/wake state not observed')
    if g['shuttle_pipeline']['domain']!='experimental-source-Shuttle-frontend-RV64IC-ALU-counter-CFI':raise ValueError('legacy source frontend label persisted')
    row['guest']=data
    r,g,row=run('wake-pulse',pulse,fixture)
    if 'PASSED source wake persists'in r.stdout:
        s=symbols(pulse);events=[x for x in g['events']if x['completed']]
        def one(pc,h):
            found=[x for x in events if x['pc']==pc and x['hart']==h]
            if len(found)!=1:raise ValueError('pulse identity ambiguous')
            return found[0]['end']
        park=one(s['source_pulse_park'],2);set_=one(s['source_wake_pulse_set'],0);clear=one(s['source_wake_pulse_clear'],0)
        wake=[x['cycle']for x in g['source_counter_clock']['transitions']if x['hart']==2 and x['stall_before']and not x['stall_after']and x['cycle']>park]
        if len(wake)!=1:raise ValueError('pulse wake transition ambiguous')
        after=[x['ID']for x in g['rocket_pipeline']['instructions']if x['ID']>wake[0]]
        if not after or not park<set_<wake[0]<clear<=min(after)or min(after)!=wake[0]+g['hart_cycle_dividers'][2]:raise ValueError('wake did not survive clear before first eligible source ID')
        row['wake_proof']=dict(park=park,set=set_,wake=wake[0],clear=clear,first_source_id=min(after))
    else:raise ValueError('pulse guest failed')
    legacy='\n'.join(x for x in fixture.splitlines()if not x.startswith('counter_policy '))+'\n'
    for h,d in ((0,1),(1,1),(2,2)):legacy=legacy.replace(f'hart {h} {d} source',f'hart {h} {d} 1')
    r,_,_=run('legacy-count-WFI-control',wfi,legacy,expected_exit=None)
    if 'SOURCE_WFI_DONE 3\n'not in r.stdout:raise ValueError('legacy synthetic count-WFI control did not expose all3 divergences')
    run('mixed-idle-policy',wfi,fixture.replace('hart 0 1 source','hart 0 1 1'),expected_exit=None,diagnostic='numeric count_wfi is synthetic')
    r,_,_=run('shuttle-cease-illegal',shuttle,fixture)
    if 'PASSED source Shuttle CEASE refusal'not in r.stdout:raise ValueError('Shuttle actual CEASE illegality not retained')
    run('rocket-cease-unqualified',rocket,fixture,expected_exit=None,diagnostic='IRIS_UNSUPPORTED_CORE_INSTRUCTION')
    if identity!=(sha(binary),sha(uart))or hashes!={str(p):sha(p)for p in inputs}:raise ValueError('source counter gate inputs changed')
    report=dict(schema='iris.frontend.source_counter_native.v1',status='passed_source_counter_WFI_and_wake_precision',binary_sha256=identity[0],uart_sha256=identity[1],input_sha256=hashes,build_commands=commands,rows=rows,
                interrupt_delivery_scope='Existing native device inputs sampled before device edge updates. Source interrupt synchronizer timing is unqualified; no invented delay.',CEASE_scope='Shuttle illegal source decode retained. Rocket configured CEASE is deferred model refusal, not a fabricated architectural illegal trap; exact Rocket integration pending.',calibrated=False,rtl_certified=False,held_out_2pct=False,full_counter_timing_certified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],runs=len(rows))))
if __name__=='__main__':main()
