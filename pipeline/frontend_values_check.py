#!/usr/bin/env python3
"""Prove forwarded pure values with integer and actual two-hart-type ALU oracles."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pipeline.alu_corpus import corpus,evaluate,NAMES,REGISTERS

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    program=corpus(32768,0x35901887);counts=Counter();rng=random.Random(0x729536);corners=[0,1,(1<<64)-1,1<<63,(1<<63)-1,0xffffffff,0xffffffff80000000,0x100000000]
    lines=[]
    for i,original in enumerate(program['instructions']):
        op={**original,'rd':5,'word':(original['word']&~(31<<7))|(5<<7)}
        registers={r:(corners[(i+r)%len(corners)] if i<1024 else rng.getrandbits(64)) for r in range(32)};registers[0]=0
        pc=0x80000000+4*i
        one=dict(initial_registers=registers,instructions=[op]);want=evaluate(one,pc)[REGISTERS.index(5)]
        lines.append([op['word'],pc,registers[op['rs1']],registers[op['rs2']],want]);counts[op['name']]+=1
    if set(counts)!=set(NAMES):raise ValueError('30 source pure-ALU groups not covered')
    trace=out/'alu.tsv';trace.write_text(''.join(' '.join(map(str,row))+'\n' for row in lines))
    compiler=Path(shutil.which('g++')).resolve();binary=out/'test_values';test=ROOT/'pipeline/test_frontend_values.cpp';commands=[]
    argv=[str(compiler),'-std=c++20','-O2','-Wall','-Wextra','-Werror',str(test),'-o',str(binary)];commands.append(argv)
    r=subprocess.run(argv,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('private value-flow build failed: '+r.stderr)
    r=subprocess.run([str(binary),str(trace)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('private value-flow differs: '+r.stderr)
    unit_stdout=r.stdout
    perl=Path('/scratch/eygao/iris-cy/.conda-env/bin/perl').resolve();verilator=perl.with_name('verilator')
    sources=[ROOT/'pipeline/frontend_values_rtl.sv',ROOT/'build/rtl-verilator/gen-collateral/RocketALU.sv',ROOT/'build/rtl-verilator/gen-collateral/RocketALU_6.sv']
    rt=ROOT/'pipeline/test_frontend_values_rtl.cpp'
    hardware_commands=[[str(perl),str(verilator),'--cc','--exe','-Wno-fatal','--top-module','IrisPureAlu','--Mdir',str(out/'obj'),*[str(p) for p in sources],str(rt),'-CFLAGS','-std=c++20 -O2 -Wall -Wextra -Werror'],
                       ['make','-C',str(out/'obj'),'-f','VIrisPureAlu.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,argv in enumerate(hardware_commands):
        r=subprocess.run(argv,text=True,capture_output=True);(out/f'rtl-build-{i}.log').write_text(r.stdout+r.stderr);commands.append(argv)
        if r.returncode:raise RuntimeError('source ALU oracle build failed: '+r.stderr)
    rb=out/'obj/VIrisPureAlu';r=subprocess.run([str(rb),str(trace)],text=True,capture_output=True);(out/'rtl.stdout').write_text(r.stdout);(out/'rtl.stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source ALU output differs: '+r.stderr)
    files=[Path(__file__).resolve(),ROOT/'pipeline/alu_corpus.py',test,rt,ROOT/'pipeline/frontend_values.hpp',*sources,ROOT/'third_party/rocket-chip/src/main/scala/rocket/ALU.scala',ROOT/'third_party/rocket-chip/src/main/scala/rocket/IDecode.scala',compiler,perl,verilator]
    report=dict(schema='iris.frontend.forwarded_values_component.v1',status='passed_integer_and_RTL_ALU_value_oracles',rows=len(lines),instruction_counts=counts,stdout=unit_stdout,rtl_stdout=r.stdout,input_sha256={str(p):sha(p) for p in files},commands=commands,
                binary_sha256=sha(binary),rtl_binary_sha256=sha(rb),trace_sha256=sha(trace),
                source_pins=dict(rocket_chip='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0',shuttle='a536ed1df91a0f65770e36758291d02a8cb929c4'),
                scope='Private result values and versioned RAW/WAW references for30 source pure ALUs; known full-width values checked against integer and two actual ALU modules. COM/cancel/unknown controls are host unit cases, not a live native pipeline.',
                native_integration=False,architectural_state_mutated_by_component=False,partial_bit_knownness_modeled=False,calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(unit_stdout.strip());print(r.stdout.strip())
if __name__=='__main__':main()
