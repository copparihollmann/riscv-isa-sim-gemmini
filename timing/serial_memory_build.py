#!/usr/bin/env python3
"""Build the source-coupled, three-clock MBUS/SerialTL/BringupSoC cut."""
import argparse,hashlib,json,os,shlex,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=R/'build/serial-memory-source-v3');p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=8);a=p.parse_args();source=a.source.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh SDK output required')
    src=json.loads((source/'extraction.json').read_text());assert not src['unresolved_candidate_leaves']
    for rel,digest in src['source_sha256'].items():assert sha(source/rel)==digest,rel
    out.mkdir();shutil.copytree(source/'rtl',out/'rtl');(out/'sdk').mkdir();(out/'model').mkdir();shutil.copy2(R/'timing/serial_memory.hpp',out/'sdk/serial_memory.hpp')
    clocks={'iris_clock','bringup_clock','serial_clock'};inputs=[f for f in src['physical_ports']if f['direction']=='input'and f['name']not in clocks];outputs=[f for f in src['physical_ports']if f['direction']=='output']
    code=(R/'timing/serial_memory.cpp').read_text().split('// BEGIN GENERATED PHYSICAL PORT MAP')[0]
    for direction,fs in [('input',inputs),('output',outputs)]:code+='std::span<const Field>Model::'+direction+'_fields()const{static constexpr Field fields[]={'+','.join('{'+json.dumps(f['name'])+','+str(f['width'])+'}'for f in fs)+'};return fields;}\n'
    code+='void Model::evaluate(std::span<const Bits>inputs){if(!impl_)throw std::logic_error("moved SerialTL model");impl_->evaluated=false;OwnerContext scoped(impl_->context.get());auto&m=*impl_->model;\n'
    code+='if(inputs.size()!='+str(len(inputs))+')throw std::invalid_argument("IRIS_SERIAL_MEMORY_PHYSICAL_INPUT_COUNT");\n'
    for i,f in enumerate(inputs):
        assert f['width']<=64;mask=(1<<f['width'])-1
        code+='if((inputs['+str(i)+'].known&'+str(mask)+'ULL)!='+str(mask)+'ULL)throw std::invalid_argument("IRIS_SERIAL_MEMORY_UNKNOWN_INPUT '+f['name']+'");\n'
        if f['width']<64:code+='if(inputs['+str(i)+'].value>'+str(mask)+'ULL)throw std::invalid_argument("IRIS_SERIAL_MEMORY_INPUT_WIDTH '+f['name']+'");\n'
    ri=next(i for i,f in enumerate(inputs)if f['name']=='iris_reset');rb=next(i for i,f in enumerate(inputs)if f['name']=='bringup_reset')
    code+='impl_->iris_reset=inputs['+str(ri)+'].value;impl_->bringup_reset=inputs['+str(rb)+'].value;if(impl_->reset_seen!=7&&!(impl_->iris_reset&&impl_->bringup_reset))throw std::logic_error("IRIS_SERIAL_MEMORY_EXPLICIT_RESET_REQUIRED_ALL_CLOCKS");\n'
    code+='impl_->context->assertOn(impl_->assertion_policy==AssertionPolicy::SourceAlways||!(impl_->iris_reset&&impl_->bringup_reset));\n'
    for i,f in enumerate(inputs):code+='m.'+f['name']+'=inputs['+str(i)+'].value;\n'
    code+='m.eval();impl_->evaluated=true;}\n'
    code+='std::vector<std::uint64_t>Model::sample()const{if(!impl_||!impl_->evaluated)throw std::logic_error("IRIS_SERIAL_MEMORY_SAMPLE_REQUIRES_EVALUATION");OwnerContext scoped(impl_->context.get());const auto&m=*impl_->model;return{'+','.join('std::uint64_t(m.'+f['name']+')'for f in outputs)+'};}\n}\n'
    (out/'serial_memory.generated.cpp').write_text(code);runtime=TOOL.parent.parent/'share/verilator/include'
    inputfiles=[Path(__file__),source/'extraction.json',R/'timing/serial_memory.hpp',R/'timing/serial_memory.cpp',TOOL,TOOL.with_name('verilator_bin'),TOOL.with_name('perl'),Path('/usr/bin/g++'),Path('/usr/bin/ar')]+sorted(runtime.rglob('*.h'))+[runtime/(n+'.cpp')for n in ['verilated','verilated_threads']]
    identity=hashlib.sha256(json.dumps({'input_sha256':{str(q):sha(q)for q in inputfiles},'generated_cpp_sha256':sha(out/'serial_memory.generated.cpp'),'configuration':str(src['module_count'])+'module exact archived conversion path; explicit3clock simultaneous phases; actual FIFOs/PHY/width/reset; strict external knownness'},sort_keys=True).encode()).hexdigest()
    (out/'sdk/serial_memory_identity.hpp').write_text('#pragma once\n#define IRIS_SERIAL_MEMORY_SOURCE_ID "'+identity+'"\n')
    commands=[[str(TOOL.with_name('perl')),str(TOOL),'--cc','--build','-j',str(a.jobs),'--top-module',src['top'],'--prefix','VIrisSerialMemoryPath','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(out/'model'),'-I'+str(out/'rtl'),'-y',str(out/'rtl'),'+libext+.sv+.v','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT','+define+RANDOMIZE_GARBAGE_ASSIGN','+define+RANDOMIZE_INVALID_ASSIGN','+define+STOP_COND=$c("Verilated::threadContextp()->assertOn()")','+define+PRINTF_COND=$c("Verilated::threadContextp()->assertOn()")',str(out/'rtl/IrisSerialMemoryPath.sv'),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3']]
    env=dict(os.environ,PATH=str(TOOL.parent)+os.pathsep+os.environ['PATH']);start=time.monotonic()
    with(out/'model.build.log').open('w')as log:status=subprocess.run(commands[-1],env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    if not status:
        include=['-I'+str(out/'sdk'),'-I'+str(out/'model'),'-I'+str(runtime)]
        for name,path in [('serial_memory',out/'serial_memory.generated.cpp'),('verilated',runtime/'verilated.cpp'),('verilated_threads',runtime/'verilated_threads.cpp')]:commands.append(['/usr/bin/g++','-O3','-std=c++20','-MD','-MF',str(out/(name+'.d')),*include,'-c',str(path),'-o',str(out/(name+'.o'))])
        objects=[out/(n+'.o')for n in ['serial_memory','verilated','verilated_threads']]+sorted((out/'model').glob('VIrisSerialMemoryPath*.o'));commands.append(['/usr/bin/ar','rcs',str(out/'sdk/libiris_serial_memory.a'),*map(str,objects)])
        with(out/'sdk.build.log').open('w')as log:
            for command in commands[1:]:
                status=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
                if status:break
    deps=set()
    for q in out.glob('*.d'):
        for entry in shlex.split(q.read_text().replace('\\\n',' ').split(':',1)[1]):
            f=Path(entry);f=f if f.is_absolute()else R/f
            if f.is_file():deps.add(f)
    receipt={'schema':'iris.archived_serial_memory_SDK_build.v1','exit_status':status,'source_identity':identity,'argv':commands,'input_sha256':{str(q):sha(q)for q in inputfiles},'compiled_dependency_sha256':{str(q):sha(q)for q in sorted(deps)},'RTL_sha256':{str(q):sha(q)for q in sorted((out/'rtl').iterdir())},'generated_cpp_sha256':sha(out/'serial_memory.generated.cpp'),'library_sha256':sha(out/'sdk/libiris_serial_memory.a')if not status else None,'host_seconds':time.monotonic()-start,'edge_policy':'caller explicitly supplies simultaneous Iris/Bringup/Serial edge set; no edge from combinational settling','external_service_supplied':False,'observed_state_or_readiness_injected':False,'public_internal_state_access':False,'hardware_contacted':False,'source_image_association_verified':False,'timing_certified':False,'calibration_usable':False}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:receipt[k]for k in ['exit_status','source_identity','library_sha256','host_seconds']}));raise SystemExit(status)
if __name__=='__main__':main()
