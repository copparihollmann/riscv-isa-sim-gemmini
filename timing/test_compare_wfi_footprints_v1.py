#!/usr/bin/env python3
"""Synthetic math/refusal tests; these are not FPGA timing evidence."""
import copy
import importlib.util
import json
from pathlib import Path
from compare_wfi_footprints_v1 import ROOT,bracket,compare_rows,groups,metrics,sha

def main():
    run=ROOT/'build/memory-footprints-WFI-groups-hybrid7bd5-selected-v1'
    corpus=json.loads((ROOT/'build/memory-footprints-mtime-wfi-groups-fit-v8/corpus.json').read_text())
    rows=[json.loads(l[len('IRIS_REGION '):])for l in(run/'stdout').read_text().splitlines()if l.startswith('IRIS_REGION ')]
    joins=json.loads((run/'CSR-endpoint-qualification.json').read_text())['joins']
    same=compare_rows(rows,rows,corpus,joins);s=metrics(same)
    assert s['regions']==s['within_2percent']==360 and s['max_absolute_error_percent']==0
    # A single known exact ratio proves sign and absolute-error semantics.
    m=copy.deepcopy(rows);h=copy.deepcopy(rows)
    for sw,hw in zip(m,h):hw['start_cycle']=100;hw['end_cycle']=200;sw['start_cycle']=300;sw['end_cycle']=410
    changed=compare_rows(m,h,corpus,joins);assert all(abs(r['signed_error_percent']-10)<1e-12 for r in changed)
    assert metrics(changed)['within_2percent']==0
    assert sum(r['regions']for r in groups(same,['hart','footprint_bytes','mask','pass_index']))==360
    b=bracket({'mtime_before':9,'mtime_after':9});assert b['enclosing_window_lower_source_core_cycles']==0 and b['enclosing_window_upper_source_core_cycles']==1000
    b=bracket({'mtime_before':9,'mtime_after':12});assert b['enclosing_window_lower_source_core_cycles']==2000 and b['enclosing_window_upper_source_core_cycles']==4000
    refused=[]
    def reject(name,action):
        try:action()
        except(ValueError,KeyError,TypeError):refused.append(name);return
        raise ValueError('Synthetic corruption admitted: '+name)
    reject('truncated-row',lambda:compare_rows(rows,rows[:-1],corpus,joins))
    for field,value in [('hart',17),('checksum',0),('pass',1),('requested_bytes',True),('end_cycle',rows[0]['start_cycle'])]:
        bad=copy.deepcopy(rows);bad[0][field]=value
        reject(field,lambda:compare_rows(rows,bad,corpus,joins))
    bad=copy.deepcopy(rows);bad[1]=bad[0]
    reject('duplicate-row',lambda:compare_rows(bad,bad,corpus,joins))
    bad=copy.deepcopy(joins);bad[0]['case_id']='other'
    reject('wrong-model-CSR-owner',lambda:compare_rows(rows,rows,corpus,bad))
    reject('CLINT-bool',lambda:bracket({'mtime_before':True,'mtime_after':2}))
    reject('CLINT-reversed',lambda:bracket({'mtime_before':3,'mtime_after':2}))
    # Interrupt-path instruction-count differences remain in the comparison.
    bad=copy.deepcopy(rows);bad[0]['instret_delta']+=1
    retained=compare_rows(rows,bad,corpus,joins);assert len(retained)==360 and metrics(retained)['instret_mismatches']==1
    out=ROOT/'build/WFI-footprint-comparison-tests-v1';out.mkdir(exist_ok=False)
    paths=[Path(__file__).resolve(),Path(__file__).with_name('compare_wfi_footprints_v1.py'),run/'stdout',run/'CSR-endpoint-qualification.json']
    report={'schema':'iris.WFI_footprint_comparison_synthetic_tests.v1','pass':True,'synthetic_math_only':True,'hardware_evidence':False,'rows_checked':360,'corruption_refusals':refused,'positive_controls':['identical-zero-errors','known-positive10percent','all-crossgroups-retained','zero-tick-uncertainty','three-tick-uncertainty','instret-mismatch-retained'],'input_sha256':{str(p):sha(p)for p in paths}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'refusals':len(refused),'sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
