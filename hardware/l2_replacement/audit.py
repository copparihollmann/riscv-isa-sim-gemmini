#!/usr/bin/env python3
"""Audit associated L2 replacement/clock expressions; no cache policy changes."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SV=Path('/scratch/eygao/iris-cy/sims/firesim/deploy/results-build/2026-11-03--03-10-49-corigine_mimicturbo_gt_firesim_iris_tethered_bringup_nocflush/cl_corigine_mimicturbo_gt-firesim-FireSim-IrisFiresimNOCflushCombinedConfig-BaseCorigineMimicTurboGTConfig/design/FireSim-generated.sv')
EXPECTED='c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def compact(s):return re.sub(r'\s+',' ',re.sub(r'//[^\n]*','',s))
GUARDS={
    'Directory':[
        'wire [9:0] victimLFSR = _victimLFSR_T[9:0];',
        "wire [3:0] victimLTE = {10'h300 <= victimLFSR,10'h200 <= victimLFSR,10'h100 <= victimLFSR,1'h1};",
        'wire [3:0] victimWayOH = victimSimp[3:0] & _victimWayOH_T_2;',
        'wire [1:0] _io_result_bits_way_T_5 = _io_result_bits_hit_T ? write_q_io_deq_bits_way : victimWay;',
        'assign io_result_bits_way = hit ? _io_result_bits_way_T_3 : _io_result_bits_way_T_5;',
        'assign victimLFSR_prng_io_increment = io_read_valid;',
        'assign victimLFSR_prng_clock = clock;',
    ],
    'MaxPeriodFibonacciLFSR':[
        'wire _T_2 = state_10 ^ state_12 ^ state_13 ^ state_15;',
        'wire _GEN_0 = io_increment ? _T_2 : state_0;',
        'state_0 <= reset | _GEN_0;',
        "state_15 <= 1'h0;",'state_15 <= state_14;',
        'always @(posedge clock) begin',
    ],
    'InclusiveCacheBankScheduler':['assign directory_clock = clock;'],
    'InclusiveCache':[f'assign inclusive_cache_bank_sched{x}_clock = clock;'for x in ('','_1','_2','_3')],
    'CoherenceManagerWrapper':['assign l2_clock = auto_coh_clock_groups_in_member_coh_0_clock;'],
    'DigitalTop':['assign coh_wrapper_auto_coh_clock_groups_in_member_coh_0_clock = clockGroupCombiner_auto_clock_group_combiner_out_member_allClocks_sbus_1_clock;'],
}
def guard(name,text):
    t=compact(text)
    for literal in GUARDS[name]:
        if literal not in t:raise ValueError('Changed associated expression '+name+':'+literal)
def main(output):
    if sha(SV)!=EXPECTED:raise ValueError('Associated source changed')
    mods={m[1]:m[0]+'\n'for m in re.finditer(r'^module\s+(\w+)[\s\S]*?^endmodule',SV.read_text(),re.M)}
    output.mkdir(exist_ok=False,parents=True);(output/'source').mkdir()
    for name in GUARDS:
        guard(name,mods[name]);(output/'source'/(name+'.sv')).write_text(mods[name])
    d=compact(mods['Directory'])
    if len(re.findall(r'InclusiveCacheBankScheduler\s+inclusive_cache_bank_sched(?:_[123])?\s*\(',mods['InclusiveCache']))!=4:raise ValueError('Configured bank count changed')
    if 'input [8:0] io_read_bits_set'not in d or 'output [1:0] io_result_bits_way'not in d:raise ValueError('Configured directory geometry changed')
    # Directly evaluate the emitted threshold/one-hot logic for every16-bit state.
    truth=[]
    for state in range(1<<16):
        value=state&1023;lte=1|((value>=256)<<1)|((value>=512)<<2)|((value>=768)<<3)
        simp=((lte>>1)<<1)|1;oh=(simp&15)&(~(simp>>1)&15)
        if oh==0 or oh&(oh-1):raise ValueError('Victim one-hot invariant')
        way=oh.bit_length()-1
        if way!=(state>>8)&3:raise ValueError('Threshold selector interpretation mismatch')
        if state<1024:truth.append(way)
    mutations=[]
    for name,old,new in [('Directory','io_increment = io_read_valid','io_increment = io_read_valid & miss'),('Directory',"10'h300 <= victimLFSR","10'h200 <= victimLFSR"),('Directory',' : victimWay;', ' : invalidWay;'),('InclusiveCacheBankScheduler','directory_clock = clock','directory_clock = core_gated_clock')]:
        text=compact(mods[name])
        if old not in text:raise ValueError('Mutation precondition')
        try:guard(name,text.replace(old,new,1))
        except ValueError:mutations.append({'module':name,'changed_expression':old,'rejected':True})
        else:raise ValueError('Source-changing mutation admitted')
    # Conditional mechanism witness, not a complete directory simulation: four
    # isolated tag-miss lookups of one empty set, no intervening reads/bypass.
    state=1;slots=[None]*4;sequence=[]
    for tag in range(4):
        feedback=((state>>10)^(state>>12)^(state>>13)^(state>>15))&1
        state=((state<<1)&65535)|feedback
        way=(state>>8)&3;sequence.append({'tag':tag,'post_read_PRNG':state,'victim_way':way,'invalid_ways_before':[i for i,x in enumerate(slots)if x is None]});slots[way]=tag
    if len([x for x in slots if x is not None])!=1:raise ValueError('Conditional invalid-preference counterexample failed')
    source=Path('/scratch/eygao/iris-cy/generators/rocket-chip-inclusive-cache/design/craft/inclusivecache/src')
    report={'schema':'iris.associated_L2_replacement_clock_audit.v1','pass':True,'associated_generated_SV_sha256':EXPECTED,'source_expressions':GUARDS,'configured_banks':4,'sets_per_bank':512,'ways_per_set':4,'source_PRNG_reset':1,'PRNG_bits':16,'victim_selector':'state[9:8], derived from low10-bit quartiles','advance_condition':'Every physical Directory.io_read_valid, including hits; not only allocations/misses','miss_way':'PRNG victim except actual same-set write/tag bypass; no invalid-first search','clock_domain':'coherence input clock from allClocks_sbus_1; direct clock through InclusiveCache->four bank schedulers->Directory->PRNG','selector_states_checked':65536,'source_changing_mutations_rejected':mutations,'conditional_no_invalid_preference_witness':sequence,'conditional_final_resident_tags':slots,'limitations':['Conditional four-read witness is a source-expression evaluation, not complete RTL directory/scheduler execution.','Architectural requests do not uniquely determine physical directory reads: bypass/reload/nesting/directory arbitration and I/D traffic matter.','Current empirical L2 uses an approximate LRU history; no policy/native/parameters were changed by this audit.','No image-loaded association attestation, physical miss measurement, or timing-fit qualification.','No new FPGA or protected held-out data accessed.'],'hardware_contacted':False,'native_or_parameters_changed':False,'input_sha256':{str(p):sha(p)for p in [Path(__file__).resolve(),SV,source/'Directory.scala',source/'Scheduler.scala',source/'Parameters.scala',ROOT/'hardware/memory-paths.json']}}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(output/'report.json'))
if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);main(p.parse_args().output.resolve())
