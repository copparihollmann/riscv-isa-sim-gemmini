#!/usr/bin/env python3
"""Independently preserve the one failed compiler gate and complete shipped values."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def signed_byte(x):return (x+128)%256-128
def float_word(integer):
    if integer==0:return 0
    sign=int(integer<0);value=abs(integer);exponent=value.bit_length()-1
    return (sign<<31)|((127+exponent)<<23)|((value-(1<<exponent))<<(23-exponent))


def check():
    out=ROOT/'build/empirical-9b2-Merlin-gemm-h1-failure-review-v1';out.mkdir(exist_ok=False)
    gate=ROOT/'build/empirical-9b2-guard-Merlin-gemm-h1-v1'
    control=ROOT/'build/empirical-9b2-guard-Merlin-gemm-h1-controller-v1'
    manifest=ROOT/'build/empirical-compute-9b2-package-v2/manifest.json'
    controller=json.loads((control/'run.json').read_text())
    if controller['status']!='failed'or controller.get('exit_status')!=1 or controller.get('timed_out')is not False:
        raise ValueError('Expected completed non-timeout failed front-door invocation')
    for name,wanted in controller['input_sha256'].items():
        if sha(name)!=wanted:raise ValueError('Actual invocation input changed')
    guest=(gate/'guest.c').read_text()
    dimensions={k:int(re.search(r'^#define '+k+r' (\d+)$',guest,re.M)[1])for k in ('M','N','K','WORKERS')}
    if dimensions!={'M':64,'N':64,'K':64,'WORKERS':1}:raise ValueError('Wrong actual gate shape/worker count')
    accumulator=[];quantized=[]
    for row in range(64):
        for col in range(64):
            total=sum(signed_byte(row*17+inner*11+3)*signed_byte(inner*13+col*7+5)for inner in range(64))
            accumulator.append(total&0xffffffff)
            quantized.append(float_word(max(-128,min(127,(total+512)//1024))))
    text=(gate/'shipped.stdout').read_text();actual={}
    for label in ('ACC_I32','OUT'):
        lines=[line.split()for line in text.splitlines()if line.startswith(label+' ')]
        if len(lines)!=1 or len(lines[0])!=4098 or lines[0][1]!='4096':raise ValueError('Incomplete full-word record')
        if any(not re.fullmatch('[0-9]+',v)for v in lines[0][2:]):raise ValueError('Invalid unsigned output token')
        actual[label]=list(map(int,lines[0][2:]))
        if any(v>0xffffffff for v in actual[label]):raise ValueError('Invalid output word width')
    if actual['ACC_I32']!=accumulator or actual['OUT']!=quantized or text.splitlines().count('DONE')!=1:
        raise ValueError('Shipped full-word values differ from independent integer oracle')
    declared=json.loads((gate/'golden.json').read_text())
    if declared!={'accumulator_u32':accumulator,'w8a8_f32_words':quantized}:raise ValueError('Generated oracle differs from independent arithmetic')
    regions=[list(map(int,line.split()[1:]))for line in text.splitlines()if line.startswith('REGION ')]
    if len(regions)!=1 or len(regions[0])!=4 or regions[0][0]!=0 or regions[0][2]<=regions[0][1]or regions[0][3]<=0:
        raise ValueError('Missing actual compute-worker counter boundaries')
    failure=(gate/'twin.stderr').read_text()
    match=re.fullmatch(r'FAST_SOURCE_FRONTEND_REQUIRED_RAS_TARGET_UNINITIALIZED pc=(\d+) head=(\d+) edge=(\d+)\n',failure)
    if not match or list(map(int,match.groups()[:2]))!=[0x80000598,3]or(gate/'twin.stdout').read_bytes():
        raise ValueError('Different failure than the expected strict source boundary')
    compiler=Path(controller['argv'][controller['argv'].index('--compiler')+1]);objdump=compiler.with_name('riscv64-unknown-elf-objdump');nm=compiler.with_name('riscv64-unknown-elf-nm')
    encodings=json.loads((gate/'encodings.json').read_text())['encodings']
    roles={k:encodings[k]for k in ('SF_MM_INT','SF_VTZERO_T','SF_VTMV_V_T','SF_VTDISCARD','SF_MSETMTYPE','SF_VSETTN','SF_VSETTM','SF_VSETTK')}
    audits={};runtime_symbol=None
    for kind in ('shipped','twin'):
        elf=gate/(kind+'.elf');listing=subprocess.check_output([str(objdump),'-d',str(elf)],text=True)
        (out/(kind+'.disassembly')).write_text(listing)
        counts={k:0 for k in roles}
        for line in listing.splitlines():
            fields=line.split()
            if len(fields)<2 or not fields[0].endswith(':')or not re.fullmatch('[0-9a-fA-F]{8}',fields[1]):continue
            raw=int(fields[1],16)
            for key,encoding in roles.items():counts[key]+=raw&encoding['mask']==encoding['match']
        if (kind=='shipped'and any(v==0 for v in counts.values()))or(kind=='twin'and any(counts.values())):
            raise ValueError('Actual executable kernel roles differ from declared variant')
        audits[kind]=counts
        symbols=subprocess.check_output([str(nm),'-S',str(elf)],text=True);(out/(kind+'.symbols')).write_text(symbols)
        if kind=='twin':
            for line in symbols.splitlines():
                f=line.split()
                if len(f)==4 and int(f[0],16)<=0x80000598<int(f[0],16)+int(f[1],16):runtime_symbol=f[3]
    inputs=[Path(__file__).resolve(),manifest,control/'run.json',control/'stdout',control/'stderr',compiler,objdump,nm,
        ROOT/'integration/iris-mlir/examples/iris/run.py',ROOT/'integration/iris-mlir/vme_kernel.py',
        ROOT/'integration/iris-mlir/vme_shim.py',ROOT/'integration/iris-mlir/source_facts.py',
        ROOT/'integration/iris-mlir/contracts/matrix_units.yaml',ROOT/'hardware/manifest.json',
        ROOT/'benchmarks/start.S',ROOT/'benchmarks/runtime.c',ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/link.ld']
    inputs.extend(p for p in gate.iterdir()if p.is_file())
    prefixes={}
    for kind in ('shipped','twin'):
        raw=(gate/(kind+'.features.jsonl')).read_bytes();end=raw.rfind(b'\n')+1
        records=[json.loads(line)for line in raw[:end].splitlines()]
        if not records or any(r['calibration_identity']!='iris-empirical-compute-fadd-shape-store-9b2-v2'for r in records):
            raise ValueError('Wrong actual captured calibration identity')
        prefixes[kind]={'complete_records':len(records),'unterminated_trailing_bytes':len(raw)-end}
    report={'schema':'iris.partial_Merlin_compiler_gate_review.v1','pass':True,'complete_compiler_gate_passed':False,
        'front_door_invocation':controller['argv'],'front_door_exit_status':1,'host_seconds':controller['host_seconds'],
        'published_manifest_sha256':sha(manifest),'native_binary_sha256':json.loads(manifest.read_text())['native_binary_sha256'],
        'shipped':{'full_accumulator_words_checked':4096,'full_W8A8_words_checked':4096,'independent_integer_oracle_passed':True,
            'terminal_DONE_observed':True,'actual_counter_regions':regions,'elf_sha256':sha(gate/'shipped.elf')},
        'twin':{'status':'strict_source_capability_refusal','architectural_trap_claimed':False,'full_output_validation_available':False,
            'actual_native_returncode_not_returned_in_aborted_upstream_receipt':True,'pc':int(match[1]),'pc_hex':hex(int(match[1])),
            'head':int(match[2]),'source_edge':int(match[3]),'symbol':runtime_symbol,'elf_sha256':sha(gate/'twin.elf')},
        'captured_prefixes':prefixes,'actual_disassembled_instruction_audit':audits,
        'remaining_three_gates_launched':False,'default_selection_changed':False,'hardware_contacted':False,
        'global_heldout_timings_consumed':False,'model_parameters_changed':False,'full_2pct_certified':False,
        'toolchain_closure':'Compiler/tool drivers and explicit sources bound; transitive system headers/libraries not fully enumerated.',
        'upstream_native_argv_receipt_available':False,'input_sha256':{str(p):sha(p)for p in inputs},
        'output_sha256':{str(p):sha(p)for p in out.iterdir()if p.is_file()}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'shipped_words_checked':8192,'twin_failure':report['twin'],'report_sha256':sha(out/'report.json')}))


if __name__=='__main__':check()
