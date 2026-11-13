#!/usr/bin/env python3
"""Fixed-parameter exact-ELF memory replay with strict post-ROI readback/CSR joins."""
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from memory_routes_current_audit_v2 import audit,rows_check,Elf
from empirical_live_features_v4 import difference
from iris_model.guest_regions import Instructions


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def decode(text,corpus,layout,elf):
    lines=text.splitlines()
    if not lines or lines[0]!=':'or any(not re.fullmatch(r'0x[0-9a-f]{16}',v)for v in lines[1:]):raise ValueError('Malformed debugger word stream/trap')
    words=[int(x,16)for x in lines[1:]];count=2592
    if len(words)!=9+count*8 or words[:3]!=[0,count,1512]or words[-6:-3]!=[0,count,1512]:raise ValueError('Incomplete or unstable completion/count footer')
    expected=[(i,h)for i,c in enumerate(corpus['cases'])for h in range(3)if c['mask']&(1<<h)];rows=[]
    for i in range(count):
        case_index,h,start,end,retired,value,golden,passed=words[3+8*i:3+8*i+8]
        if(case_index,h)!=expected[i]or passed!=1:raise ValueError('Wrong buffered case/hart/order/check status')
        case=corpus['cases'][case_index]
        row={k:case[k]for k in ('case_id','parent_case_id','trial_id','suite')}
        row.update(hart=h,region='kernel',start_cycle=start,end_cycle=end,instret_delta=retired,checksum=value,expected_checksum=golden,**{'pass':True})
        rows.append(row)
    rows_check(rows,corpus)
    for pc in words[-3:]:
        if pc&1 or not any(base<=pc<base+fs and flags&1 for base,pos,fs,ms,flags in elf.loads):raise ValueError('Final architectural PC outside actual executable ELF bytes')
    return rows,words[-3:]


