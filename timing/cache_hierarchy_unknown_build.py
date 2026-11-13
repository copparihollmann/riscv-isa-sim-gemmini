#!/usr/bin/env python3
"""Build a minimal saved-cache unknown-control witness and bound real queue writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,default=ROOT/'build/cache-hierarchy-native-v3');p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-unknown-v1');a=p.parse_args();model=a.model.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh unknown-control proof output required')
    out.mkdir();extract=ROOT/'build/cache-hierarchy-source-v1/extraction.json';j=json.loads(extract.read_text())
    (out/'cache_hierarchy_zero_inputs.inc').write_text('\n'.join('m.'+x['name']+'=0;'for x in j['components']['shuttle']['physical_ports']if x['direction']=='input')+'\n')
    code='return {{\n'
    for i in range(4):
        prefix='r.ShuttleDCache__DOT__mshrs__DOT__mshrs_'+str(i)+'__DOT__'
        code+='{'+prefix+'state,'+prefix+'rpq__DOT__enq_ptr_value,'+prefix+'rpq__DOT__deq_ptr_value,bool('+prefix+'rpq__DOT__maybe_full),bool('+prefix+'rpq__DOT__do_enq)},\n'
    code+='}};\n';(out/'cache_hierarchy_queue_views.inc').write_text(code)
    argv=['/usr/bin/g++','-O3','-std=c++20','-I'+str(model/'shuttle'),'-I'+str(TOOL),'-I'+str(out),str(ROOT/'timing/cache_hierarchy_unknown.cpp'),str(model/'sdk/libiris_cache_hierarchy.a'),'-pthread','-latomic','-o',str(out/'witness')]
    with(out/'build.log').open('w')as log:q=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT)
    if q.returncode:raise RuntimeError('unknown-control witness build failed')
    with(out/'witness.json').open('w')as stdout,(out/'stderr').open('w')as stderr:q=subprocess.run([str(out/'witness')],stdout=stdout,stderr=stderr)
    if q.returncode:raise RuntimeError('unknown-control witness run failed')
    data=json.loads((out/'witness.json').read_text());first=None
    for i,a in enumerate(data['seeds']):
        for b in data['seeds'][i+1:]:
            for x,y in zip(a['same_external_store_burst'],b['same_external_store_burst']):
                if x['ready']!=y['ready']:
                    candidate={'seed_a':a['seed'],'seed_b':b['seed'],'cycle':x['cycle'],'a':x,'b':y}
                    if first is None or candidate['cycle']<first['cycle']:first=candidate
                    break
    if first is None:raise ValueError('alternate reset choices did not expose readiness divergence')
    if first['a']['replay_valid']or first['b']['replay_valid']or first['a']['head_defined_by_accepted_write']or first['b']['head_defined_by_accepted_write']:raise ValueError('witness did not isolate invalid unwritten head')
    for row in data['accepted_queue_write_bound']:
        if row['before']['head_defined_by_accepted_write']or not row['after_real_enqueues']['head_defined_by_accepted_write']or row['after_real_dequeue']['head_defined_by_accepted_write']:raise ValueError('queue-slot knownness bound failed')
    sources=[Path(__file__),ROOT/'timing/cache_hierarchy_unknown.cpp',out/'cache_hierarchy_zero_inputs.inc',out/'cache_hierarchy_queue_views.inc',model/'build.json',model/'sdk/libiris_cache_hierarchy.a',extract]
    result={'schema':'iris.shuttle_undefined_timing_bound.v1','status':'proved_source_definedness_gap','argv':argv,'input_sha256':{str(x):sha(x)for x in sources},'binary_sha256':sha(out/'witness'),'witness_sha256':sha(out/'witness.json'),'first_divergent_edge':first,'accepted_queue_write_bounds':data['accepted_queue_write_bound'],'internal_state_reads':'read-only diagnostic observation and shadow accepted-write tracking; never model inputs','internal_state_injected':False,'source_logic_modified':False,'hardware_contacted':False,'timing_certified':False}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'first_divergent_cycle':first['cycle'],'seeds':[first['seed_a'],first['seed_b']],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
