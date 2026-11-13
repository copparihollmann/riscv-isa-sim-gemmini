#!/usr/bin/env python3
"""Time the exact buffered ELF and read completed records via Spike's debugger.

This stops intentionally after the measured work and numeric checks, before the
bulk console loop. It never claims normal guest exit or end-to-end timing.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from validate import check_rows

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(text,corpus,layout):
    lines=text.splitlines()
    if not lines or lines[0]!=':' or any(not re.fullmatch(r'0x[0-9a-f]{16}',v) for v in lines[1:]):
        raise ValueError('Unexpected debugger output/trap')
    values=[int(v,16) for v in lines[1:]]
    count=corpus['expected_region_count']
    if (len(values)!=6+8*count or values[:3]!=[0,count,len(corpus['cases'])]
            or layout['fields']!=['case_index','hart','start','end','instret','checksum','expected','pass']):
        raise ValueError('Incomplete buffered measurement/case sentinel or record geometry')
    rows=[];expected_order=[(i,h) for i,c in enumerate(corpus['cases']) for h in range(3) if c['mask']&(1<<h)]
    for index in range(count):
        case_index,hart,start,end,instret,checksum,expected,passed=values[3+8*index:3+8*index+8]
        if (case_index,hart)!=expected_order[index] or passed!=1:raise ValueError('Wrong record order/identity/numeric failure')
        case=corpus['cases'][case_index]
        rows.append({key:case[key] for key in ('case_id','parent_case_id','suite','trial_id')})
        rows[-1].update(hart=hart,region='kernel',start_cycle=start,end_cycle=end,instret_delta=instret,
                        checksum=checksum,expected_checksum=expected,pass_=True)
        rows[-1]['pass']=rows[-1].pop('pass_')
    check_rows(rows,corpus)
    return rows


def qualify_prefix(path,rows,elf,rom):
    raw=Path(path).read_bytes();cut=raw.rfind(b'\n')+1
    records=[json.loads(line) for line in raw[:cut].splitlines()]
    by_key={};last={};instructions=Instructions(elf,rom)
    for record in records:
        h=record['hart'];seq=record['sequence']
        if (record.get('schema')!='iris.empirical.prefix.v1' or h not in (0,1,2)
                or seq<=last.get(h,0) or record['raw']!=instructions.read(record['pc'])):
            raise ValueError('Wrong or unordered actual prefix CSR/ELF')
        last[h]=seq
        if record.get('result_discarded'):continue
        key=h,record['value']
        if key in by_key:raise ValueError('Ambiguous actual CSR read value')
        by_key[key]=record
    identities={record['calibration_identity'] for record in records}
    if len(identities)!=1:raise ValueError('Mixed/absent fixture identity')
    for row in rows:
        a,b=[by_key[(row['hart'],row[key])] for key in ('start_cycle','end_cycle')]
        if (a['sequence']>=b['sequence'] or a['read_cycle']>=b['read_cycle']
                or a['csr'] not in (0xB00,0xC00) or b['csr'] not in (0xB00,0xC00)):
            raise ValueError('Invalid actual measured CSR endpoints')
        row.update(begin_pc=a['pc'],end_pc=b['pc'],begin_read_cycle=a['read_cycle'],end_read_cycle=b['read_cycle'],
                   observation_source='post_ROI_debugger_known_memory_readback')
    return {'actual_CSR_ELF_boundary_joins':2*len(rows),'complete_prefix_records':len(records),
            'preserved_unterminated_final_prefix_bytes':len(raw)-cut,'calibration_identity':next(iter(identities))}


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--native',type=Path,required=True)
    p.add_argument('--uart',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=float,default=900)
    p.add_argument('--normal-prefix',type=Path)
    a=p.parse_args();build=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    corpus=json.loads((build/'corpus.json').read_text());layout=json.loads((build/'readback-layout.json').read_text())
    elf=build/'campaign.elf'
    if layout['elf_sha256']!=sha(elf):raise ValueError('Changed readback ELF')
    objects=layout['objects'];get=lambda name:objects[name]['address']
    if not layout['file_backed_initial_sentinel_verified']:raise ValueError('Known file-backed debugger sentinel required')
    commands=['rs 0',f'while mem {get("buffered_measurements_done"):x} ffffffffffffffff']
    commands += [f'mem {get(name):x}' for name in ('buffered_measurements_done','buffered_record_count','buffered_case_count')]
    base=get('buffered_records');commands += [f'mem {v:x}' for v in range(base,base+objects['buffered_records']['size'],8)]
    commands += ['pc 0','pc 1','pc 2','quit']
    (out/'commands.txt').write_text('\n'.join(commands)+'\n')
    dma='rv64gcv_zfh_zvfh_zvl256b_zvbb'
    compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
    argv=[str(a.native.resolve()),'--iris-vme','--isa='+dma,'--hart-isa=0:'+compute,'--hart-isa=1:'+compute,
        '--hart-isa=2:'+dma,'-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
        '--device=sifive_uart,0x10020000','--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),
        '--dtb='+str(ROOT/'board/build/iris.dtb'),str(elf)]
    argv[1:1]=['-d','--debug-cmd='+str(out/'commands.txt'),'--iris-timing-fixture='+str(a.fixture.resolve()),'--extlib='+str(a.uart.resolve())]
    (out/'argv.json').write_text(json.dumps(argv,indent=2)+'\n')
    paths=[a.native.resolve(),a.uart.resolve(),a.fixture.resolve(),elf,build/'corpus.json',build/'build.json',
           build/'readback-layout.json',out/'commands.txt',out/'argv.json',Path(__file__).resolve(),Path(__file__).with_name('validate.py')]
    paths += [Path(v.split('=',1)[1]) for v in argv if v.startswith(('--iris-bootrom=','--dtb='))]
    inputs={str(f):sha(f) for f in paths}
    r={'schema':'iris.buffered_campaign_native_readback.v1','status':'running','argv':argv,
       'input_sha256':inputs,'hardware_contacted':False,'global_heldout_timings_consumed':False,
       'normal_guest_exit_verified':False,'whole_run_timing_or_speed_claim':False}
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
        if r['debugger_process_exit_status']!=0:raise ValueError('Native failed/stopped before measurements completed')
        rows=decode((out/'stderr').read_text(),corpus,layout)
        rom=next(v.split('=',1)[1] for v in argv if v.startswith('--iris-bootrom='))
        r.update(qualify_prefix(out/'features.jsonl',rows,elf,rom))
        if a.normal_prefix:
            n=Path(a.normal_prefix).read_bytes();normal_records=[json.loads(v) for v in n[:n.rfind(b'\n')+1].splitlines()]
            d=(out/'features.jsonl').read_bytes();debug_records=[json.loads(v) for v in d[:d.rfind(b'\n')+1].splitlines()]
            if normal_records[:len(debug_records)]!=debug_records:raise ValueError('Debugger changes normal modeled prefix')
            r['normal_prefix_timing_invariance_verified']=True
            r['input_sha256'][str(a.normal_prefix.resolve())]=sha(a.normal_prefix)
        for path,digest in inputs.items():
            if sha(path)!=digest:raise ValueError('Execution input changed '+path)
        (out/'regions.jsonl').write_text(''.join(json.dumps(v,sort_keys=True)+'\n' for v in rows))
        r.update(status='completed_measured_regions_with_intentional_debugger_stop',pass_=True,regions=len(rows),all_numeric_goldens_passed=True)
        r['pass']=r.pop('pass_')
    except (ValueError,KeyError,TypeError) as error:r.update(status='failed',pass_=False,error=str(error));r['pass']=r.pop('pass_')
    r['output_sha256']={str(f):sha(f) for f in out.iterdir() if f.name in ('stdout','stderr','features.jsonl','regions.jsonl')}
    (out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r.get(k) for k in ('status','pass','host_seconds','regions','error')}))
    if not r['pass']:raise SystemExit(1)


if __name__=='__main__':main()
