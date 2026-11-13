#!/usr/bin/env python3
"""Host-only derivative: preserve caller across full context destruction/unwind."""
import argparse,hashlib,json,re,shlex,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
V=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('fresh context derivative required')
    plans={'serial':{'base':R/'build/serial-memory-native-v4','cpp':'serial_memory.generated.cpp','object':'serial_memory.o','library':'libiris_serial_memory.a','header':'serial_memory_identity.hpp','macro':'IRIS_SERIAL_MEMORY_SOURCE_ID','prefix':'VIrisSerialMemoryPath'},'fased':{'base':R/'build/fased-service-native-v3','cpp':'fased_service.generated.cpp','object':'fased_service.o','library':'libiris_fased_service.a','header':'fased_service_identity.hpp','macro':'IRIS_FASED_SERVICE_SOURCE_ID','prefix':'VFASEDLatencyPipe'}}
    out.mkdir();commands=[];reports={};start=time.monotonic()
    for name,q in plans.items():
        base=q['base'];prior=json.loads((base/'build.json').read_text());lib=base/'sdk'/q['library'];assert sha(lib)==prior['library_sha256'];original=base/q['cpp'];assert sha(original)==prior['generated_cpp_sha256'];code=original.read_text();dest=out/name;dest.mkdir();(dest/'sdk').mkdir();(dest/'objects').mkdir()
        helper='''#include <utility>
namespace {
struct IrisHostPreserveContext {
  VerilatedContext* previous=Verilated::threadContextp();
  ~IrisHostPreserveContext(){Verilated::threadContextp(previous);}
};
template<class T,class...Args>
std::unique_ptr<T> iris_host_owned_make(Args&&...args){
  IrisHostPreserveContext preserve;
  return std::make_unique<T>(std::forward<Args>(args)...);
}
}
'''
        index=code.index('namespace iris::');code=code[:index]+helper+code[index:]
        assert code.count('std::make_unique<Impl>(')==1;code=code.replace('std::make_unique<Impl>(', 'iris_host_owned_make<Impl>(')
        destroy='if(impl_){auto*previous=Verilated::threadContextp();auto*owner=impl_->context.get();Verilated::threadContextp(owner);impl_.reset();Verilated::threadContextp(previous==owner?nullptr:previous);}'
        assert code.count('Model::~Model()=default;')==1;code=code.replace('Model::~Model()=default;','Model::~Model(){'+destroy+'}')
        move=r'Model&\s*Model::operator=\(Model&&\)\s*noexcept=default;';assert len(re.findall(move,code))==1
        code=re.sub(move,'Model&Model::operator=(Model&&other)noexcept{if(this!=&other){'+destroy+'impl_=std::move(other.impl_);}return*this;}',code,count=1)
        model_cpp=base/'model'/(q['prefix']+'.cpp');assert re.search(r'unsigned '+q['prefix']+r'::threads\(\) const \{ return 1; \}',model_cpp.read_text())
        assert code.count('context->randReset(2);')==1;code=code.replace('context->randReset(2);','context->randReset(2);context->threads(1);',1)
        identity=hashlib.sha256(json.dumps({'base_library_sha256':sha(lib),'base_cpp_sha256':sha(original),'new_cpp_sha256':hashlib.sha256(code.encode()).hexdigest(),'generator_sha256':sha(__file__),'compiler_sha256':sha('/usr/bin/g++'),'verilated_h_sha256':sha(V/'verilated.h'),'policy':'outer construction/unwind/destruction/move assignment preserve caller after entire Impl and context destruction; all target objects unchanged'},sort_keys=True).encode()).hexdigest()
        for header in (base/'sdk').glob('*.hpp'):shutil.copy2(header,dest/'sdk'/header.name)
        (dest/'sdk'/q['header']).write_text('#pragma once\n#define '+q['macro']+' "'+identity+'"\n');cpp=dest/'host-context.cpp';cpp.write_text(code)
        command=['/usr/bin/ar','x',str(lib)];commands.append(command);subprocess.run(command,cwd=dest/'objects',check=True);objects={p.name:sha(p)for p in(dest/'objects').iterdir()};assert q['object']in objects
        command=['/usr/bin/g++','-O3','-std=c++20','-MD','-MF',str(dest/'wrapper.d'),'-I'+str(dest/'sdk'),'-I'+str(base/'model'),'-I'+str(V),'-c',str(cpp),'-o',str(dest/'objects'/q['object'])];commands.append(command)
        with(dest/'compile.stdout').open('w')as stdout,(dest/'compile.stderr').open('w')as stderr:status=subprocess.run(command,stdout=stdout,stderr=stderr).returncode
        if status:raise RuntimeError('context derivative compile failed '+name)
        changed=[p.name for p in(dest/'objects').iterdir()if sha(p)!=objects[p.name]];assert changed==[q['object']]
        command=['/usr/bin/ar','rcs',str(dest/'sdk'/q['library']),*map(str,sorted((dest/'objects').iterdir()))];commands.append(command);subprocess.run(command,check=True)
        deps={Path(x)for x in shlex.split((dest/'wrapper.d').read_text().replace('\\\n',' ').split(':',1)[1])}
        receipt={'schema':'iris.external_memory_host_context_derivative.v1','source_identity':identity,'base_library':str(lib),'base_library_sha256':sha(lib),'base_build_json':str(base/'build.json'),'base_build_json_sha256':sha(base/'build.json'),'base_wrapper':str(original),'base_wrapper_sha256':sha(original),'new_wrapper_sha256':sha(cpp),'library_sha256':sha(dest/'sdk'/q['library']),'only_replaced_object':q['object'],'unchanged_object_sha256':{n:h for n,h in objects.items()if n!=q['object']},'compiled_dependency_sha256':{str(q):sha(q)for q in sorted(deps)if q.is_file()},'single_host_thread_evidence':{'model_cpp':str(model_cpp),'sha256':sha(model_cpp),'model_threads':1,'context_threads':1,'unused_default_worker_pool_disabled':True},'RTL_model_and_runtime_objects_unchanged':True,'public_header_unchanged_except_identity':True,'host_policy_only':True,'fix':'VerilatedContext::~VerilatedContext selects its owner then clears threadContextp; preserve outside complete Impl deletion and constructor-unwind. Explicit move assignment uses same complete cleanup.','hardware_contacted':False,'source_image_association_verified':False,'timing_certified':False,'calibration_usable':False}
        (dest/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');reports[name]=receipt
    report={'schema':'iris.external_memory_context_derivatives.v1','components':reports,'argv':commands,'input_sha256':{str(p):sha(p)for p in [Path(__file__),Path('/usr/bin/g++'),Path('/usr/bin/ar'),V/'verilated.h',V/'verilated.cpp']},'host_seconds':time.monotonic()-start,'source_RTL_or_timing_logic_changed':False,'hardware_contacted':False,'timing_certified':False}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'identities':{n:j['source_identity']for n,j in reports.items()},'host_seconds':report['host_seconds']}))
if __name__=='__main__':main()
