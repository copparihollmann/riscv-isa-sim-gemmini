#!/usr/bin/env python3
"""Build the exact archived target-clock LatencyPipe, with no service defaults."""
import argparse,hashlib,json,os,shlex,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=R/'build/fased-service-source-v2');p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=8);a=p.parse_args()
    source=a.source.resolve();out=a.output.resolve();report=json.loads((source/'extraction.json').read_text())
    if out.exists():raise ValueError('fresh build directory required')
    unit=report['image_source_units']['LatencyPipe'];assert not unit['unresolved_candidate_leaves']
    for module in unit['modules']:
        rel='rtl/'+module+'.sv';assert sha(source/rel)==report['extracted_files'][rel]
    out.mkdir();(out/'rtl').mkdir();(out/'sdk').mkdir();(out/'model').mkdir()
    for module in unit['modules']:shutil.copy2(source/'rtl'/(module+'.sv'),out/'rtl'/(module+'.sv'))
    fields=unit['physical_ports'];inputs=[x for x in fields if x['direction']=='input' and not x['name'].startswith('tNasti_io_mmReg_')];outputs=[x for x in fields if x['direction']=='output']
    code=(R/'timing/fased_service.cpp').read_text().split('// BEGIN GENERATED PHYSICAL PORT MAP')[0]
    for direction,fs in [('input',inputs),('output',outputs)]:
        code+='std::span<const Field> Model::'+direction+'_fields()const{static constexpr Field fields[]={'+','.join('{'+json.dumps(x['name'])+','+str(x['width'])+'}'for x in fs)+'};return fields;}\n'
    code+='void Model::evaluate(std::span<const Bits> inputs){if(!impl_)throw std::logic_error("moved FASED model");impl_->evaluated=false;OwnerContext scoped(impl_->context.get());auto&m=*impl_->model;\n'
    code+='if(inputs.size()!='+str(len(inputs))+')throw std::invalid_argument("IRIS_FASED_PHYSICAL_INPUT_COUNT");\n'
    for i,x in enumerate(inputs):
        mask=(1<<x['width'])-1;code+='if((inputs['+str(i)+'].known&'+str(mask)+'ULL)!='+str(mask)+'ULL)throw std::invalid_argument("IRIS_FASED_UNKNOWN_INPUT '+x['name']+'");\n'
        if x['width']<64:code+='if(inputs['+str(i)+'].value>'+str(mask)+'ULL)throw std::invalid_argument("IRIS_FASED_INPUT_WIDTH '+x['name']+'");\n'
    reset=next(i for i,x in enumerate(inputs)if x['name']=='reset')
    code+='if(!impl_->reset_seen&&!inputs['+str(reset)+'].value)throw std::logic_error("IRIS_FASED_EXPLICIT_RESET_REQUIRED");impl_->evaluated_reset=inputs['+str(reset)+'].value;\n'
    for i,x in enumerate(inputs):code+='m.'+x['name']+'=inputs['+str(i)+'].value;\n'
    for field,param in [('readMaxReqs','read_max_requests'),('writeMaxReqs','write_max_requests'),('readLatency','read_latency'),('writeLatency','write_latency')]:code+='m.tNasti_io_mmReg_'+field+'=impl_->parameters.'+param+';\n'
    for ch in ('ar','aw'):code+='if(m.tNasti_io_tNasti_'+ch+'_valid&&!(m.tNasti_io_tNasti_'+ch+'_bits_burst==1||(m.tNasti_io_tNasti_'+ch+'_bits_burst==0&&!m.tNasti_io_tNasti_'+ch+'_bits_len)))throw std::invalid_argument("IRIS_FASED_UNSUPPORTED_BURST");\n'
    for ch in ('ar','aw'):code+='if(m.tNasti_io_tNasti_'+ch+'_valid&&m.tNasti_io_tNasti_'+ch+'_bits_len>7)throw std::invalid_argument("IRIS_FASED_BURST_EXCEEDS_ARCHIVED_8_BEAT_LIMIT");\n'
    code+='m.eval();impl_->evaluated=true;}\n'
    code+='std::vector<std::uint64_t> Model::sample()const{if(!impl_||!impl_->evaluated)throw std::logic_error("IRIS_FASED_SAMPLE_REQUIRES_EVALUATION");OwnerContext scoped(impl_->context.get());const auto&m=*impl_->model;return {'+','.join('std::uint64_t(m.'+x['name']+')'for x in outputs)+'};}\n'
    code+='void Model::commit(){if(!impl_||!impl_->evaluated)throw std::logic_error("IRIS_FASED_COMMIT_REQUIRES_EVALUATION");OwnerContext scoped(impl_->context.get());auto&m=*impl_->model;m.clock=1;m.eval();m.clock=0;m.eval();impl_->reset_seen|=impl_->evaluated_reset;impl_->evaluated=false;++impl_->edges;}\n}\n'
    (out/'fased_service.generated.cpp').write_text(code);shutil.copy2(R/'timing/fased_service.hpp',out/'sdk/fased_service.hpp')
    runtime=TOOL.parent.parent/'share/verilator/include'
    inputs_files=[Path(__file__),source/'extraction.json',R/'timing/fased_service.hpp',R/'timing/fased_service.cpp',TOOL,TOOL.with_name('verilator_bin'),TOOL.with_name('perl'),Path('/usr/bin/g++'),Path('/usr/bin/ar')]+sorted(runtime.rglob('*.h'))+[runtime/(n+'.cpp')for n in ['verilated','verilated_threads']]
    identity=hashlib.sha256(json.dumps({'inputs':{str(p):sha(p)for p in inputs_files},'generated':sha(out/'fased_service.generated.cpp'),'configuration':'archived exact target-clock LatencyPipe; explicit parameters; scoped context; strict physical knownness'},sort_keys=True).encode()).hexdigest()
    (out/'sdk/fased_service_identity.hpp').write_text('#pragma once\n#define IRIS_FASED_SERVICE_SOURCE_ID "'+identity+'"\n')
    env=dict(os.environ,PATH=str(TOOL.parent)+os.pathsep+os.environ['PATH'])
    commands=[[str(TOOL.with_name('perl')),str(TOOL),'--cc','--build','-j',str(a.jobs),'--top-module','LatencyPipe','--prefix','VFASEDLatencyPipe','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(out/'model'),'-I'+str(out/'rtl'),'-y',str(out/'rtl'),'+libext+.sv+.v','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT','+define+RANDOMIZE_GARBAGE_ASSIGN','+define+RANDOMIZE_INVALID_ASSIGN',str(out/'rtl/LatencyPipe.sv'),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3']]
    status=0;start=time.monotonic()
    with(out/'model.build.log').open('w')as log:status=subprocess.run(commands[-1],env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    if not status:
        include=['-I'+str(out/'sdk'),'-I'+str(out/'model'),'-I'+str(runtime)]
        for name,path in [('fased_service',out/'fased_service.generated.cpp'),('verilated',runtime/'verilated.cpp'),('verilated_threads',runtime/'verilated_threads.cpp')]:commands.append(['/usr/bin/g++','-O3','-std=c++20','-MD','-MF',str(out/(name+'.d')),*include,'-c',str(path),'-o',str(out/(name+'.o'))])
        objects=[out/(n+'.o')for n in ['fased_service','verilated','verilated_threads']]+sorted((out/'model').glob('VFASEDLatencyPipe*.o'))
        commands.append(['/usr/bin/ar','rcs',str(out/'sdk/libiris_fased_service.a'),*map(str,objects)])
        with(out/'sdk.build.log').open('w')as log:
            for command in commands[1:]:
                status=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
                if status:break
    dependency_files=set()
    for path in out.glob('*.d'):
        for entry in shlex.split(path.read_text().replace('\\\n',' ').split(':',1)[1]):
            file=Path(entry)
            if not file.is_absolute():file=R/file
            if file.is_file():dependency_files.add(file)
    receipt={'schema':'iris.fased_target_latency_pipe_sdk_build.v1','source_identity':identity,'argv':commands,'exit_status':status,'host_seconds':time.monotonic()-start,'input_sha256':{str(p):sha(p)for p in inputs_files},'compiled_dependency_sha256':{str(p):sha(p)for p in sorted(dependency_files)},'RTL_sha256':{str(p):sha(p)for p in sorted((out/'rtl').iterdir())},'generated_cpp_sha256':sha(out/'fased_service.generated.cpp'),'library_sha256':sha(out/'sdk/libiris_fased_service.a')if not status else None,'parameters_have_no_defaults':True,'public_internal_state_access':False,'clock':'exact one caller-supplied LatencyPipe target edge per commit','full_FASED_host_token_functional_model':False,'serial_TL_path_modeled':False,'hardware_contacted':False,'source_image_association_verified':False,'calibration_usable':False,'timing_certified':False}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:receipt[k]for k in ['source_identity','exit_status','host_seconds','library_sha256']}))
    if status:raise SystemExit(status)
if __name__=='__main__':main()
