#!/usr/bin/env python3
"""Full priority-v2 readback: all4050 regions, including heavy contention.

Adapted from frozen replay_v2; original reader and selected prefix remain intact.

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
from validate_priority import check_rows

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
        for key,limit in [('hart',3),('sequence',1<<64),('value',1<<64),('read_cycle',1<<64),('pc',1<<64),('raw',1<<32),('csr',1<<12),('destination',32)]:
            if type(record.get(key))is not int or not 0<=record[key]<limit:
                raise ValueError('Invalid typed actual prefix '+key)
        encoded=record['raw'];csr=encoded>>20;rd=(encoded>>7)&31
        if (encoded&127!=0x73 or (encoded>>12)&7 not in (1,2,3,5,6,7) or csr not in (0xB00,0xC00)
                or record.get('csr')!=csr or record.get('destination')!=rd
                or type(record.get('result_discarded'))is not bool or record['result_discarded']!=(rd==0)):
            raise ValueError('Actual prefix must encode returning/discarded mcycle')
        if (record.get('schema')!='iris.empirical.prefix.v1' or h not in (0,1,2)
                or seq<=last.get(h,-1) or record['raw']!=instructions.read(record['pc'])):
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


def analyze_existing(build,directory,output):
    build,directory,output=Path(build).resolve(),Path(directory).resolve(),Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    original=directory/'run.json';run=json.loads(original.read_text())
    if (run.get('schema')!='iris.buffered_priority_full_native_readback.v2' or run.get('status')=='running'
            or run.get('debugger_process_exit_status')!=0 or run.get('timed_out')
            or run.get('normal_guest_exit_verified')is not False or run.get('hardware_contacted')is not False):
        raise ValueError('A quiescent successful intentional debugger stop is required')
    for path,digest in {**run['input_sha256'],**run['output_sha256']}.items():
        if sha(path)!=digest:raise ValueError('Changed original execution input/output '+path)
    corpus=json.loads((build/'corpus.json').read_text());layout=json.loads((build/'readback-layout.json').read_text())
    elf=build/'campaign.elf'
    if sha(elf)!=layout['elf_sha256'] or run['argv'][-1]!=str(elf):raise ValueError('Actual exact ELF mismatch')
    rows=decode((directory/'stderr').read_text(),corpus,layout)
    rom=next(v.split('=',1)[1] for v in run['argv'] if v.startswith('--iris-bootrom='))
    proof=qualify_prefix(directory/'features.jsonl',rows,elf,rom)
    fixture=Path(next(v.split('=',1)[1] for v in run['argv'] if v.startswith('--iris-timing-fixture=')))
    identities=[line.split()[2] for line in fixture.read_text().splitlines() if line.startswith('empirical_profile ')]
    if identities!=[proof['calibration_identity']]:raise ValueError('Executed fixture/prefix identity mismatch')
    regions=output/'regions.jsonl';regions.write_text(''.join(json.dumps(v,sort_keys=True)+'\n' for v in rows))
    inputs={**run['input_sha256'],**run['output_sha256'],str(original):sha(original),
        str(Path(__file__).resolve()):sha(Path(__file__).resolve()),str(regions):sha(regions)}
    result={'schema':'iris.buffered_priority_full_readback_validation.v2','pass':True,
        'regions':len(rows),'all_numeric_goldens_passed':True,'normal_guest_exit_verified':False,
        'intentional_post_ROI_debugger_stop':True,'original_reader_status':run['status'],
        'original_reader_error':run.get('error'),'reader_repair':'Initial sequence0 is legal; exact typed CSR/ELF and monotonic sequences are checked.',
        'native_binary_sha256':sha(run['argv'][0]),'fixture_sha256':sha(fixture),
        'elf_sha256':sha(elf),'host_seconds':run['host_seconds'],'argv':run['argv'],
        'hardware_contacted':False,'global_heldout_timings_consumed':False,
        'whole_run_timing_or_speed_claim':False,'input_sha256':inputs,**proof}
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('pass','regions','host_seconds','original_reader_status')}))


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--native',type=Path)
    p.add_argument('--uart',type=Path);p.add_argument('--fixture',type=Path)
    p.add_argument('--analyze-existing',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=float,default=900)
    p.add_argument('--normal-prefix',type=Path)
    a=p.parse_args()
    if a.analyze_existing:
        return analyze_existing(a.build,a.analyze_existing,a.output)
    if any(v is None for v in (a.native,a.uart,a.fixture)):p.error('Fresh run requires --native, --uart and --fixture')
    build=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
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
    r={'schema':'iris.buffered_priority_full_native_readback.v2','status':'running','argv':argv,
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
