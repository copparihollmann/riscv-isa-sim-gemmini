#!/usr/bin/env python3
"""Strict source-derived scalar counter contract; preserves the original collector."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.run_functional import symbols
from iris_model.guest_regions import Instructions
from iris_model.counter_regions import observations
MASK=(1<<64)-1
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def contract(elf):
    table=symbols(elf);code=Instructions(elf);result={}
    for kind,name in enumerate(('scalar_dep256','scalar_ind256')):
        pc=table[name];registers={0:0};reads=[];body=[]
        for _ in range(400):
            raw=code.read(pc)
            if raw&3!=3:raise ValueError('probe instruction compression changed')
            rd=(raw>>7)&31;rs=(raw>>15)&31;funct=(raw>>12)&7
            if raw&127==0x73:
                csr=raw>>20
                if funct!=2 or rs!=0 or csr not in (0xb00,0xb02,0xc00,0xc02):raise ValueError('counter bracket encoding changed')
                reads.append(dict(pc=pc,raw=raw,csr=csr,destination=rd))
                if len(reads)==4:break
            else:
                if raw&0x707f!=0x13:raise ValueError('non-ADDI in straight-line source probe')
                imm=raw>>20;imm=imm-4096 if imm&2048 else imm
                if len(reads)==2:
                    if imm!=1 or rs!=rd:raise ValueError('ALU body is no longer an increment chain')
                    body.append(raw)
                if rs not in registers:raise ValueError('ALU checksum depends on unknown initial state')
                if rd:registers[rd]=(registers[rs]+imm)&MASK
            pc+=4
        if len(reads)!=4 or len(body)!=256:raise ValueError('source probe bracket/body coverage changed')
        if [r['csr']&0xff for r in reads]!=[0,2,2,0]:raise ValueError('unexpected counter bracket order')
        checksum=registers[5] if kind==0 else sum(registers[r] for r in (5,6,7,28,12,13,14,15))&MASK
        result[kind]=dict(name=name,reads=reads,operations=len(body),checksum=checksum)
    return result


def decode(path,rules):
    lines=Path(path).read_text().splitlines()
    if len(lines)!=56 or any(not re.fullmatch('[0-9a-f]{16}',line) for line in lines):raise ValueError('invalid exact448-byte signature')
    words=[int(line,16) for line in lines]
    if words[:8]!=[0x495249535343414c,1,0,1,1,1,0,0]:raise ValueError('incomplete/failed mailbox')
    rows=[]
    for hart in range(3):
        for kind in range(2):
            first,last,irfirst,irlast,checksum,ops,pad0,pad1=words[8+hart*16+kind*8:16+hart*16+kind*8]
            rule=rules[kind]
            loses_open_read=hart<2 and rule['reads'][1]['csr']==0xb02
            expected_ir=rule['operations']+(0 if loses_open_read else 1)
            if last<=first or ((irlast-irfirst)&MASK)!=expected_ir or checksum!=rule['checksum'] or ops!=rule['operations'] or pad0 or pad1:
                raise ValueError('source counter/checksum contract mismatch')
            rows.append(dict(hart=hart,kernel='dependent256' if kind==0 else 'independent256',kind=kind,
                             start_cycle=first,end_cycle=last,cycles=last-first,instret_delta=(irlast-irfirst)&MASK,
                             checksum=checksum,alu_operations=ops,expected_visible_instret=expected_ir))
    return rows


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--binary',type=Path,default=ROOT/'build/spike-counter-policy-v1/spike')
    parser.add_argument('--uart',type=Path,default=ROOT/'build/spike-counter-policy-v1/libsifive_uart.so')
    parser.add_argument('--build',type=Path,default=ROOT/'build/scalar-rtl-probe-v1')
    parser.add_argument('--reference',type=Path,default=ROOT/'build/scalar-rtl-reference-v1/signature')
    parser.add_argument('--launch-receipt',type=Path,default=ROOT/'build/scalar-rtl-pipeline-v2/results.json')
    parser.add_argument('--output',type=Path,default=ROOT/'build/counter-policy-v1-scalar-contract')
    parser.add_argument('--fixture',type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
    (out/'results.json').write_text('{"status":"in_progress","calibrated":false}\n')
    build=json.loads((args.build/'build.json').read_text());elf=Path(build['elf']);rules=contract(elf)
    if sha(elf)!=build['elf_sha256']:raise RuntimeError('probe ELF changed')
    reference=decode(args.reference,rules)
    launcher=json.loads(args.launch_receipt.read_text());argv=list(launcher['argv'])
    if Path(argv[-1]).resolve()!=elf.resolve():
        parent=Path(argv[-1])
        if build.get('parent_elf_sha256')!=sha(parent):raise ValueError('same-ELF launch receipt mismatch')
        old,new=parent.read_bytes(),elf.read_bytes()
        changes=build.get('instruction_changes',[])
        expected=bytearray(old)
        if len(changes)!=8 or len(old)!=len(new):raise ValueError('alias control derivation changed')
        for change in changes:
            offset=change['file_offset'];before=int.from_bytes(old[offset:offset+4],'little')
            if before!=change['old_instruction'] or change['new_instruction']!=(before+0x10000000):
                raise ValueError('alias control changed more than a CSR address field')
            expected[offset:offset+4]=change['new_instruction'].to_bytes(4,'little')
        if bytes(expected)!=new:raise ValueError('alias ELF has unrecorded changes')
        argv[-1]=str(elf)
    argv[0]=str(args.binary.resolve())
    if args.fixture:argv=['--iris-timing-fixture='+str(args.fixture.resolve()) if a.startswith('--iris-timing-fixture=') else a for a in argv]
    argv=['--extlib='+str(args.uart.resolve()) if a.startswith('--extlib=') else
          '--iris-timing-trace='+str(out/'graph.json') if a.startswith('--iris-timing-trace=') else
          '+signature='+str(out/'signature') if a.startswith('+signature=') else a for a in argv]
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    initial=(sha(args.binary),sha(args.uart));start=time.perf_counter()
    p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=90);elapsed=time.perf_counter()-start
    (out/'stdout').write_text(p.stdout);(out/'stderr').write_text(p.stderr)
    if p.returncode:raise RuntimeError('counter-policy scalar process failed: '+p.stderr)
    model=decode(out/'signature',rules);graph=json.loads((out/'graph.json').read_text());reads=observations(graph,Instructions(elf,ROOT/'board/evidence/bootrom.rv64.img'))
    table=[]
    for actual,expected in zip(model,reference):
        hart,kind=actual['hart'],actual['kind'];rule=rules[kind]
        matches=[]
        for index in (0,3):
            candidates=[r for r in reads if r['hart']==hart and r['pc']==rule['reads'][index]['pc'] and
                        r['value']==actual['start_cycle' if index==0 else 'end_cycle']]
            if len(candidates)!=1:raise RuntimeError('same-ELF physical/read-value boundary ambiguous')
            matches.append(candidates[0])
        span=matches[1]['read_cycle']-matches[0]['read_cycle'];divider=graph['hart_cycle_dividers'][hart]
        if span%divider:raise RuntimeError('read endpoints not on the same hart clock')
        predicted=span//divider-(1 if hart<2 and rule['reads'][0]['csr']==0xb00 else 0)
        if predicted!=actual['cycles']:raise RuntimeError('source write-over-increment does not match visible mcycle interval')
        table.append(dict(hart=hart,kernel=actual['kernel'],model_cycles=actual['cycles'],reference_cycles=expected['cycles'],
                          signed_error_percent=100*(actual['cycles']-expected['cycles'])/expected['cycles'],
                          model_instret_delta=actual['instret_delta'],reference_instret_delta=expected['instret_delta'],
                          model_physical_read_span=span//divider,source_counter_contract_matches=True))
    # Corruptions must still be refused. Source-specific expected counts do not
    # admit wrong checksums, missing work, padding, or the former hart0 count.
    negatives=[];original=(out/'signature').read_text().splitlines()
    wrong_count=256 if rules[0]['reads'][1]['csr']==0xc02 else 257
    for name,index,value in [('wrong_count',11,int(original[10],16)+wrong_count),('wrong_checksum',12,0),('wrong_operations',13,255),('bad_padding',14,1)]:
        changed=list(original);changed[index]=f'{value:016x}';path=out/(name+'.signature');path.write_text('\n'.join(changed)+'\n')
        try:decode(path,rules)
        except ValueError:negatives.append(name)
        else:raise RuntimeError('corrupted source contract admitted: '+name)
    if (sha(args.binary),sha(args.uart))!=initial:raise RuntimeError('native/plugin changed while running')
    used_fixture=Path(next(a.split('=',1)[1] for a in argv if a.startswith('--iris-timing-fixture=')))
    extra=[elf,args.build/'build.json',args.reference,used_fixture]
    source_inputs={'pipeline/check_scalar_counter_contract.py':sha(__file__),
                   'build/pipeline-csr-proof-closed/manifest.json':sha(ROOT/'build/pipeline-csr-proof-closed/manifest.json'),
                   'build/csr-phase-proof-v2/report.json':sha(ROOT/'build/csr-phase-proof-v2/report.json')}
    source_inputs.update({str(p.resolve().relative_to(ROOT)):sha(p) for p in extra})
    report=dict(schema='iris.scalar_source_counter_contract.v1',status='passed_source_counter_contract',argv=argv,exit_status=p.returncode,
                binary_sha256=initial[0],uart_sha256=initial[1],elf_sha256=sha(elf),reference_signature_sha256=sha(args.reference),
                model_signature_sha256=sha(out/'signature'),graph_sha256=sha(out/'graph.json'),rules=rules,table=table,negative_controls=negatives,
                source_sha256=source_inputs,
                host_seconds=elapsed,original_collector_modified=False,calibrated=False,held_out_validation=False,
                timing_qualified=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],table=table,receipt=str(out/'results.json'))))


if __name__=='__main__':main()
