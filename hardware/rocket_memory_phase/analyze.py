#!/usr/bin/env python3
"""Check actual WB retirement and later cache-result writes without fitting."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[2]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def audit_rows(rows):
    pending={};matches=[];retired_loads=0;rf_writes=0;counter_steps=0;last_edge=0
    for row in rows:
        edge=row['edge'];before=row['before'];after=row['after']
        if edge<=last_edge:raise ValueError('nonmonotonic actual source edge')
        last_edge=edge
        if before['ll_wen']or(before['wb_valid']and before['wb_wxd']):
            rd=before['rf_waddr']
            if rd and after['rf'][rd]!=before['rf_wdata']:raise ValueError('actual RF edge write does not match preedge source data')
            rf_writes+=bool(rd)
        if before['wb_valid']and before['wb_mem']and(before['wb_inst']&127)==3:
            retired_loads+=1;rd=(before['wb_inst']>>7)&31
            delta=(after['instret']-before['instret'])&((1<<64)-1);expected=0 if before['inhibit']&4 else before['retire']
            if delta!=expected:raise ValueError('retired memory edge/counter transition differs')
            counter_steps+=1
            if before['retire']and not before['core_dresp_valid']:
                if not rd or rd in pending:raise ValueError('ambiguous load destination before late value')
                pending[rd]=dict(load_pc=before['wb_pc'],load_raw=before['wb_inst'],rd=rd,WB_edge=edge,instret_before=before['instret'],instret_after=after['instret'],WB_RF_value=after['rf'][rd],data_response_at_WB=False)
        if before['ll_wen']and before['cache_resp_valid']and before['cache_replay']and before['cache_has_data']and before['cache_tag']&3==1 and not before['cache_tag']&4:
            rd=before['cache_tag']>>3
            if rd not in pending:raise ValueError('late scalar result has no matching retired load')
            witness=pending.pop(rd)
            if before['rf_waddr']!=rd or edge<=witness['WB_edge']or after['rf'][rd]!=before['rf_wdata']:raise ValueError('late result RF destination/data/phase differs')
            witness.update(result_ready_edge=edge,WB_to_result_edges=edge-witness['WB_edge'],result_value=after['rf'][rd],intervening_retired=(before['instret']-witness['instret_after'])&((1<<64)-1));matches.append(witness)
    if pending or len(matches)<8 or retired_loads<500:raise ValueError('late-result source corpus incomplete')
    if counter_steps!=retired_loads:raise ValueError('counter check coverage differs')
    return matches,retired_loads,counter_steps,rf_writes

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,default=ROOT/'build/rocket-memory-phase-reference-v1');p.add_argument('--output',type=Path,required=True);a=p.parse_args();run=a.run.resolve();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    receipt=json.loads((run/'run.json').read_text());build=ROOT/'build/rocket-memory-phase-observer-v1/build.json';br=json.loads(build.read_text());trace=run/'memory-phase.jsonl.gz'
    if receipt['status']!='passed_252_architectural_checks'or receipt['observer_build_sha256']!=sha(build)or receipt['trace_sha256']!=sha(trace):raise ValueError('actual whole-CPU run identity/status differs')
    for path,digest in br['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('actual observer source/library input changed: '+path)
    original=ROOT/'build/memory-fabric-rtl-v1/coherent.signature'
    if sha(original)!=sha(run/'coherent.signature'):raise ValueError('read-only observer changed coherent architectural signature')
    rows=[json.loads(s)for s in gzip.open(trace,'rt')]
    matches,retired_loads,counter_steps,rf_writes=audit_rows(rows);rejected=[]
    load_index=next(i for i,r in enumerate(rows)if r['before']['wb_valid']and r['before']['wb_mem']and(r['before']['wb_inst']&127)==3)
    late_index=next(i for i,r in enumerate(rows)if r['before']['ll_wen']and r['before']['cache_resp_valid']and r['before']['cache_replay']and r['before']['cache_tag']&3==1 and not r['before']['cache_tag']&4)
    for kind in ['edge_order','counter_increment','late_RF_data','late_source_tag','missing_late_replay']:
        altered=copy.deepcopy(rows)
        if kind=='edge_order':altered[1]['edge']=altered[0]['edge']
        elif kind=='counter_increment':altered[load_index]['after']['instret']^=1
        elif kind=='late_RF_data':
            rd=altered[late_index]['before']['rf_waddr'];altered[late_index]['after']['rf'][rd]^=1
        elif kind=='late_source_tag':altered[late_index]['before']['cache_tag']^=1
        else:altered[late_index]['before']['cache_replay']=0
        try:audit_rows(altered)
        except ValueError:rejected.append(kind)
        else:raise ValueError('adversarial phase corruption accepted: '+kind)
    paths=[Path(__file__).resolve(),ROOT/'hardware/rocket_memory_phase/build.py',ROOT/'hardware/rocket_memory_phase/run.py',run/'run.json',trace,run/'coherent.signature',run/'all-harts-coherent.elf',build,original]
    report=dict(schema='iris.rocket.memory_WB_late_result_proof.v1',status='passed_actual_WB_retirement_separate_from_cache_result',source_FIR_sha256=receipt['source_FIR_sha256'],whole_CPU_architectural_checks=252,physical_sample_rows=len(rows),retired_loads=retired_loads,checked_memory_counter_edges=counter_steps,checked_RF_edge_writes=rf_writes,adversarial_corruptions_rejected=rejected,late_load_witnesses=matches,coherent_signature_byte_identical=True,input_sha256={str(p):sha(p)for p in paths},observer_build_sha256=sha(build),source_wide_counter_low_bits=6,
        source_policy=['RocketCore787: load without WB data sets scalar scoreboard.','RocketCore846–855/884: WB retires before late result; a late replay response selects LL RF write.','RocketCore1030–1038: scalar scoreboard clears on actual LL write, with same-edge bypass.'],
        implications=['Native modeling must distinguish WB retirement/PC/minstret from result-ready/scoreboard.','Delaying architectural retirement until cache response is not source-equivalent even when the immediate next instruction depends on the load.','Reported WB-to-result intervals are observations of this exact source reference, not fitted/default memory latencies.'],
        RTL_logic_modified=False,source_state_or_ready_injected=False,full_internal_knownness_certified=False,calibration=False,held_out_2pct=False,hardware_contacted=False,loaded_image_association_verified=False)
    archive=out/'evidence';archive.mkdir()
    for path in paths:
        if path.stat().st_size<10485760:shutil.copy2(path,archive/(sha(path)+'-'+path.name))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],retired_loads=retired_loads,late_results=len(matches),report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()
