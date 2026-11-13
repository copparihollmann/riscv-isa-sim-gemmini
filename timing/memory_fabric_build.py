#!/usr/bin/env python3
"""Build exact saved memory width/CDC/coherence adapters into a port-only SDK."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
KINDS={'rocket_tile':('RocketTile','VFabricRocketTile'),'rocket_source':('RocketClockSource','VFabricRocketSource'),'rocket_sink':('RocketClockSink','VFabricRocketSink'),'manager':('CoherenceManager','VFabricManager')}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=ROOT/'build/memory-fabric-adapters-source-v1');p.add_argument('--output',type=Path,default=ROOT/'build/memory-fabric-adapters-native-v1');p.add_argument('--jobs',type=int,default=6);a=p.parse_args();src=a.source.resolve();out=a.output.resolve()
 if out.exists():raise ValueError('fresh native build required')
 source=json.loads((src/'extraction.json').read_text())
 for name,h in source['extracted_files'].items():assert sha(src/'rtl'/name)==h,name
 out.mkdir();shutil.copytree(src/'rtl',out/'rtl');(out/'sdk').mkdir();shutil.copyfile(ROOT/'timing/memory_fabric_adapters.hpp',out/'sdk/memory_fabric_adapters.hpp')
 code='#include "memory_fabric_adapters.hpp"\n#include "memory_fabric_identity.hpp"\n#include "verilated.h"\n#include <stdexcept>\n#include <string>\n'
 code+=''.join('#include "'+prefix+'.h"\n'for _,prefix in KINDS.values())
 code+='namespace iris::fabric {\nstruct Adapters::Impl {Adapter kind;std::unique_ptr<VerilatedContext>context;bool evaluated=false,reset_seen=false,evaluated_reset=false;std::uint64_t edges=0;\n'
 code+=''.join('std::unique_ptr<'+prefix+'>'+kind+';\n'for kind,(_,prefix)in KINDS.items())
 code+='Impl(Adapter kind_,std::uint32_t seed):kind(kind_),context(std::make_unique<VerilatedContext>()){context->randReset(2);context->randSeed(seed);switch(kind){\n'
 for kind,(enum,prefix)in KINDS.items():code+='case Adapter::'+enum+':'+kind+'=std::make_unique<'+prefix+'>(context.get());'+kind+'->edge_clock=0;break;\n'
 code+='default:throw std::invalid_argument("unknown memory adapter");}}};\nAdapters::Adapters(Adapter kind,std::uint32_t seed):impl_(std::make_unique<Impl>(kind,seed)){}\nAdapters::~Adapters()=default;\nAdapter Adapters::component()const{return impl_->kind;}\nstd::uint64_t Adapters::edges()const{return impl_->edges;}\nconst char*Adapters::source_identity(){return IRIS_MEMORY_FABRIC_SOURCE_ID;}\n'
 evaluate=[];sample=[];commit=[];tables={'input':[],'output':[]}
 for kind,(enum,prefix)in KINDS.items():
  info=source['cuts'][kind];inputs=[x for x in info['physical_ports']if x['direction']=='input'];outputs=[x for x in info['physical_ports']if x['direction']=='output'];reset=next(x['index']for x in inputs if x['reset'])
  block='case Adapter::'+enum+':{auto&m=*impl_->'+kind+';\nif(in.size()!='+str(len(inputs))+')throw std::invalid_argument("adapter input count");\n'
  for x in inputs:
   idx=str(x['index']);words=(x['width']+63)//64;tail=x['width']%64
   for limb in range(words,4):block+='if(in['+idx+'].limbs['+str(limb)+'])throw std::invalid_argument("adapter input width: '+x['name']+'");\n'
   if tail:block+='if(in['+idx+'].limbs['+str(words-1)+']>='+str(1<<tail)+'ULL)throw std::invalid_argument("adapter input width: '+x['name']+'");\n'
  block+='if(!impl_->reset_seen&&!in['+str(reset)+'].limbs[0])throw std::logic_error("adapter requires explicitly committed reset");\nimpl_->evaluated_reset=in['+str(reset)+'].limbs[0];\n'
  for x in inputs:
   idx=str(x['index']);port=x['port']
   if x['width']<=64:block+='m.'+port+'=in['+idx+'].limbs[0];\n'
   else:
    for word in range((x['width']+31)//32):block+='m.'+port+'['+str(word)+']=in['+idx+'].limbs['+str(word//2)+']'+('>>32'if word%2 else'')+';\n'
  evaluate.append(block+'m.eval();break;}\n')
  block='case Adapter::'+enum+':{const auto&m=*impl_->'+kind+';std::vector<Bits>out('+str(len(outputs))+');\n'
  for x in outputs:
   idx=str(x['index']);port=x['port']
   if x['width']<=64:block+='out['+idx+'].limbs[0]=m.'+port+';\n'
   else:
    for word in range((x['width']+31)//32):block+='out['+idx+'].limbs['+str(word//2)+']|=std::uint64_t(m.'+port+'['+str(word)+'])'+('<<32'if word%2 else'')+';\n'
  sample.append(block+'return out;}\n')
  commit.append('case Adapter::'+enum+':{auto&m=*impl_->'+kind+';m.edge_clock=1;m.eval();m.edge_clock=0;m.eval();break;}\n')
  for direction,fields in [('input',inputs),('output',outputs)]:tables[direction].append('case Adapter::'+enum+':{static constexpr Field fields[]={'+','.join('{'+json.dumps(x['name'])+','+str(x['width'])+'}'for x in fields)+'};return fields;}\n')
 code+='void Adapters::evaluate(std::span<const Bits>in){impl_->evaluated=false;switch(impl_->kind){'+''.join(evaluate)+'}impl_->evaluated=true;}\n'
 code+='std::vector<Bits>Adapters::sample()const{if(!impl_->evaluated)throw std::logic_error("adapter sample requires current edge");switch(impl_->kind){'+''.join(sample)+'}throw std::logic_error("bad adapter");}\n'
 code+='void Adapters::commit(){if(!impl_->evaluated)throw std::logic_error("adapter commit requires fresh evaluation");switch(impl_->kind){'+''.join(commit)+'}++impl_->edges;impl_->reset_seen|=impl_->evaluated_reset;impl_->evaluated=false;}\n'
 for direction in ['input','output']:code+='std::span<const Field>Adapters::'+direction+'_fields()const{switch(impl_->kind){'+''.join(tables[direction])+'}throw std::logic_error("bad adapter");}\n'
 code+='std::vector<Bits>Adapters::step(std::span<const Bits>in){evaluate(in);auto out=sample();commit();return out;}\n}\n';generated=out/'memory_fabric_adapters.generated.cpp';generated.write_text(code)
 runtime=TOOL.parent.parent/'share/verilator/include';inputs=[Path(__file__),src/'extraction.json',ROOT/'timing/memory_fabric_adapters.hpp',TOOL,TOOL.with_name('verilator_bin'),TOOL.with_name('perl'),Path('/usr/bin/g++'),Path('/usr/bin/ar')]+sorted(runtime.rglob('*.h'))+[runtime/(n+'.cpp')for n in ['verilated','verilated_threads','verilated_save']]
 identity=hashlib.sha256(json.dumps({'inputs':{str(p):sha(p)for p in inputs},'generated_cpp_sha256':sha(generated),'contract':'actual source adapters; explicit local clock; evaluate/sample/commit; no service inference'},sort_keys=True).encode()).hexdigest();(out/'sdk/memory_fabric_identity.hpp').write_text('#pragma once\n#define IRIS_MEMORY_FABRIC_SOURCE_ID "'+identity+'"\n')
 env=dict(os.environ,PATH=str(TOOL.parent)+os.pathsep+os.environ['PATH']);commands=[];begin=time.monotonic();status=0
 def run(argv,log):
  commands.append(argv)
  with log.open('w')as f:return subprocess.run(argv,env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 for kind,(enum,prefix)in KINDS.items():
  model=out/kind;model.mkdir();top=source['cuts'][kind]['top']
  cmd=[str(TOOL.with_name('perl')),str(TOOL),'--cc','--build','-j',str(a.jobs),'--top-module',top,'--prefix',prefix,'--assert','--savable','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(model),'-I'+str(out/'rtl'),'-y',str(out/'rtl'),'+libext+.sv+.v','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT','+define+RANDOMIZE_GARBAGE_ASSIGN','+define+RANDOMIZE_INVALID_ASSIGN',str(out/'rtl'/(top+'.sv')),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3']
  status=run(cmd,out/(kind+'.build.log'))
  if status:break
 if not status:
  inc=['-I'+str(out/'sdk'),'-I'+str(runtime)]+['-I'+str(out/k)for k in KINDS]
  cmds=[['/usr/bin/g++','-O3','-std=c++20',*inc,'-c',str(generated),'-o',str(out/'adapters.o')]]
  for name in ['verilated','verilated_threads','verilated_save']:cmds.append(['/usr/bin/g++','-O3','-std=c++20',*inc,'-c',str(runtime/(name+'.cpp')),'-o',str(out/(name+'.o'))])
  objects=[p for k,(_,prefix)in KINDS.items()for p in sorted((out/k).glob(prefix+'*.o'))]
  cmds.append(['/usr/bin/ar','rcs',str(out/'sdk/libiris_memory_adapters.a'),str(out/'adapters.o'),*[str(out/(name+'.o'))for name in ['verilated','verilated_threads','verilated_save']],*map(str,objects)])
  for i,cmd in enumerate(cmds):
   status=run(cmd,out/('sdk-'+str(i)+'.build.log'))
   if status:break
 result={'schema':'iris.memory_fabric_adapters_sdk_build.v1','source_identity':identity,'argv':commands,'exit_status':status,'host_seconds':time.monotonic()-begin,'input_sha256':{str(p):sha(p)for p in inputs},'source_sha256':{str(p):sha(p)for p in sorted((out/'rtl').iterdir())},'generated_cpp_sha256':sha(generated),'added_clock_edges':0,'external_service_inferred':False,'public_internal_state_access':False,'hardware_contacted':False,'timing_certified':False}
 if not status:result['library_sha256']=sha(out/'sdk/libiris_memory_adapters.a')
 (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'exit_status':status,'source_identity':identity,'host_seconds':result['host_seconds'],'library_sha256':result.get('library_sha256')}))
 if status:raise SystemExit(status)
if __name__=='__main__':main()