def join_features(path,rows,corpus,elf,rom,identity):
    raw=path.read_bytes();cut=raw.rfind(b'\n')+1;prefix=[json.loads(x)for x in raw[:cut].splitlines()]
    code=Instructions(elf,rom);index={};last={}
    for p in prefix:
        for key,limit in [('hart',3),('sequence',1<<64),('value',1<<64),('read_cycle',1<<64),('pc',1<<64),('raw',1<<32),('csr',1<<12),('destination',32)]:
            if type(p.get(key))is not int or not 0<=p[key]<limit:raise ValueError('Invalid typed actual prefix field: '+key)
        if(p.get('schema')!='iris.empirical.prefix.v1'or p.get('endpoint')!='get_csr_before_current_instruction_retirement'
                or p.get('calibration_identity')!=identity or p['sequence']<=last.get(p['hart'],-1)):
            raise ValueError('Wrong prefix schema/identity/order')
        last[p['hart']]=p['sequence'];rawinsn=p['raw'];rd=(rawinsn>>7)&31;csr=rawinsn>>20
        if(code.read(p['pc'])!=rawinsn or rawinsn&127!=0x73 or (rawinsn>>12)&7 not in (1,2,3,5,6,7)
                or csr not in (0xb00,0xc00)or p['csr']!=csr or p['destination']!=rd
                or type(p.get('result_discarded'))is not bool or p['result_discarded']!=(rd==0)):
            raise ValueError('Counter prefix does not match actual returning/discarded cycle CSR instruction')
        if p['result_discarded']:continue
        key=p['hart'],p['value']
        if key in index:raise ValueError('Ambiguous real CSR observation')
        index[key]=p
    cases={c['case_id']:c for c in corpus['cases']};joined=[]
    for row in rows:
        a=index[(row['hart'],row['start_cycle'])];b=index[(row['hart'],row['end_cycle'])]
        if a['sequence']>=b['sequence']or a['read_cycle']>=b['read_cycle']:raise ValueError('Actual ROI endpoints unordered')
        case=cases[row['case_id']]
        features=difference(a['features'],b['features']);memory=difference(a.get('memory',{}),b.get('memory',{}))
        joined.append({**row,'native_cycles':row['end_cycle']-row['start_cycle'],'global_model_cycles':b['read_cycle']-a['read_cycle'],
            'begin_pc':a['pc'],'end_pc':b['pc'],'start_sequence':a['sequence'],'end_sequence':b['sequence'],
            'semantic_parent_case_id':case['semantic_parent_case_id'],'target_region_for_reporting':case['target_region'],
            'mask_for_reporting':case['mask'],'stride_for_reporting':case['stride'],'spread_for_reporting':case['spread'],
            'n_for_reporting':case['n'],'kind_for_reporting':case['kind'],'features':features,'memory':memory,
            'resource_occupancy':difference(a.get('resource_occupancy_prefix',{}),b.get('resource_occupancy_prefix',{})),
            'hardware_reference_cycles':None,'actual_reference_timings_consumed':False})
    return joined,{'actual_CSR_ELF_boundary_joins':2*len(rows),'complete_prefix_records':len(prefix),
        'unterminated_tail_bytes_preserved':len(raw)-cut,'required_boundaries_all_complete':True}


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('build','native','uart','fixture','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--timeout',type=float,default=300);a=p.parse_args();build=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    corpus,layout,proof=audit(build);elf=build/'memory-routes.elf';e=Elf(elf);objects=layout['objects'];address=lambda n:objects[n]['address']
    identity=[x.split()[2]for x in a.fixture.read_text().splitlines()if x.startswith('empirical_profile ')]
    if len(identity)!=1:raise ValueError('Unique exact fitted fixture identity required')
    command=['rs 0',f'while mem {address("buffered_measurements_done"):x} ffffffffffffffff']
    fields=('buffered_measurements_done','buffered_record_count','buffered_case_count')
    command += [f'mem {address(n):x}'for n in fields]
    base=address('buffered_records');command +=[f'mem {n:x}'for n in range(base,base+objects['buffered_records']['size'],8)]
    command +=[f'mem {address(n):x}'for n in fields]+['pc 0','pc 1','pc 2','quit']
    (out/'commands.txt').write_text('\n'.join(command)+'\n')
    from spike.run_functional import COMPUTE,DMA
    rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb'
    argv=[str(a.native.resolve()),'-d','--debug-cmd='+str(out/'commands.txt'),'--iris-timing-fixture='+str(a.fixture.resolve()),
        '--extlib='+str(a.uart.resolve()),'--iris-vme','--isa='+DMA,'--hart-isa=0:'+COMPUTE,'--hart-isa=1:'+COMPUTE,'--hart-isa=2:'+DMA,
        '-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000','--device=sifive_uart,0x10020000',
        '--iris-bootrom='+str(rom),'--dtb='+str(dtb),str(elf)]
    (out/'argv.json').write_text(json.dumps(argv,indent=2)+'\n')
    paths=[Path(__file__).resolve(),ROOT/'timing/memory_routes_current_audit_v2.py',ROOT/'timing/empirical_live_features_v4.py',
        ROOT/'iris_model/guest_regions.py',ROOT/'spike/run_functional.py',a.native.resolve(),a.uart.resolve(),a.fixture.resolve(),rom,dtb,
        *[build/n for n in ('ready.json','build.json','corpus.json','split.json','readback-layout.json','memory-routes.elf')],out/'commands.txt',out/'argv.json']
    inputs={str(f):sha(f)for f in paths};report={'schema':'iris.memory_routes_current_native_readback.v1','status':'running',
        'argv':argv,'input_sha256':inputs,'normal_guest_exit_verified':False,'intentional_post_ROI_debugger_stop':True,
        'hardware_contacted':False,'global_heldout_timings_consumed':False,'memory_reference_timings_consumed':False,
        'parameter_fit_performed':False,'parameters_changed':False,'full_2pct_certified':False}
    (out/'run.json').write_text(json.dumps(report,indent=2)+'\n');started=time.monotonic()
    with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
        child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True,
            env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(out/'features.jsonl')))
        report['owned_child_pid']=child.pid
        try:report['debugger_exit_status']=child.wait(timeout=a.timeout);report['timed_out']=False
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            report.update(debugger_exit_status=child.returncode,timed_out=True)
    report['host_seconds']=time.monotonic()-started
    try:
        if report['debugger_exit_status']!=0 or report['timed_out']:raise ValueError('No complete quiescent post-ROI readback')
        rows,pcs=decode((out/'stderr').read_text(),corpus,layout,e)
        features,joins=join_features(out/'features.jsonl',rows,corpus,elf,rom,identity[0])
        if any(sha(path)!=digest for path,digest in inputs.items()):raise ValueError('Execution input changed')
        for name,values in [('regions.jsonl',rows),('region-features.jsonl',features)]:
            (out/name).write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in values))
        report.update({'pass':True,'status':'completed_all2592_regions_with_intentional_debugger_stop','regions':2592,
            'all_independent_goldens_passed':True,'final_architectural_PCs':pcs,'source_and_compiled_table_audit':proof,**joins})
    except (ValueError,KeyError,TypeError,UnicodeError)as error:report.update({'pass':False,'status':'failed','error':str(error)})
    report['output_sha256']={str(f):sha(f)for f in out.iterdir()if f.name in ('stdout','stderr','features.jsonl','regions.jsonl','region-features.jsonl')}
    (out/'run.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in ('status','pass','host_seconds','regions','error')}))
    if not report['pass']:raise SystemExit(1)


if __name__=='__main__':main()
