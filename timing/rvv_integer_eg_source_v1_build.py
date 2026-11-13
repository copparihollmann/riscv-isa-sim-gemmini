#!/usr/bin/env python3
"""Build and compare finite integer VADD control/numeric outputs against untouched saved Saturn RTL."""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import os
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
SDK=ROOT/'build/saturn-timing-ownership-sdk-v7/sdk'
RTL=ROOT/'build/saturn-timing-component-v1-final/build/saturn-timing-source-v1/compute/rtl'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def run(argv,folder,commands,timeout=120):
    folder.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    result=subprocess.run(list(map(str,argv)),stdout=(folder/'stdout').open('wb'),stderr=(folder/'stderr').open('wb'),timeout=timeout,
        env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ.get('PATH','')))
    row=dict(argv=list(map(str,argv)),exit_status=result.returncode,host_seconds=time.monotonic()-started,
        stdout_sha256=sha(folder/'stdout'),stderr_sha256=sha(folder/'stderr'))
    commands.append(row);(folder/'run.json').write_text(json.dumps(row,indent=2)+'\n')
    return result.returncode

def main():
    a=argparse.ArgumentParser(__doc__);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);commands=[];inputs=[Path(__file__).resolve()]
    header=ROOT/'timing/rvv_integer_eg_source_v1.hpp';probe=ROOT/'timing/rvv_integer_eg_source_v1_probe.cpp'
    inputs += [header,probe,SDK/'saturn_timing.hpp',SDK/'libiris_saturn_timing.a',SDK.parent/'build.json',SDK/'ownership-schema.json',Path('/usr/bin/g++')]
    initial_header_sha256=sha(header)
    compile=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(SDK),'-I'+str(ROOT/'timing'),probe,SDK/'libiris_saturn_timing.a','-latomic','-o',out/'probe']
    if run(compile,out/'compile',commands):raise ValueError('Probe compile failed')
    numeric=ROOT/'timing/rvv_integer_eg_source_v1_numeric.cpp';inputs.append(numeric)
    if run(['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(SDK),'-I'+str(ROOT/'timing'),numeric,SDK/'libiris_saturn_timing.a','-latomic','-o',out/'numeric-probe'],out/'numeric-compile',commands):raise ValueError('Numeric probe compile failed')
    rows=[];numeric_rows=[]
    for sew,lm,mode,seed in itertools.product((8,16,32,64),(1,2,4,8),range(4),(1,17)):
        case=out/f'H{sew}-M{lm}-mode{mode}-seed{seed}'
        if run([out/'probe',sew,lm,mode,seed,96],case,commands):raise ValueError('Source differential failed: '+str(case))
        result=json.loads(next(x for x in reversed((case/'stderr').read_text().splitlines())if x.startswith('{')))
        rows.append(result)
        ncase=out/f'numeric-H{sew}-M{lm}-mode{mode}-seed{seed}'
        if run([out/'numeric-probe',sew,lm,mode,seed,64],ncase,commands):raise ValueError('Source numeric differential failed: '+str(ncase))
        numeric_rows.append(json.loads(next(x for x in reversed((ncase/'stderr').read_text().splitlines())if x.startswith('{'))))
    mutations=[
      ('extra-IQ-entry','iq_capacity=3','iq_capacity=4',(8,8,0,1,96)),
      ('whole-register-EG','d=2*c.vd+index_','d=2*c.vd',(32,1,1,1,32)),
      ('flow-full-VDQ','e.input_ready=vdq_.size()<vdq_capacity;','e.input_ready=vdq_.size()<vdq_capacity||e.vdq_dequeue;',(8,8,0,1,96))]
    mutant_rows=[]
    for name,old,new,case in mutations:
        folder=out/'mutants'/name;folder.mkdir(parents=True)
        text=header.read_text()
        if text.count(old)!=1:raise ValueError('Mutation source pattern no longer exact: '+name)
        (folder/header.name).write_text(text.replace(old,new));shutil.copy2(probe,folder/probe.name)
        argv=['/usr/bin/g++','-O2','-std=c++20','-pthread','-I'+str(SDK),'-I'+str(folder),folder/probe.name,SDK/'libiris_saturn_timing.a','-latomic','-o',folder/'probe']
        if run(argv,folder/'compile',commands):raise ValueError('Mutant did not compile '+name)
        code=run([folder/'probe',*case],folder/'check',commands)
        if code!=2 or 'model='not in(folder/'check/stderr').read_text():raise ValueError('Mutant escaped actual source differential '+name)
        mutant_rows.append(dict(name=name,source_mismatch_detected=True,diagnostic=(folder/'check/stderr').read_text().splitlines()[-1]))
    # Standalone original sequencer ports exercise external read/write masks
    # and backpressure, where a pure single-VADD full-unit stream has no WAR.
    seq=out/'sequencer';seq.mkdir();svs=[RTL/'ExecuteSequencer.sv',RTL/'PipeScheduler.sv']
    for p in svs:shutil.copy2(p,seq/p.name)
    inputs+=svs+[ROOT/'timing/rvv_integer_eg_source_v1_sequence_check.cpp']
    verilator=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');perl=verilator.with_name('perl')
    inputs += [verilator,perl]
    argv=[perl,verilator,'--cc','--exe','--build','-j','4','--top-module','ExecuteSequencer','--prefix','VIntegerSourceSeq','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique',
          '--Mdir',seq/'obj','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT',*[seq/p.name for p in svs],
          ROOT/'timing/rvv_integer_eg_source_v1_sequence_check.cpp','-CFLAGS','-std=c++20 -O2 -I'+str(ROOT/'timing'),
          '-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O2 OPT_SLOW=-O2']
    if run(argv,seq/'compile',commands):raise ValueError('Exact source sequencer build failed')
    seq_rows=[]
    for seed in (1,17,31):
        folder=seq/f'seed{seed}'
        if run([seq/'obj/VIntegerSourceSeq',seed],folder,commands):raise ValueError('Source sequencer port differential failed')
        row=json.loads(next(x for x in reversed((folder/'stdout').read_text().splitlines())if x.startswith('{')));seq_rows.append(row)
    guard=ROOT/'timing/rvv_integer_eg_source_v1_guards.cpp';inputs.append(guard);guard_rows=[]
    for mode,flags in [('optimized',['-O2']),('checked',['-O1','-D_GLIBCXX_ASSERTIONS'])]:
        binary=out/('guards-'+mode)
        if run(['/usr/bin/g++',*flags,'-std=c++20',guard,'-o',binary],out/('guard-compile-'+mode),commands):raise ValueError('Guard compile failed')
        folder=out/('guard-check-'+mode)
        if run([binary],folder,commands):raise ValueError('Finite API guard checks failed')
        guard_rows.append(dict(mode=mode,**json.loads((folder/'stdout').read_text())))
    # Bind exact source/module witnesses, preserving original generated bytes.
    schema=ROOT/'build/saturn-timing-activity-component-v1-final/build/saturn-timing-activity-schema-v1/schema.json';inputs.append(schema)
    fields=json.loads(schema.read_text())['profiles']['compute']['fields']
    names=['vu.vxsint.valid','vu.vxuint.io_pipe_hazards_0_valid','vu.vxuint.io_pipe_hazards_1_valid','vu.vdq.valids_0','vu.vxissq_int.q.valids_0']
    witnesses=[]
    for name in names:
        source=next(f for f in fields if f['name']==name)['source'];path=Path(source['path'])
        if sha(path)!=source['sha256']or path.read_text().splitlines()[source['line']-1]!=source['literal']:raise ValueError('Saved source witness changed '+name)
        inputs.append(path);witnesses.append(dict(field=name,**source))
    for relative in ['backend/Backend.scala','backend/ExecuteSequencer.scala','backend/IssueQueue.scala','backend/RegisterAccess.scala','backend/RegisterFile.scala','exu/ExecutionUnit.scala','exu/int/IntegerPipe.scala','common/Parameters.scala']:
        inputs.append(ROOT/'third_party/saturn/src/main/scala'/relative)
    if sha(header)!=initial_header_sha256:raise ValueError('Component source changed during qualification')
    snapshots=out/'inputs';snapshots.mkdir()
    for p in dict.fromkeys(inputs):
        if p.stat().st_size<8*1024*1024:shutil.copy2(p,snapshots/sha(p))
    report=dict(schema='iris.rvv_integer_VADD_per_EG_source_differential.v1',**{'pass':True},
        profile='saved Compute128 source; applies to identical harts0/1 geometry',
        full_unit_runs=len(rows),commands=sum(r['commands']for r in rows),edge_field_checks=sum(r['edge_checks']for r in rows),
        microissues=sum(r['microissues']for r in rows),physical_write_beats=sum(r['physical_write_beats']for r in rows),
        full_unit_rows=rows,numeric_full_unit_runs=len(numeric_rows),numeric_full_unit_rows=numeric_rows,independent_output_bytes=sum(x['output_bytes']for x in numeric_rows),numeric_microissues=sum(x['microissues']for x in numeric_rows),numeric_physical_write_beats=sum(x['physical_write_beats']for x in numeric_rows),numeric_service_scope='actual accepted VSE8 Put byte/mask outputs after fullVADD drain; explicit identityTLB and synthetic ACKdelay2+seedmod5, Aready periodicbackpressure; no memorylatency claim',source_mutation_controls=mutant_rows,sequencer_port_rows=seq_rows,finite_API_guards=guard_rows,
        source_witnesses=witnesses,source_RTL_modified=False,native_integrated=False,hardware_contacted=False,
        FPGA_labels_or_fit_used=False,full_CPU_flags_knownness_and_numeric_publication_qualified=False,numerical_VADD_outputs_verified=True,
        limitations=['Integer VADD.VV SEW8/16/32/64 fullVLmax unmasked aligned LMUL only; no other ALU/widening/reduction/masked/vstart operations.',
          'Full-unit tests use actual EX/PFC retirement, VDQ inputs and read-only source observations; no readiness/state injection.',
          'External WAR/other-unit masks and read/write-port backpressure are differential at the original sequencer input boundary, not whole-SMP integration.',
          'Finite modular VADD output bytes checked from actualVMV initialized source registers through physical VSE8outputs; no CPU/IRQ/trap cancellation/publication or modelknownness certification.',
          'Reference is explicit two-state saved-unit simulation with reset/scrub; no image/loaded-FPGA attestation or host-speed claim.'],
        argv=commands,input_sha256={str(p):sha(p)for p in dict.fromkeys(inputs)},
        source_snapshots={str(p):sha(p)for p in snapshots.iterdir()},
        executable_sha256={str(p):sha(p)for p in (out/'probe',out/'numeric-probe',seq/'obj/VIntegerSourceSeq',out/'guards-optimized',out/'guards-checked')})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(pass_=True,full_unit_runs=len(rows),source_edge_checks=report['edge_field_checks'],report_sha256=sha(out/'report.json'))))

if __name__=='__main__':main()
