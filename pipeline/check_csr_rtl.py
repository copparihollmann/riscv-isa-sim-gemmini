#!/usr/bin/env python3
"""Check source-specific CSR commands and edge semantics against saved Iris RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
MASK=(1<<64)-1
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wrapper(sources):
    lines=['module CsrPair(input clock,reset,input [11:0] address,input [31:0] instruction,',
           'input [2:0] shuttle_cmd,rocket_cmd,input [63:0] write_data,input [1:0] shuttle_retire,input rocket_retire,',
           'output [63:0] shuttle_data,rocket_data,output shuttle_read_illegal,shuttle_write_illegal,rocket_read_illegal,rocket_write_illegal);']
    for module,path,prefix in sources:
        ports=re.findall(r'^\s*(input|output)\s*(?:\[[^]]+\]\s*)?(\w+)\s*[,)]',path.read_text(),re.M)
        if len(ports)<50:raise RuntimeError('incomplete CSR port parse')
        selected={'clock':'clock','reset':'reset','io_ungated_clock':'clock','io_rw_addr':'address','io_rw_cmd':prefix+'_cmd',
                  'io_rw_wdata':'write_data','io_retire':prefix+'_retire','io_decode_0_inst':'instruction',
                  'io_rw_rdata':prefix+'_data','io_decode_0_read_illegal':prefix+'_read_illegal',
                  'io_decode_0_write_illegal':prefix+'_write_illegal'}
        if not set(selected).issubset({p for _,p in ports}):raise RuntimeError('required CSR probe ports missing')
        mappings=[]
        for kind,name in ports:
            expression=selected.get(name,"'0" if kind=='input' else '')
            mappings.append(f'.{name}({expression})')
        lines.append(module+' '+prefix+'('+','.join(mappings)+');')
    lines.append('endmodule')
    return '\n'.join(lines)+'\n'


def counter_step(before,address,cmd,data,retire):
    mc,ir,inhibit=before
    values={0xb00:mc,0xb02:ir,0xc00:mc,0xc02:ir,0x320:inhibit}
    read=values[address]
    after=[(mc+(not(inhibit&1)))&MASK,(ir+(0 if inhibit&4 else retire))&MASK,inhibit]
    if cmd in (5,6,7):
        value=data if cmd==5 else read|data if cmd==6 else read&~data
        if address==0xb00:after[0]=value&MASK
        elif address==0xb02:after[1]=value&MASK
        elif address==0x320:after[2]=value&5
    return read,after


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/pipeline-csr-source-proof')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
    (out/'results.json').write_text('{"status":"in_progress","timing_certified":false}\n')
    collateral=ROOT/'build/rtl-verilator/gen-collateral';sources=[]
    for module,prefix in [('CSRFile','shuttle'),('CSRFile_2','rocket')]:
        path=out/(module+'.sv');shutil.copyfile(collateral/path.name,path);sources.append((module,path,prefix))
    top=out/'CsrPair.sv';top.write_text(wrapper(sources));commands=[]
    perl=Path('/scratch/eygao/iris-cy/.conda-env/bin/perl');tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
    for name,argv in [('verilate',[str(perl),str(tool),'--cc','--exe','-Wno-fatal','--top-module','CsrPair','--Mdir',str(out/'obj'),
                                  str(top)]+[str(p) for _,p,_ in sources]+[str(ROOT/'pipeline/test_csr_rtl.cpp'),'-CFLAGS','-std=c++20 -O2']),
                      ('build',['make','-C',str(out/'obj'),'-f','VCsrPair.mk','-j8','CXX=g++','LINK=g++','AR=ar'])]:
        p=subprocess.run(argv,text=True,capture_output=True);(out/(name+'.log')).write_text(p.stdout+p.stderr)
        commands.append(dict(name=name,argv=argv,exit_status=p.returncode,log_sha256=sha(out/(name+'.log'))))
        if p.returncode:raise RuntimeError(name+' failed: '+p.stderr[-3000:])
    binary=out/'obj/VCsrPair';p=subprocess.run([str(binary)],capture_output=True,text=True)
    (out/'transcript.jsonl').write_text(p.stdout);(out/'stderr').write_text(p.stderr)
    if p.returncode:raise RuntimeError('CSR unit probe failed: '+p.stderr)
    rows=[json.loads(line) for line in p.stdout.splitlines()];failures=[];brackets=[];opening={};prior=None;macro={}
    for index,row in enumerate(rows):
        for core in ('shuttle','rocket'):
            expected_before=prior[core+'_after'] if prior is not None and row['cycle']==prior['cycle']+1 else [0,0,0]
            if row[core+'_before']!=expected_before:failures.append(dict(index=index,core=core,kind='reset_or_state_continuity',expected=expected_before,row=row))
            funct=(row['instruction']>>12)&7;rsfield=(row['instruction']>>15)&31
            command={0:0,1:5,2:6,3:7,5:5,6:6,7:7}[funct]
            readonly=funct in (2,3,6,7) and rsfield==0
            illegal=row['address'] in (0xc00,0xc02) and command>=4 and not readonly
            expected_cmd=2 if core=='rocket' and readonly else command
            if illegal:expected_cmd&=3
            if row[core+'_cmd']!=expected_cmd or row[core+'_illegal']!=int(illegal):
                failures.append(dict(index=index,core=core,kind='source_command_or_legality',expected_cmd=expected_cmd,expected_illegal=illegal,row=row))
            if funct in (5,6,7) and row['write_data']!=rsfield:failures.append(dict(index=index,kind='immediate_operand',row=row))
            expected_read,expected_after=counter_step(row[core+'_before'],row['address'],row[core+'_cmd'],row['write_data'],row[core+'_retire'])
            if row[core+'_read']!=expected_read or row[core+'_after']!=expected_after:failures.append(dict(index=index,core=core,row=row,expected_read=expected_read,expected_after=expected_after))
        if row['tag']=='bracket_open':opening=row
        if row['tag']=='bracket_close':
            brackets.append(dict(address=row['address'],op=row['op'],shuttle_delta=(row['shuttle_read']-opening['shuttle_read'])&MASK,
                                 rocket_delta=(row['rocket_read']-opening['rocket_read'])&MASK))
        if row['tag'].startswith('macro_'):macro[row['tag']]=row
        prior=row
    matrix=[r for r in rows if r['tag']=='instruction_matrix']
    if len(matrix)!=40 or len(brackets)!=16 or not rows:raise RuntimeError('CSR corpus incomplete')
    for row in brackets:
        expected=(256 if row['address'] in (0xb00,0xb02) else 257)
        if row['shuttle_delta']!=expected or row['rocket_delta']!=257:failures.append(dict(bracket=row,expected_shuttle=expected,expected_rocket=257))
    macro_result={core:{counter:(macro['macro_'+counter+'_close'][core+'_read']-macro['macro_'+counter+'_open'][core+'_read'])&MASK
                        for counter in ('cycle','instret')} for core in ('shuttle','rocket')}
    if macro_result!={'shuttle':{'cycle':258,'instret':256},'rocket':{'cycle':259,'instret':257}}:
        failures.append(dict(kind='same_macro_bracket',actual=macro_result))
    evidence=[]
    for repository,name,lines in [('shuttle','src/main/scala/exu/Core.scala',[[240,258],[444,487],[998,1010],[1082,1089]]),
                                  ('shuttle','src/main/scala/common/MicroOp.scala',[[57,62]]),
                                  ('rocket-chip','src/main/scala/rocket/RocketCore.scala',[[350,355],[960,965]]),
                                  ('rocket-chip','src/main/scala/rocket/IDecode.scala',[[117,124]]),
                                  ('rocket-chip','src/main/scala/rocket/CSR.scala',[[173,184],[646,650],[1292,1295],[1375,1380],[1712,1734]]),
                                  ('rocket-chip','src/main/scala/util/Counters.scala',[[41,69]])]:
        path=ROOT/'third_party'/repository/name;target=out/'source'/repository/name;target.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(path,target)
        evidence.append(dict(path=str(path.relative_to(ROOT)),sha256=sha(path),snapshot=str(target.relative_to(out)),lines=lines,
                             repository_sha=subprocess.check_output(['git','-C',str(ROOT/'third_party'/repository),'rev-parse','HEAD'],text=True).strip()))
    receipt=dict(schema='iris.shuttle.csr_edge_proof.v1',status='passed_component_csr_edge_proof' if not failures else 'failed',
                 rows=len(rows),instruction_cases=len(matrix),brackets=brackets,same_macro_component_deltas=macro_result,
                 failures=failures,commands=commands,
                 transcript_sha256=sha(out/'transcript.jsonl'),simulator_sha256=sha(binary),
                 source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).resolve(),ROOT/'pipeline/test_csr_rtl.cpp']},
                 sv_sha256={p.name:sha(p) for _,p,_ in sources},wrapper_sha256=sha(top),source_evidence=evidence,
                 source_fir_sha256=json.loads((ROOT/'build/rtl-verilator/manifest.json').read_text())['source_fir_sha256'],
                 tools={'perl_sha256':sha(perl),'verilator_script_sha256':sha(tool),
                        'verilator_binary_sha256':sha(tool.with_name('verilator_bin')),
                        'verilator_version':subprocess.check_output([str(perl),str(tool),'--version'],text=True).strip(),
                        'cxx_sha256':sha(Path(shutil.which('g++')).resolve()),
                        'cxx_version':subprocess.check_output(['g++','--version'],text=True).splitlines()[0]},
                 saved_design='chipyard.harness.TestHarness.IrisConfig',source_build_association_verified=False,
                 matches_ethan_firesim_image=False,native_model_changed=False,full_cpu_timing_certified=False,
                 scope='Counter-only CSRFile component transactions with all unrelated inputs explicitlyzero, plus source-derived Shuttle/Rocket command rewrites. COM read is pre-edge and explicit counter writes override same-edge increment. Does not guess full-pipeline counter read phase.')
    (out/'results.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(status=receipt['status'],rows=len(rows),failures=len(failures),receipt=str(out/'results.json'))))
    if failures:raise RuntimeError('independent CSR oracle mismatch')


if __name__=='__main__':main()
