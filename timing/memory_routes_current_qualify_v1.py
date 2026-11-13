#!/usr/bin/env python3
"""Qualify preserved exact readback with real-data corruption controls, no fitting."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

from memory_routes_current_audit_v2 import audit,Elf
from memory_routes_current_replay_v1 import decode,join_features

ROOT=Path(__file__).resolve().parents[1]
FAMILY=re.compile(r'(scalar\.(integer|branch|csr_system|fence|fp(16|32|64|128)|fadd\.fp(16|32|64))|vector\.config|rvv\.(integer|fp(8|16|32|64)|fadd\.(bf16|fp(8|16|32|64)))|vme\.(int8|fp8|zero|row_move|discard)|memory\.(DRAM|LOCAL_TCM|REMOTE_TCM|SCRATCHPAD|UNCACHED|MMIO)\.(load|store|atomic|lr|sc)|memory\.vector\.(load|store)(\.address_pattern_uncalibrated)?)')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_prefix(records):
    for row in records:
        if type(row.get('retired'))is not int or row['retired']<0:raise ValueError('Exact unsigned retired prefix required')
        if not isinstance(row.get('features'),dict):raise ValueError('Runtime feature map required')
        for family,metrics in row['features'].items():
            if not FAMILY.fullmatch(family)or not isinstance(metrics,dict):raise ValueError('Unknown runtime family')
            if not {'instructions','work','bytes','macs'}<=set(metrics)or not set(metrics)<={'instructions','work','bytes','macs','dlen_beats','atl_beats'}:
                raise ValueError('Unknown feature metric')
            if any(type(v)is not int or v<0 for v in metrics.values()):raise ValueError('Exact unsigned feature metrics required')
        for key in ('memory','resource_occupancy_prefix'):
            if not isinstance(row.get(key),dict):raise ValueError('Counter map required: '+key)
            for metrics in row[key].values():
                if not isinstance(metrics,dict)or any(type(v)is not int or v<0 for v in metrics.values()):raise ValueError('Unsigned nested prefix counters required')


def main(a):
    source=a.run.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    run=json.loads((source/'run.json').read_text());corpus,layout,proof=audit(a.build);elf=Elf(a.build/'memory-routes.elf')
    if run.get('pass')is not True or run.get('debugger_exit_status')!=0 or run.get('timed_out')is not False or run.get('normal_guest_exit_verified')is not False:
        raise ValueError('Complete intentional debugger-stop run required')
    for name,expected in {**run['input_sha256'],**run['output_sha256']}.items():
        if sha(name)!=expected:raise ValueError('Preserved replay input/output changed')
    rawtext=(source/'stderr').read_text();rows,pcs=decode(rawtext,corpus,layout,elf)
    raw=(source/'features.jsonl').read_bytes();cut=raw.rfind(b'\n')+1;records=[json.loads(x)for x in raw[:cut].splitlines()];check_prefix(records)
    fixture=Path(next(x.split('=',1)[1]for x in run['argv']if x.startswith('--iris-timing-fixture=')))
    identity=next(x.split()[2]for x in fixture.read_text().splitlines()if x.startswith('empirical_profile '));rom=ROOT/'board/evidence/bootrom.rv64.img'
    joined,joins=join_features(source/'features.jsonl',rows,corpus,a.build/'memory-routes.elf',rom,identity)
    controls=[];words=[int(x,16)for x in rawtext.splitlines()[1:]]
    def stream(values):return ':\n'+''.join(f'0x{v:016x}\n'for v in values)
    mutations={
        'missing_final_word':lambda x:x[:-1], 'extra_word':lambda x:x+[0],
        'header_incomplete':lambda x:x.__setitem__(0,1), 'footer_incomplete':lambda x:x.__setitem__(-6,1),
        'wrong_case_count':lambda x:x.__setitem__(2,1511),'wrong_case_index':lambda x:x.__setitem__(3,1512),
        'wrong_hart':lambda x:x.__setitem__(4,3),'failed_record':lambda x:x.__setitem__(10,0),
        'wrong_value':lambda x:x.__setitem__(8,x[8]^1),'wrong_expected':lambda x:x.__setitem__(9,x[9]^1),
        'reversed_clock':lambda x:x.__setitem__(6,x[5]),'odd_final_PC':lambda x:x.__setitem__(-1,x[-1]|1),
        'nonexec_final_PC':lambda x:x.__setitem__(-1,0),'wrong_order':lambda x:x.__setitem__(slice(3,19),x[11:19]+x[3:11])}
    for name,mutate in mutations.items():
        changed=list(words);result=mutate(changed)
        if result is not None:changed=result
        path=out/(name+'.words');path.write_text(stream(changed))
        try:decode(path.read_text(),corpus,layout,elf)
        except (ValueError,KeyError):pass
        else:raise ValueError('Corruption accepted: '+name)
        controls.append({'name':name,'rejected':True,'sha256':sha(path)})
    first=rows[0];lookup={(p['hart'],p['value']):p for p in records if not p['result_discarded']}
    sample=[lookup[(first['hart'],first[k])]for k in ('start_cycle','end_cycle')]
    counter_mutations={
        'boolean_retired':lambda r:r[0].update(retired=True),
        'unknown_family':lambda r:r[0]['features'].update(benchmark_ID={'instructions':1,'work':1,'bytes':0,'macs':0}),
        'boolean_counter':lambda r:r[0]['features']['scalar.integer'].update(instructions=True),
        'wrong_CSR':lambda r:r[0].update(csr=0xb02),'wrong_raw_instruction':lambda r:r[0].update(raw=r[0]['raw']^16),
        'wrong_fixture_identity':lambda r:r[0].update(calibration_identity='not-selected'),
        'boolean_hart':lambda r:r[0].update(hart=False),'duplicate_sequence':lambda r:r[1].update(sequence=r[0]['sequence'])}
    for name,mutate in counter_mutations.items():
        changed=copy.deepcopy(sample);mutate(changed);path=out/(name+'.jsonl');path.write_text(''.join(json.dumps(x)+'\n'for x in changed))
        try:check_prefix(changed);join_features(path,[first],corpus,a.build/'memory-routes.elf',rom,identity)
        except (ValueError,KeyError):pass
        else:raise ValueError('Prefix corruption accepted: '+name)
        controls.append({'name':name,'rejected':True,'sha256':sha(path)})
    report={'schema':'iris.memory_routes_current_native_qualification.v1','pass':True,'actual_native_regions':2592,
        'all_real_independent_goldens_passed':True,'normal_guest_exit_verified':False,'post_ROI_debugger_stop':True,
        'actual_CSR_ELF_boundary_joins':joins['actual_CSR_ELF_boundary_joins'],'counter_word_controls':len(mutations),
        'prefix_controls':len(counter_mutations),'controls':controls,'parameter_fit_performed':False,'parameters_changed':False,
        'memory_reference_timings_consumed':False,'global_heldout_timings_consumed':False,'hardware_contacted':False,
        'input_sha256':{str(p):sha(p)for p in (Path(__file__).resolve(),ROOT/'timing/memory_routes_current_replay_v1.py',
            ROOT/'timing/memory_routes_current_audit_v2.py',source/'run.json',source/'stderr',source/'features.jsonl',
            a.build/'memory-routes.elf',a.build/'corpus.json',a.build/'readback-layout.json')}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'regions':2592,'controls':len(controls),'report_sha256':sha(out/'report.json')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
