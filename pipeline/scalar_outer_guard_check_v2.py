#!/usr/bin/env python3
import json
from pathlib import Path
from scalar_l2_hit_guard_check import ROOT,sha,vector_nodes
def main():
    witness=[];paths=[Path(__file__).resolve(),ROOT/'pipeline/scalar_outer_response_service_v2.hpp',ROOT/'pipeline/scalar_outer_guard_guest_v2.c']
    for h in range(3):
        ds={mode:ROOT/f'build/scalar-outer-guard-v2-{h}-{mode}'for mode in('OFF','beta100')};values={};sigs={}
        for mode,d in ds.items():
            r=json.loads((d/'run.json').read_text())
            if r['pass']is not True or r['exit_status']!=0 or r['timed_out']is not False or(d/'stderr').read_bytes():raise ValueError('Actual normal clean guard exit required')
            rows=[list(map(int,l.split()[1:]))for l in(d/'stdout').read_text().splitlines()if l.startswith('IRIS_SCALAR_OUTER_GUARD ')]
            if len(rows)!=1 or rows[0][0]!=h or rows[0][-1]!=0:raise ValueError('Numeric512-load/vector guard failed')
            values[mode]=rows[0];nodes=vector_nodes(d/'native-summary.json')
            if len(nodes)!=4 or not any(n['resource']=='empirical.outer'for n in nodes):raise ValueError('Cold vector OUTER witness required')
            sigs[mode]=sorted((n['hart'],n['pc'],n['name'],n['resource'],n['end']-n['start'],n['bytes'])for n in nodes)
            paths.extend(d/n for n in('run.json','stdout','stderr','native-summary.json','features.jsonl'))
        off,on=values['OFF'],values['beta100'];difference=(on[2]-on[1])-(off[2]-off[1])
        if difference!=51200 or sigs['OFF']!=sigs['beta100']:raise ValueError('Beta scalar sensitivity / vector service changed')
        prefix=[json.loads(l)for l in(ds['beta100']/'features.jsonl').read_text().splitlines()];ends=[]
        for value in(on[1],on[2]):
            rows=[r for r in prefix if r['hart']==h and r['value']==value and r['csr']==0xb00]
            if len(rows)!=1:raise ValueError('Actual unique program CSR endpoints required')
            ends.append(rows[0]['memory']['SCALAR_OUTER_SERVICE'])
        probes=ends[1]['L2_miss_lines']-ends[0]['L2_miss_lines'];charge=ends[1]['charged_core_cycles']-ends[0]['charged_core_cycles']
        if probes!=512 or charge!=51200:raise ValueError('Actual admitted cold-load cost basis mismatch')
        witness.append({'hart':h,'OFF_scalar_cycles':off[2]-off[1],'ON_scalar_cycles':on[2]-on[1],'added_program_cycles':difference,'actual_admitted_outer_lines':probes,'actual_charged_core_cycles':charge,'vector_service_signatures':sigs['beta100']})
    parent=ROOT/'build/scalar-outer-guard-v2-0-parent-e8';child=ROOT/'build/scalar-outer-guard-v2-0-OFF'
    for name in('stdout','stderr','native-summary.json','features.jsonl'):
        if sha(parent/name)!=sha(child/name):raise ValueError('V2 defaultOFF vs e8 whole-byte parity failed '+name)
        paths.extend([parent/name,child/name])
    out=ROOT/'build/scalar-outer-actual-guard-proof-v2';out.mkdir(exist_ok=False)
    report={'schema':'iris.scalar_outer_response_actual_guard.v2','pass':True,'witness':witness,'V2_OFF_vs_e8_whole_graph_prefix_stdout_stderr_byteidentical':True,'vector_transaction_duration_resource_bytes_unchanged':True,'scope':'Only synthetic beta100, ordinary scalar DRAM512 coldloads per independently activehart. Shared OUTER issue interval and explicit Icache/formulas unchanged; no latency fit or physical cache assertion.','hardware_contacted':False,'input_sha256':{str(p):sha(p)for p in paths}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(out/'report.json'),'program_cycle_deltas':[r['added_program_cycles']for r in witness]}))
if __name__=='__main__':main()
