#!/usr/bin/env python3
"""Build the strict external-port replay checker; internal state is never an input."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--observer',type=Path,default=ROOT/'build/cache-hierarchy-observer-v1');p.add_argument('--model',type=Path,default=ROOT/'build/cache-hierarchy-native-v2');p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-replay-v1');a=p.parse_args();out=a.output.resolve();observer=a.observer.resolve();model=a.model.resolve()
    if out.exists():raise ValueError('fresh cache replay build directory required')
    out.mkdir()
    while not(observer/'build.json').exists():time.sleep(1)
    receipt=json.loads((observer/'build.json').read_text());fields=receipt['fields'];kinds={'shuttle':'ShuttleL1D','rocket':'RocketL1D','l2':'InclusiveL2'}
    code='#pragma once\nstatic constexpr unsigned FRAME_WORDS='+str(receipt['frame_words'])+';\nstatic std::vector<Definition> definitions(){return {\n';rules=[]
    for instance in ('shuttle0','shuttle1','rocket2','l2'):
        group=[x for x in fields if x['instance']==instance];by_name={x['name']:x for x in group};off=lambda n:by_name[n]['word_offset']+1 if n in by_name else -1
        inputs=[];outputs=[]
        for field in group:
            if field['direction']=='input':inputs.append('{'+','.join(map(str,[field['word_offset']+1,field['index'],field['word_count']]))+'}');continue
            name=field['name'];valid=flag=opcode=-1;kind=0;reason='source-defined control output'
            if '_bits_'in name and name.startswith('auto_'):
                prefix,payload=name.split('_bits_',1);valid=off(prefix+'_valid');opcode=off(prefix+'_bits_opcode');reason='TL payload only while source channel valid'
                if payload=='data':
                    channel=prefix.rsplit('_',1)[1]
                    if channel=='a':kind=1
                    elif channel=='c':kind=2
                    elif channel=='d':kind=3
                    else:kind=9;reason='Probe has no data payload'
            elif name.startswith('io_resp_bits_')or name.startswith('io_cpu_resp_bits_'):
                prefix='io_cpu_resp'if name.startswith('io_cpu_')else'io_resp';valid=off(prefix+'_valid');reason='CPU response payload only while response valid'
                payload=name[len(prefix+'_bits_'):]
                if payload in ('data','data_word_bypass','data_raw'):flag=off(prefix+'_bits_has_data');reason+=' and has_data'
                elif payload=='store_data':kind=4;opcode=off(prefix+'_bits_cmd');reason+=' and source command writes data'
            elif name.startswith('io_ptw_req_bits_'):
                valid=off('io_ptw_req_valid');reason='PTW request payload only while its source Decoupled request is valid'
            elif name.startswith('io_tlb_port_s1_resp_'):
                # This scalar probe does not drive the separate Saturn TLB port.
                # Its inactive payload has no returning-request validity output.
                kind=9;reason='inactive auxiliary TLB response has no source-defined observation in scalar corpus'
            outputs.append('{'+','.join(map(str,[field['word_offset']+1,field['index'],field['word_count'],valid,flag,opcode,kind]))+','+json.dumps(name)+'}')
            rules.append({'instance':instance,'name':name,'kind':kind,'valid_offset':valid,'flag_offset':flag,'opcode_offset':opcode,'reason':reason})
        req='io_req'if group[0]['kind']=='shuttle'else'io_cpu_req';resp='io_resp_valid'if group[0]['kind']=='shuttle'else'io_cpu_resp_valid';nack='io_s2_nack'if group[0]['kind']=='shuttle'else'io_cpu_s2_nack'
        values=[off('reset'),off(req+'_valid'),off(req+'_ready'),off(resp),off(nack),off('io_tlb_port_req_valid')]
        code+='{'+json.dumps(instance)+',Component::'+kinds[group[0]['kind']]+',{'+','.join(inputs)+'},{'+','.join(outputs)+'},'+','.join(map(str,values))+'},\n'
    code+='};}\n';(out/'cache_hierarchy_replay_map.hpp').write_text(code)
    (out/'qualification.json').write_text(json.dumps({'schema':'iris.cache_boundary_payload_qualification.v1','rules':rules,'reset_policy':'Replay every edge from first observed asserted reset; compare control and valid-qualified payload after reset deassertion. No cache state, hit, MSHR or readiness output is injected.','inactive_auxiliary_tlb_port_excluded':True},indent=2)+'\n')
    command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(model/'sdk'),'-I'+str(out),str(ROOT/'timing/cache_hierarchy_replay.cpp'),str(model/'sdk/libiris_cache_hierarchy.a'),'-pthread','-latomic','-lz','-o',str(out/'replay')]
    with(out/'build.log').open('w')as log:q=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    if q.returncode:raise RuntimeError('cache boundary replay compilation failed')
    inputs=[Path(__file__),ROOT/'timing/cache_hierarchy_replay.cpp',out/'cache_hierarchy_replay_map.hpp',out/'qualification.json',observer/'build.json',model/'build.json',model/'sdk/libiris_cache_hierarchy.a',model/'sdk/cache_hierarchy.hpp',Path('/usr/bin/g++')]
    result={'schema':'iris.cache_boundary_replay_build.v1','argv':command,'input_sha256':{str(x):sha(x)for x in inputs},'binary_sha256':sha(out/'replay'),'hardware_contacted':False,'timing_certified':False}
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'binary_sha256':result['binary_sha256'],'report_sha256':sha(out/'build.json')}))
if __name__=='__main__':main()
