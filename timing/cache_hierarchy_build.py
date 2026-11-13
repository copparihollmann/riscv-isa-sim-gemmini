#!/usr/bin/env python3
"""Build port-only saved L1D/L2 RTL models into a reusable in-process SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
KINDS={'shuttle':('ShuttleL1D','VCacheShuttle'),'rocket':('RocketL1D','VCacheRocket'),'l2':('InclusiveL2','VCacheL2')}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def field_table(fields):
    return ',\n'.join('{'+json.dumps(x['name'])+','+str(x['width'])+'}'for x in fields)
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=ROOT/'build/cache-hierarchy-source-v1');p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-native-v1');p.add_argument('--jobs',type=int,default=8);a=p.parse_args()
    source=a.source.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh native build output required')
    report=json.loads((source/'extraction.json').read_text())
    for name,digest in report['extracted_files'].items():
        if sha(source/'rtl'/name)!=digest:raise ValueError('source RTL identity mismatch '+name)
    out.mkdir();shutil.copytree(source/'rtl',out/'rtl');(out/'sdk').mkdir()
    for name in ('cache_hierarchy.hpp',):shutil.copyfile(ROOT/'timing'/name,out/'sdk'/name)
    code=(ROOT/'timing/cache_hierarchy.cpp').read_text().split('// BEGIN GENERATED PHYSICAL PORT MAP')[0]
    input_cases=[];sample_cases=[];commit_cases=[];table_cases={'input':[],'output':[]}
    for kind,(enum,prefix)in KINDS.items():
        info=report['components'][kind];members={'shuttle':'shuttle','rocket':'rocket','l2':'l2'};member=members[kind]
        inputs=[x for x in info['physical_ports']if x['direction']=='input'];outputs=[x for x in info['physical_ports']if x['direction']=='output']
        block='case Component::'+enum+':{auto &m=*impl_->'+member+';\n'
        block+='if(inputs.size()!='+str(len(inputs))+')throw std::invalid_argument("physical cache input count disagrees");\n'
        for x in inputs:
            words=(x['width']+63)//64;tail=x['width']%64
            for limb in range(words,4):block+='if(inputs['+str(x['index'])+'].limbs['+str(limb)+'])throw std::invalid_argument("physical cache input exceeds width: '+x['name']+'");\n'
            if tail:block+='if(inputs['+str(x['index'])+'].limbs['+str(words-1)+']>='+str(1<<tail)+'ULL)throw std::invalid_argument("physical cache input exceeds width: '+x['name']+'");\n'
        reset_index=next(x['index']for x in inputs if x['name']=='reset')
        block+='if(!impl_->reset_seen&&!inputs['+str(reset_index)+'].limbs[0])throw std::logic_error("cache requires an explicitly committed reset before active operation");\n'
        block+='impl_->evaluated_reset=inputs['+str(reset_index)+'].limbs[0];\n'
        for x in inputs:
            index=x['index'];name=x['name'];bits=x['width']
            if bits<=64:block+='m.'+name+'=inputs['+str(index)+'].limbs[0];\n'
            else:
                for word in range((bits+31)//32):block+='m.'+name+'['+str(word)+']=inputs['+str(index)+'].limbs['+str(word//2)+']'+('>>32'if word%2 else'')+';\n'
        block+='m.eval();\n'
        if kind=='shuttle':
            prefix='r.ShuttleDCache__DOT__mshrs__DOT__mshrs_'
            block+='const auto&r=*m.rootp;unsigned selected=3;\n'
            # Highest-priority valid replay selects0,1,2; otherwise3, including
            # the invalid-all case. This is exact Arbiter4_ShuttleMSHRReq RTL.
            for queue in (2,1,0):
                q=prefix+str(queue)+'__DOT__'
                block+='if('+q+'state==8&&('+q+'rpq__DOT__maybe_full||'+q+'rpq__DOT__enq_ptr_value!='+q+'rpq__DOT__deq_ptr_value))selected='+str(queue)+';\n'
            block+='const std::array<unsigned,4> heads={'+','.join(prefix+str(q)+'__DOT__rpq__DOT__deq_ptr_value'for q in range(4))+'};\n'
            block+='const bool write=m.io_req_bits_cmd==1||m.io_req_bits_cmd==4||m.io_req_bits_cmd==7||(m.io_req_bits_cmd>=8&&m.io_req_bits_cmd<=15)||m.io_req_bits_cmd==17;\n'
            block+='impl_->pending_unknown_replay=!m.reset&&m.io_req_valid&&m.io_req_ready&&write&&!impl_->replay_command_known[selected][heads[selected]];\n'
            block+='if(impl_->pending_unknown_replay&&impl_->replay_policy==UnresetReplayPolicy::RefuseUse)throw std::runtime_error("IRIS_SHUTTLE_INVALID_REPLAY_COMMAND_UNDEFINED queue="+std::to_string(selected)+" slot="+std::to_string(heads[selected]));\n'
        input_cases.append(block+'break;}\n')
        block='case Component::'+enum+':{const auto &m=*impl_->'+member+';std::vector<Bits> out('+str(len(outputs))+');\n'
        for x in outputs:
            index=x['index'];name=x['name'];bits=x['width']
            if bits<=64:block+='out['+str(index)+'].limbs[0]=m.'+name+';\n'
            else:
                for word in range((bits+31)//32):block+='out['+str(index)+'].limbs['+str(word//2)+']|=std::uint64_t(m.'+name+'['+str(word)+'])'+('<<32'if word%2 else'')+';\n'
        sample_cases.append(block+'return out;}\n')
        commit='case Component::'+enum+':{auto&m=*impl_->'+member+';\n'
        if kind=='shuttle':
            prefix='r.ShuttleDCache__DOT__mshrs__DOT__mshrs_'
            commit+='const auto&r=*m.rootp;const bool active=!m.reset;\n'
            commit+='const std::array<bool,4> writes={'+','.join('bool('+prefix+str(q)+'__DOT__rpq__DOT__do_enq)'for q in range(4))+'};\n'
            commit+='const std::array<unsigned,4> slots={'+','.join(prefix+str(q)+'__DOT__rpq__DOT__enq_ptr_value'for q in range(4))+'};\n'
        commit+='m.clock=1;m.eval();m.clock=0;m.eval();\n'
        if kind=='shuttle':
            commit+='if(active)for(unsigned q=0;q<4;++q)if(writes[q])impl_->replay_command_known[q][slots[q]]=true;\n'
            commit+='impl_->concretized_unknown_replay|=impl_->pending_unknown_replay;\n'
        commit_cases.append(commit+'break;}\n')
        for direction,fields in [('input',inputs),('output',outputs)]:
            table_cases[direction].append('case Component::'+enum+':{static constexpr Field fields[]={\n'+field_table(fields)+'\n};return fields;}\n')
    code+='void Model::evaluate(std::span<const Bits> inputs){impl_->evaluated=false;impl_->pending_unknown_replay=false;switch(impl_->kind){\n'+''.join(input_cases)+'}impl_->evaluated=true;}\n'
    code+='std::vector<Bits> Model::sample()const{if(!impl_->evaluated)throw std::logic_error("cache sample requires current edge evaluation");switch(impl_->kind){\n'+''.join(sample_cases)+'}throw std::logic_error("invalid cache component");}\n'
    code+='void Model::commit(){if(!impl_->evaluated)throw std::logic_error("cache commit requires fresh evaluation");switch(impl_->kind){\n'+''.join(commit_cases)+'}++impl_->edge_count;impl_->reset_seen=impl_->reset_seen||impl_->evaluated_reset;impl_->evaluated=false;}\n'
    for direction in ('input','output'):code+='std::span<const Field> Model::'+direction+'_fields()const{switch(impl_->kind){\n'+''.join(table_cases[direction])+'}throw std::logic_error("invalid cache component");}\n'
    code+='}\n';(out/'cache_hierarchy.generated.cpp').write_text(code)
    inputs=[Path(__file__),source/'extraction.json',ROOT/'timing/cache_hierarchy.hpp',ROOT/'timing/cache_hierarchy.cpp',ROOT/'timing/cache_hierarchy_driver.cpp',TOOL,TOOL.with_name('verilator_bin'),TOOL.with_name('perl'),Path('/usr/bin/g++'),Path('/usr/bin/ar')]
    runtime_root=TOOL.parent.parent/'share/verilator/include'
    inputs+=sorted(runtime_root.rglob('*.h'))+[runtime_root/(name+'.cpp')for name in ('verilated','verilated_threads','verilated_save')]
    identity=hashlib.sha256(json.dumps({'inputs':{str(p):sha(p)for p in inputs},'generated_cpp_sha256':sha(out/'cache_hierarchy.generated.cpp'),'configuration':'actual unmodified saved RTL; port-only; arbitrary unreset state; explicit evaluate/sample/commit; v1'},sort_keys=True).encode()).hexdigest()
    (out/'sdk/cache_hierarchy_identity.hpp').write_text('#pragma once\n#define IRIS_CACHE_HIERARCHY_SOURCE_ID "'+identity+'"\n')
    commands=[];start=time.monotonic();status=0
    env=dict(os.environ,PATH=str(TOOL.parent)+os.pathsep+os.environ['PATH'])
    for kind,(_,prefix)in KINDS.items():
        model=out/kind;model.mkdir()
        command=[str(TOOL.with_name('perl')),str(TOOL),'--cc','--build','-j',str(a.jobs),'--top-module',report['components'][kind]['top'],'--prefix',prefix,'--assert','--savable','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(model),'-I'+str(out/'rtl'),'-y',str(out/'rtl'),'+libext+.sv+.v','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT','+define+RANDOMIZE_GARBAGE_ASSIGN','+define+RANDOMIZE_INVALID_ASSIGN',str(out/'rtl'/(report['components'][kind]['top']+'.sv')),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3']
        commands.append(command)
        with(out/(kind+'.build.log')).open('w')as log:status=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
        if status:break
    if not status:
        include=['-I'+str(out/'sdk'),'-I'+str(TOOL.parent.parent/'share/verilator/include')]+['-I'+str(out/k)for k in KINDS]
        commands.append(['/usr/bin/g++','-O3','-std=c++20',*include,'-c',str(out/'cache_hierarchy.generated.cpp'),'-o',str(out/'cache_hierarchy.o')])
        runtime=[]
        for name in ('verilated','verilated_threads','verilated_save'):
            obj=out/(name+'.o');runtime.append(obj)
            commands.append(['/usr/bin/g++','-O3','-std=c++20',*include,'-c',str(TOOL.parent.parent/'share/verilator/include'/(name+'.cpp')),'-o',str(obj)])
        model_objects=[p for kind,(_,prefix)in KINDS.items()for p in sorted((out/kind).glob(prefix+'*.o'))]
        commands.append(['/usr/bin/ar','rcs',str(out/'sdk/libiris_cache_hierarchy.a'),str(out/'cache_hierarchy.o'),*map(str,runtime+model_objects)])
        commands.append(['/usr/bin/g++','-O3','-std=c++20','-I'+str(out/'sdk'),str(ROOT/'timing/cache_hierarchy_driver.cpp'),str(out/'sdk/libiris_cache_hierarchy.a'),'-pthread','-latomic','-o',str(out/'cache-hierarchy')])
        with(out/'sdk.build.log').open('w')as log:
            for command in commands[3:]:
                status=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
                if status:break
    receipt={'schema':'iris.cache_hierarchy_sdk_build.v1','source_identity':identity,'argv':commands,'exit_status':status,'host_seconds':time.monotonic()-start,
        'input_sha256':{str(p):sha(p)for p in inputs},'source_sha256':{str(p):sha(p)for p in (out/'rtl').iterdir()},'generated_cpp_sha256':sha(out/'cache_hierarchy.generated.cpp'),
        'public_internal_state_access':False,'added_clock_edges':0,'automatic_external_service':False,'hardware_contacted':False,'timing_certified':False}
    if not status:
        dynamic=subprocess.check_output(['/usr/bin/ldd',str(out/'cache-hierarchy')],text=True)
        (out/'linked-runtime.txt').write_text(dynamic)
        linked=[]
        for line in dynamic.splitlines():
            for token in line.split():
                if token.startswith('/')and Path(token).is_file():linked.append(Path(token).resolve())
        receipt.update(binary_sha256=sha(out/'cache-hierarchy'),library_sha256=sha(out/'sdk/libiris_cache_hierarchy.a'),
                       host_link_runtime_sha256={str(path):sha(path)for path in sorted(set(linked))},
                       generated_model_sha256={str(path):sha(path)for kind in KINDS for pattern in ('*.cpp','*.h')for path in sorted((out/kind).glob(pattern))},
                       duplicate_runtime_objects_in_sdk=False,unreset_replay_control_policy="default refuse; per-slot accepted-write knownness; concrete reset exploration requires explicit opt-in")
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'exit_status':status,'source_identity':identity,'binary_sha256':receipt.get('binary_sha256'),'host_seconds':receipt['host_seconds']}))
    if status:raise SystemExit(status)
if __name__=='__main__':main()
