#!/usr/bin/env python3
"""Qualify the first K completed cases of the unchanged buffered fitting ELF.

An intentional debugger stop produces a partial calibration dataset. No final
guest exit, future cases, whole-run accuracy or MIPS result is implied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from replay_v2 import qualify_prefix
from validate_priority import check_rows

ROOT=Path(__file__).resolve().parents[2]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(text,corpus,k):
    cases=corpus['cases'][:k]
    order=[(i,h) for i,c in enumerate(cases) for h in range(3) if c['mask']&(1<<h)]
    lines=text.splitlines()
    if not lines or lines[0]!=':' or any(not re.fullmatch(r'0x[0-9a-f]{16}',v) for v in lines[1:]):
        raise ValueError('Unexpected checkpoint debugger output/trap')
    words=[int(v,16) for v in lines[1:]]
    if len(words)!=6+8*len(order) or words[:3]!=[(1<<64)-1,len(order),k]:
        raise ValueError('Exact partial checkpoint sentinel/case/record count required')
    rows=[]
    for n,(case_index,hart) in enumerate(order):
        values=words[3+8*n:3+8*n+8]
        if values[:2]!=[case_index,hart] or values[-1]!=1:raise ValueError('Wrong partial record identity/order/numeric failure')
        case=cases[case_index]
        row={key:case[key] for key in ('case_id','parent_case_id','suite','trial_id')}
        row.update(hart=hart,region='kernel',start_cycle=values[2],end_cycle=values[3],
                   instret_delta=values[4],checksum=values[5],expected_checksum=values[6])
        row['pass']=True;rows.append(row)
    partial=dict(corpus,cases=cases,expected_region_count=len(order))
    check_rows(rows,partial)
    return rows


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('build','native','uart','fixture','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--cases',type=int,default=1870)
    p.add_argument('--timeout',type=float,default=3600)
    p.add_argument('--prefix-reference',type=Path)
    a=p.parse_args();build=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    corpus=json.loads((build/'corpus.json').read_text());layout=json.loads((build/'readback-layout.json').read_text())
    if not 1<=a.cases<len(corpus['cases']):raise ValueError('Checkpoint must be a proper nonempty case prefix')
    elf=build/'campaign.elf'
    if layout['elf_sha256']!=sha(elf) or not layout['file_backed_initial_sentinel_verified']:
        raise ValueError('Exact known-sentinel ELF required')
    count=sum(bin(c['mask']).count('1') for c in corpus['cases'][:a.cases])
    objects=layout['objects'];address=lambda key:objects[key]['address']
    # The same-ELF823 first ROI has ~6.954m retired instructions per hart.
    # 25m completed steps passes its BSS initialization. Other epochs retain
    # strict knownness: premature counter reads must fail, never assume zero.
    commands=['rs 25000000',f'until mem {address("buffered_case_count"):x} {a.cases:x}']
    commands += [f'mem {address(key):x}' for key in ('buffered_measurements_done','buffered_record_count','buffered_case_count')]
    base=address('buffered_records');commands += [f'mem {v:x}' for v in range(base,base+64*count,8)]
    commands += ['pc 0','pc 1','pc 2','quit']
    if any(len(line)>40 for line in commands):raise ValueError('Debugger command length exceeds upstream limit')
    (out/'commands.txt').write_text('\n'.join(commands)+'\n')
    dma='rv64gcv_zfh_zvfh_zvl256b_zvbb'
    compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
    rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb'
    argv=[str(a.native.resolve()),'-d','--debug-cmd='+str(out/'commands.txt'),'--iris-vme','--isa='+dma,
        '--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:'+dma,'-p3',
        '-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
        '--extlib='+str(a.uart.resolve()),'--device=sifive_uart,0x10020000','--iris-bootrom='+str(rom),
        '--dtb='+str(dtb),'--iris-timing-fixture='+str(a.fixture.resolve()),str(elf)]
    paths=[a.native.resolve(),a.uart.resolve(),a.fixture.resolve(),rom,dtb,elf,build/'corpus.json',
        build/'build.json',build/'readback-layout.json',out/'commands.txt',Path(__file__).resolve(),
        Path(__file__).with_name('replay_v2.py'),Path(__file__).with_name('validate_priority.py')]
    inputs={str(f):sha(f) for f in paths}
    r={'schema':'iris.buffered_priority_checkpoint_replay.v2','status':'running','argv':argv,
        'input_sha256':inputs,'expected_prefix_cases':a.cases,'expected_prefix_regions':count,
        'partial_dataset':True,'normal_guest_exit_verified':False,'whole_run_timing_or_speed_claim':False,
        'hardware_contacted':False,'global_heldout_timings_consumed':False}
    (out/'run.json').write_text(json.dumps(r,indent=2)+'\n');started=time.monotonic()
    with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:
        child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True,
            env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(out/'features.jsonl')))
        r['pid']=child.pid;(out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
        try:r['debugger_process_exit_status']=child.wait(timeout=a.timeout)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            r.update(debugger_process_exit_status=child.returncode,timed_out=True)
    r['host_seconds']=time.monotonic()-started
    try:
        if r['debugger_process_exit_status']!=0 or r.get('timed_out'):raise ValueError('Checkpoint not reached within owned bound')
        rows=decode((out/'stderr').read_text(),corpus,a.cases)
        r.update(qualify_prefix(out/'features.jsonl',rows,elf,rom))
        identities=[line.split()[2] for line in a.fixture.read_text().splitlines() if line.startswith('empirical_profile ')]
        if identities!=[r['calibration_identity']]:raise ValueError('Fixture/prefix identity mismatch')
        if a.prefix_reference:
            ref=a.prefix_reference.read_bytes();refrows=[json.loads(v) for v in ref[:ref.rfind(b'\n')+1].splitlines()]
            raw=(out/'features.jsonl').read_bytes();mine=[json.loads(v) for v in raw[:raw.rfind(b'\n')+1].splitlines()]
            common=min(len(refrows),len(mine))
            if not common or refrows[:common]!=mine[:common]:raise ValueError('Checkpoint debugger changes common model history')
            r.update(identical_common_reference_prefix_records=common,
                prefix_reference_kind='Preserved same-ELF/native/fixture partial debugger replay; not normal complete guest')
            inputs[str(a.prefix_reference.resolve())]=sha(a.prefix_reference)
        for path,digest in inputs.items():
            if sha(path)!=digest:raise ValueError('Execution input changed '+path)
        (out/'regions.jsonl').write_text(''.join(json.dumps(v,sort_keys=True)+'\n' for v in rows))
        r.update(status='passed_completed_case_prefix',pass_=True,regions=len(rows),cases=a.cases,all_prefix_goldens_passed=True)
        r['pass']=r.pop('pass_')
    except (ValueError,KeyError,TypeError) as error:r.update(status='failed',pass_=False,error=str(error));r['pass']=r.pop('pass_')
    r['output_sha256']={str(f):sha(f) for f in out.iterdir() if f.name in ('stdout','stderr','features.jsonl','regions.jsonl')}
    (out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({key:r.get(key) for key in ('status','pass','host_seconds','cases','regions','error')}))
    if not r['pass']:raise SystemExit(1)


if __name__=='__main__':main()
