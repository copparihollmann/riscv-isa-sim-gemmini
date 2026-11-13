#!/usr/bin/env python3
"""Bounded-memory check of actual scalar sensitivity and vector service parity."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def vector_nodes(path):
    marker=b'"name":"empirical.cache.memory.vector.';nodes={};tail=b'';position=0
    decoder=json.JSONDecoder()
    with path.open('rb')as f:
        while True:
            chunk=f.read(8<<20)
            if not chunk:break
            buf=tail+chunk;cursor=0
            while True:
                pos=buf.find(marker,cursor)
                if pos<0:break
                begin=buf.rfind(b'{"id":',0,pos)
                if begin<0:raise ValueError('Vector event prefix missing')
                try:node,_=decoder.raw_decode(buf[begin:begin+16384].decode('utf-8'))
                except(json.JSONDecodeError,UnicodeDecodeError):break
                nodes[node['id']]=node;cursor=pos+len(marker)
            tail=buf[-32768:];position+=len(chunk)
    return list(nodes.values())
def records(path):
    result={}
    for line in path.read_text().splitlines():
        if line.startswith('IRIS_SCALAR_L2_GUARD '):
            values=list(map(int,line.split()[1:]));h,*v=values
            if h in result or v[-1]!=0:raise ValueError('Numeric witness failed / duplicate')
            result[h]=v
    if set(result)!={0,1,2}:raise ValueError('All3 actual harts required')
    return result
def main():
    dirs={k:ROOT/'build'/('scalar-L2hit-guard-'+k+'-v1')for k in('parent','OFF','ON')}
    rs={k:records(d/'stdout')for k,d in dirs.items()};receipts={k:json.loads((d/'run.json').read_text())for k,d in dirs.items()}
    if not all(r['pass']is True and r['exit_status']==0 and r['timed_out']is False for r in receipts.values()):raise ValueError('Normal actual guest exits required')
    for name in('stdout','stderr','native-summary.json','features.jsonl'):
        if sha(dirs['parent']/name)!=sha(dirs['OFF']/name):raise ValueError('OFF whole-byte parity failed '+name)
    sensitivity=[]
    for h in range(3):
        off,on=rs['OFF'][h],rs['ON'][h];delta=(on[1]-on[0])-(off[1]-off[0])
        if delta!=512*100:raise ValueError('Scalar actual512-load sensitivity mismatch')
        sensitivity.append({'hart':h,'OFF_scalar_cycles':off[1]-off[0],'ON_scalar_cycles':on[1]-on[0],'added_cycles':delta})
    signatures={}
    for name,d in dirs.items():
        nodes=vector_nodes(d/'native-summary.json')
        if len(nodes)!=12:raise ValueError('Actual12vector transactions required')
        signatures[name]=sorted((n['hart'],n['pc'],n['name'],n['resource'],n['end']-n['start'],n['bytes'])for n in nodes)
        if not any(n['resource']=='empirical.outer'for n in nodes):raise ValueError('Cold vector OUTER witness missing')
    if signatures['parent']!=signatures['OFF']or signatures['OFF']!=signatures['ON']:raise ValueError('Vector transaction service changed')
    out=ROOT/'build/scalar-L2hit-actual-guard-proof-v1';out.mkdir(exist_ok=False)
    inputs=[Path(__file__).resolve(),ROOT/'pipeline/scalar_l2_hit_service.hpp',ROOT/'pipeline/scalar_l2_hit_guard_guest.c',ROOT/'build/scalar-L2hit-guard-guest-v1/build.json',*[p for d in dirs.values()for p in[d/'run.json',d/'stdout',d/'stderr',d/'features.jsonl',d/'native-summary.json']]]
    report={'schema':'iris.scalar_L2_hit_actual_guard_proof.v1','pass':True,'numeric_harts':[0,1,2],
        'OFF_parent_whole_graph_prefix_stdout_stderr_byteidentical':True,'scalar_sensitivity':sensitivity,
        'vector_transactions_service_parity':signatures['ON'],'cold_vector_outer_included':True,
        'scope':'Per-vector-transaction duration/resource/bytes unchanged, including coldouter. Absolute issue timestamps and aggregate concurrent region durations may change with corrected scalar progress.',
        'full_graph_analysis_streamed':True,'synthetic_coefficients_not_calibration':True,
        'hardware_contacted':False,'timing_certified':False,'input_sha256':{str(p):sha(p)for p in inputs}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(out/'report.json'),'scalar_sensitivity':sensitivity}))
if __name__=='__main__':main()
