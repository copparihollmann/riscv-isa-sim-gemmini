#!/usr/bin/env python3
"""Host-only own-context derivatives; source/native model objects stay identical."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
SCOPE='''struct SaturnContextScope {
 VerilatedContext* previous=Verilated::threadContextp();
 SaturnContextScope()=default;
 explicit SaturnContextScope(VerilatedContext*c){select(c);}
 void select(VerilatedContext*c){Verilated::threadContextp(c);}
 ~SaturnContextScope(){Verilated::threadContextp(previous);}
};
'''
IMPL=''' Impl(Profile p,unsigned h,std::uint32_t seed,std::span<const std::string_view> args):profile(p),hart(h){
  if((p==Profile::Compute128&&h>1)||(p==Profile::Rocket256&&h!=2))throw std::invalid_argument("Hart/profile mismatch");
  // Capture the caller before construction changes the Verilator TLS context.
  // A local context is destroyed before the restore guard on constructor error.
  SaturnContextScope caller;
  auto owned=std::make_unique<VerilatedContext>();caller.select(owned.get());
  owned->threads(1);owned->randSeed(seed);owned->randReset(2);
  std::vector<std::string> owned_args{"iris-saturn-runtime"};
  for(auto arg:args){if(arg.empty()||arg.front()!='+'||arg.starts_with("+verilator+"))throw std::invalid_argument("Only explicit source plusargs, not host-seed overrides, are accepted");owned_args.emplace_back(arg);}
  std::vector<const char*> argv;for(const auto&arg:owned_args)argv.push_back(arg.c_str());
  owned->commandArgs(argv.size(),argv.data());
  if(p==Profile::Compute128){compute=std::make_unique<VSaturnCompute>(owned.get());compute->clock=0;}
  else{rocket=std::make_unique<VSaturnRocket>(owned.get());rocket->clock=0;}
  context=std::move(owned);
 }
 ~Impl(){
  if(!context)return;
  SaturnContextScope caller;
  if(caller.previous==context.get())caller.previous=Verilated::defaultContextp();
  caller.select(context.get());compute.reset();rocket.reset();context.reset();
 }
'''
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--variant',choices=['fast','reference'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);reference=R/'build/saturn-timing-component-v1-final';fast=R/'build/saturn-timing-fast-component-v1-final';base=fast/'build/saturn-timing-fast-v1/sdk'if a.variant=='fast'else reference/'build/saturn-timing-sdk-v1';source=(base/'source/saturn_timing.cpp').read_text();begin=source.index(' Impl(Profile p,unsigned h,std::uint32_t seed)');end=source.index('\n};',begin);original=source[begin:end];source=source[:begin]+IMPL.rstrip()+source[end:];source=source.replace('struct SaturnTimingCut::Impl {',SCOPE+'struct SaturnTimingCut::Impl {');old='SaturnTimingCut::SaturnTimingCut(Profile p,unsigned h,std::uint32_t seed,ReferenceScope scope):impl_(std::make_unique<Impl>(p,h,seed)){';new='''SaturnTimingCut::SaturnTimingCut(Profile p,unsigned h,std::uint32_t seed,ReferenceScope scope):SaturnTimingCut(p,h,seed,scope,{}){}
SaturnTimingCut::SaturnTimingCut(Profile p,unsigned h,std::uint32_t seed,ReferenceScope scope,std::span<const std::string_view> args):impl_(std::make_unique<Impl>(p,h,seed,args)){''';assert source.count(old)==1;source=source.replace(old,new)
 for signature in['void SaturnTimingCut::evaluate(const ReferenceInputs&i){','ReferenceOutputs SaturnTimingCut::sample()const{','void SaturnTimingCut::commit(){']:
  assert source.count(signature)==1;source=source.replace(signature,signature+'\n SaturnContextScope owner(impl_->context.get());')
 probe='''std::string SaturnTimingCut::context_argument(std::string_view prefix)const{
 SaturnContextScope owner(impl_->context.get());
 std::string owned(prefix);const char*match=Verilated::commandArgsPlusMatch(owned.c_str());
 return match?std::string(match):std::string();
}
''';source=source.replace('const char* SaturnTimingCut::source_identity()',probe+'const char* SaturnTimingCut::source_identity()');local=out/'source';local.mkdir();implementation=local/'saturn_timing.cpp';implementation.write_text(source);header=(base/'source/saturn_timing.hpp').read_text().replace('#include <string_view>','#include <string_view>\n#include <string>');constructor=' SaturnTimingCut(Profile,unsigned hart,std::uint32_t seed,ReferenceScope);';assert header.count(constructor)==1;header=header.replace(constructor,constructor+'\n SaturnTimingCut(Profile,unsigned hart,std::uint32_t seed,ReferenceScope,std::span<const std::string_view> context_plusargs);\n // Actual owner-context plusarg query; no source edge advances.\n std::string context_argument(std::string_view prefix)const;');api=local/'saturn_timing.hpp';api.write_text(header);driver=local/'saturn_timing_driver.cpp';shutil.copy2(base/'source/saturn_timing_driver.cpp',driver)
 compute=(fast/'build/saturn-timing-fast-v1/native/compute/model')if a.variant=='fast'else reference/'build/saturn-timing-native-v1/compute/model';rocket=reference/'build/saturn-timing-native-v1/rocket/model';tool=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');inputs=[Path(__file__),base/'build.json',base/'sdk/libiris_saturn_timing.a',base/'source/saturn_timing.cpp',base/'source/saturn_timing.hpp',base/'source/saturn_timing_driver.cpp',implementation,api,driver,reference/'report.json',Path('/usr/bin/g++'),Path('/usr/bin/ar')];identity=hashlib.sha256(json.dumps({str(p):sha(p)for p in inputs},sort_keys=True).encode()).hexdigest();identity_header=local/'saturn_timing_identity.hpp';identity_header.write_text('#pragma once\n#define IRIS_SATURN_TIMING_SOURCE_ID "'+identity+'"\n');inputs.append(identity_header);sdk=out/'sdk';sdk.mkdir();library=sdk/'libiris_saturn_timing.a';shutil.copy2(base/'sdk/libiris_saturn_timing.a',library);common=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(local),'-I'+str(tool),'-I'+str(tool/'vltstd'),'-I'+str(compute),'-I'+str(rocket)];commands=[common+['-c',str(implementation),'-o',str(out/'saturn_timing.o')],['/usr/bin/ar','rcs',str(library),str(out/'saturn_timing.o')],common+[str(driver),str(library),'-latomic','-o',str(out/'saturn-timing')],common+[str(reference/'timing/saturn_timing_bench.cpp'),str(library),'-latomic','-o',str(out/'benchmark')]]
 with(out/'build.log').open('w')as log:
  for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 # Exact archive members other than the host wrapper must remain unchanged.
 members=subprocess.check_output(['/usr/bin/ar','t',str(library)],text=True).splitlines();preserved=0
 for member in members:
  if member=='saturn_timing.o':continue
  left=subprocess.check_output(['/usr/bin/ar','p',str(library),member]);right=subprocess.check_output(['/usr/bin/ar','p',str(base/'sdk/libiris_saturn_timing.a'),member]);assert left==right,member;preserved+=1
 shutil.copy2(api,sdk/api.name);inputs.extend([tool/'verilated.h',tool/'verilated.cpp']);report={'schema':'iris.saturn_own_context_host_derivative.v1','variant':a.variant,'source_identity':identity,'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},'native_sha256':sha(out/'saturn-timing'),'library_sha256':sha(library),'model_and_runtime_archive_members_byte_identical':preserved,'own_context_selected_for':['construction','evaluate','sample','commit','destruction','context_argument'],'caller_context_restored_on_scope_exit':True,'default_commandArgs_initialized':True,'global_Verilator_RNG_stream_isolated':False,'unknown_reset_scope_unchanged':True,'source_RTL_or_model_objects_modified':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'variant':a.variant,'source_identity':identity,'native_sha256':report['native_sha256'],'preserved_archive_members':preserved}))
if __name__=='__main__':main()
