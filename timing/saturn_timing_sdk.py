#!/usr/bin/env python3
"""Package phase-correct full Saturn cuts; duplicate datapath is explicit reference scope."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();b=a.native.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=out/'sdk';sdk.mkdir();profiles={k:json.loads((b/k/'ports.json').read_text())for k in ['compute','rocket']};source='''#include "saturn_timing.hpp"
#include "saturn_timing_identity.hpp"
#include "VSaturnCompute.h"
#include "VSaturnRocket.h"
#include "verilated.h"
#include <stdexcept>
namespace iris::saturn {
struct SaturnTimingCut::Impl {
 Profile profile;unsigned hart;std::uint64_t edge_count=0;bool evaluated=false;
 std::unique_ptr<VerilatedContext> context;std::unique_ptr<VSaturnCompute> compute;std::unique_ptr<VSaturnRocket> rocket;
 Impl(Profile p,unsigned h,std::uint32_t seed):profile(p),hart(h),context(std::make_unique<VerilatedContext>()){
  if((p==Profile::Compute128&&h>1)||(p==Profile::Rocket256&&h!=2))throw std::invalid_argument("Hart/profile mismatch");
  context->threads(1);context->randSeed(seed);context->randReset(2);
  if(p==Profile::Compute128){compute=std::make_unique<VSaturnCompute>(context.get());compute->clock=0;}
  else{rocket=std::make_unique<VSaturnRocket>(context.get());rocket->clock=0;}
 }
};
SaturnTimingCut::SaturnTimingCut(Profile p,unsigned h,std::uint32_t seed,ReferenceScope scope):impl_(std::make_unique<Impl>(p,h,seed)){
 if(scope!=ReferenceScope::ExplicitTwoStateWithExternalDefinedness)throw std::invalid_argument("Explicit reference definedness scope required");
}
SaturnTimingCut::~SaturnTimingCut()=default;
SaturnTimingCut::SaturnTimingCut(SaturnTimingCut&&)noexcept=default;
SaturnTimingCut&SaturnTimingCut::operator=(SaturnTimingCut&&)noexcept=default;
void SaturnTimingCut::evaluate(const ReferenceInputs&i){
 impl_->evaluated=false;
 auto fields=input_fields(impl_->profile);
 if(i.words.size()!=fields.size())throw std::invalid_argument("Incomplete/extra physical Saturn boundary");
 for(unsigned n=0;n<fields.size();n++)if(fields[n].word_width<64&&i.words[n]>=(1ULL<<fields[n].word_width))throw std::invalid_argument("Physical Saturn field exceeds source width");
'''
 for k,j in profiles.items():
  branch='impl_->profile==Profile::Compute128'if k=='compute'else'impl_->profile==Profile::Rocket256';source+='if('+branch+'){auto&m=*impl_->'+k+';m.clock=0;\n'
  for f in j['words']['input']:
   value='i.words['+str(f['word_index'])+']'
   if f['width']<=64:source+='m.'+f['name']+'='+value+';\n'
   else:
    source+='m.'+f['name']+'['+str(f['lo']//32)+']=std::uint32_t('+value+');\n'
    if f['word_width']>32:source+='m.'+f['name']+'['+str(f['lo']//32+1)+']=std::uint32_t('+value+'>>32);\n'
  source+='m.eval();}\n'
 source+='impl_->evaluated=true;\n}\nReferenceOutputs SaturnTimingCut::sample()const{\nif(!impl_->evaluated)throw std::logic_error("Saturn sample requires fresh evaluate");ReferenceOutputs o;o.words.resize(output_fields(impl_->profile).size());\n'
 for k,j in profiles.items():
  source+='if(impl_->profile==Profile::'+('Compute128'if k=='compute'else'Rocket256')+'){const auto&m=*impl_->'+k+';\n'
  for f in j['words']['output']:
   value='m.'+f['name']
   if f['width']>64:
    value='std::uint64_t{'+value+'['+str(f['lo']//32)+']}'
    if f['word_width']>32:value+='|(std::uint64_t{m.'+f['name']+'['+str(f['lo']//32+1)+']}<<32)'
   source+='o.words['+str(f['word_index'])+']='+value+';\n'
  source+='}\n'
 source+='''return o;
}
void SaturnTimingCut::commit(){
 if(!impl_->evaluated)throw std::logic_error("Saturn commit requires fresh evaluate");
 if(impl_->profile==Profile::Compute128){auto&m=*impl_->compute;m.clock=1;m.eval();m.clock=0;m.eval();}
 else{auto&m=*impl_->rocket;m.clock=1;m.eval();m.clock=0;m.eval();}
 ++impl_->edge_count;impl_->evaluated=false;
}
ReferenceOutputs SaturnTimingCut::step(const ReferenceInputs&i){evaluate(i);auto o=sample();commit();return o;}
std::uint64_t SaturnTimingCut::edges()const{return impl_->edge_count;}
Profile SaturnTimingCut::profile()const{return impl_->profile;}
unsigned SaturnTimingCut::hart()const{return impl_->hart;}
const char* SaturnTimingCut::source_identity(){return IRIS_SATURN_TIMING_SOURCE_ID;}
std::string_view SaturnTimingCut::source_clock_id(Profile p,unsigned h){
 if(p==Profile::Compute128&&h==0)return "sbusFixedClockNode.out2";
 if(p==Profile::Compute128&&h==1)return "sbusFixedClockNode.out3";
 if(p==Profile::Rocket256&&h==2)return "tileClockGroup.rockettile_2";
 throw std::invalid_argument("Hart/profile clock mismatch");
}
'''
 for direction in ['input','output']:
  source+='std::span<const Field> SaturnTimingCut::'+direction+'_fields(Profile p){\n'
  for k,j in profiles.items():source+='static constexpr Field '+k+'[]={'+','.join('{'+json.dumps(f['word_name'])+','+str(f['width'])+','+str(f['lo'])+','+str(f['word_width'])+'}'for f in j['words'][direction])+'};\n'
  source+='if(p==Profile::Compute128)return compute;if(p==Profile::Rocket256)return rocket;throw std::invalid_argument("Unknown source Saturn profile");}\n'
 source+='}\n';implementation=R/'timing/saturn_timing.cpp';implementation.write_text(source);api=R/'timing/saturn_timing.hpp';driver=R/'timing/saturn_timing_driver.cpp';identity_inputs=[implementation,api,driver,Path(__file__)]+[b/k/'build.json'for k in profiles]+[b/k/'ports.json'for k in profiles];identity=hashlib.sha256(json.dumps({str(p):sha(p)for p in identity_inputs},sort_keys=True).encode()).hexdigest();header=R/'timing/saturn_timing_identity.hpp';header.write_text('#pragma once\n#define IRIS_SATURN_TIMING_SOURCE_ID "'+identity+'"\n');tool=Path('/scratch/eygao/iris-cy/.conda-env');include=tool/'share/verilator/include';c=Path('/usr/bin/g++');ar=Path('/usr/bin/ar');commands=[];objects=[];common=['-O3','-std=c++20','-pthread','-I'+str(R/'timing'),'-I'+str(include),'-I'+str(include/'vltstd')]+['-I'+str(b/k/'model')for k in profiles]
 for file in [implementation,include/'verilated.cpp',include/'verilated_threads.cpp']:
  target=out/(file.stem+'.o');commands.append([str(c),*common,'-c',str(file),'-o',str(target)]);objects.append(target)
 for k,j in profiles.items():objects+=sorted((b/k/'model').glob(('VSaturnCompute'if k=='compute'else'VSaturnRocket')+'*.o'))
 library=sdk/'libiris_saturn_timing.a';commands.append([str(ar),'rcs',str(library),*map(str,objects)]);commands.append([str(c),*common,str(driver),str(library),'-latomic','-o',str(out/'saturn-timing')])
 with(out/'build.log').open('w')as log:
  for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 shutil.copy2(api,sdk/api.name);(out/'source').mkdir()
 for p in [implementation,api,driver,header,Path(__file__)]:shutil.copy2(p,out/'source'/p.name)
 inputs=identity_inputs+[header]+objects+[include/'verilated.cpp',include/'verilated_threads.cpp',c,ar];report={'schema':'iris.saturn_runtime_reference_sdk.v1','source_identity':identity,'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},'native_sha256':sha(out/'saturn-timing'),'library_sha256':sha(library),'public_flat_internal_state_exposed':False,'scope':'Explicit two-state full-runtime reference/integration cut; no implicit architectural initializedness or production timing qualification.','edge_API':'evaluate/sample/commit; exactly one supplied core edge, repeatable same-edge settling','hardware_contacted':False,'production_live_timing_certified':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source_identity':identity,'native_sha256':report['native_sha256'],'library_sha256':report['library_sha256']}))
if __name__=='__main__':main()
