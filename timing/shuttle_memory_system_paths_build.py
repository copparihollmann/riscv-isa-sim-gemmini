#!/usr/bin/env python3
"""Build exact saved memory width/CDC/coherence adapters into a port-only SDK."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
KINDS={'tile':('Tile','VShuttleMemoryTile'),'prci':('PRCI','VShuttleMemoryPRCI'),'uncore':('Uncore','VShuttleMemoryUncore')}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=6);a=p.parse_args();src=a.source.resolve();out=a.output.resolve()
 if out.exists():raise ValueError('fresh native build required')
 source=json.loads((src/'extraction.json').read_text())
 for name,h in source['extracted_files'].items():assert sha(src/'rtl'/name)==h,name
 out.mkdir();shutil.copytree(src/'rtl',out/'rtl');(out/'sdk').mkdir();shutil.copyfile(ROOT/'timing/shuttle_memory_system_paths.hpp',out/'sdk/shuttle_memory_system_paths.hpp')
 code='#include "shuttle_memory_system_paths.hpp"\n#include "shuttle_memory_system_paths_identity.hpp"\n#include "verilated.h"\n#include <stdexcept>\n#include <string>\n#include <utility>\n'
 code+=''.join('#include "'+prefix+'.h"\n'for _,prefix in KINDS.values())
 code+='namespace {struct Preserve{VerilatedContext*previous=Verilated::threadContextp();~Preserve(){Verilated::threadContextp(previous);}};struct Select{VerilatedContext*previous=Verilated::threadContextp();explicit Select(VerilatedContext*c){Verilated::threadContextp(c);}~Select(){Verilated::threadContextp(previous);}};template<class T,class...Args>std::unique_ptr<T>owned_make(Args&&...args){Preserve p;return std::make_unique<T>(std::forward<Args>(args)...);}}\nnamespace iris::shuttle_memory {\nstruct Paths::Impl {Path kind;std::unique_ptr<VerilatedContext>context;std::uint32_t tcm_known[2][2048]{};bool evaluated=false,reset_seen=false,evaluated_reset=false;std::uint64_t edges=0;\n'
 code+=''.join('std::unique_ptr<'+prefix+'>'+kind+';\n'for kind,(_,prefix)in KINDS.items())
 code+='Impl(Path kind_,std::uint32_t seed):kind(kind_),context(std::make_unique<VerilatedContext>()){context->threads(1);context->randReset(2);context->randSeed(seed);switch(kind){\n'
 for kind,(enum,prefix)in KINDS.items():code+='case Path::'+enum+':'+kind+'=std::make_unique<'+prefix+'>(context.get());'+kind+'->edge_clock=0;break;\n'
 code+='default:throw std::invalid_argument("unknown memory adapter");}}};\nPaths::Paths(Path kind,std::uint32_t seed):impl_(owned_make<Impl>(kind,seed)){}\nPaths::~Paths(){if(impl_){Preserve p;Verilated::threadContextp(impl_->context.get());impl_.reset();}}\nPath Paths::component()const{return impl_->kind;}\nstd::uint64_t Paths::edges()const{return impl_->edges;}\nconst char*Paths::source_identity(){return IRIS_SHUTTLE_MEMORY_PATHS_SOURCE_ID;}\n'
 evaluate=[];sample=[];commit=[];preflight=[];tables={'input':[],'output':[]}
 for kind,(enum,prefix)in KINDS.items():
  info=source['cuts'][kind];inputs=[x for x in info['physical_ports']if x['direction']=='input'];outputs=[x for x in info['physical_ports']if x['direction']=='output'];reset=next(x['index']for x in inputs if x['reset'])
  block='case Path::'+enum+':{auto&m=*impl_->'+kind+';\nif(in.size()!='+str(len(inputs))+')throw std::invalid_argument("adapter input count");\n'
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
  block='case Path::'+enum+':{const auto&m=*impl_->'+kind+';std::vector<Bits>out('+str(len(outputs))+');\n'
  for x in outputs:
   idx=str(x['index']);port=x['port']
   if x['width']<=64:block+='out['+idx+'].limbs[0]=m.'+port+';\n'
   else:
    for word in range((x['width']+31)//32):block+='out['+idx+'].limbs['+str(word//2)+']|=std::uint64_t(m.'+port+'['+str(word)+'])'+('<<32'if word%2 else'')+';\n'
  sample.append(block+'return out;}\n')
  mark='';after_mark=''
  if kind=='tile':
   guards='case Path::Tile:{const auto&m=*impl_->tile;if(!impl_->evaluated_reset){\n'
   for bank,instance in enumerate(['tcm','tcm_1']):
    observer={x['TCM_observer'][1]:x['port']for x in outputs if x.get('TCM_observer')and x['TCM_observer'][0]==instance}
    pins=lambda n:'m.'+observer['auto_in_'+n]
    valid=pins('a_valid')+'&&'+pins('a_ready');address=pins('a_bits_address');opcode=pins('a_bits_opcode');mask=pins('a_bits_mask')
    row='((('+address+'>>7)&0x3ff)<<1)|(('+address+'>>5)&1)'
    guards+='if('+valid+'){auto row='+row+';std::uint32_t mask='+mask+';auto opcode='+opcode+';if(opcode>4||!mask)throw std::runtime_error("IRIS_SHUTTLE_TCM_UNSUPPORTED_TRANSACTION");if((opcode==2||opcode==3||opcode==4)&&(impl_->tcm_known['+str(bank)+'][row]&mask)!=mask)throw std::runtime_error("IRIS_SHUTTLE_TCM_UNDEFINED_READ bank='+str(bank)+' row="+std::to_string(row));}\n'
    mark+='const auto write_row_'+str(bank)+'='+row+';const std::uint32_t write_mask_'+str(bank)+'=(!impl_->evaluated_reset&&'+valid+'&&'+opcode+'<=1)?std::uint32_t('+mask+'):0;\n'
    after_mark+='impl_->tcm_known['+str(bank)+'][write_row_'+str(bank)+']|=write_mask_'+str(bank)+';\n'
   preflight.append(guards+'}break;}\n')
  else:preflight.append('case Path::'+enum+':break;\n')
  commit.append('case Path::'+enum+':{auto&m=*impl_->'+kind+';'+mark+'m.edge_clock=1;m.eval();m.edge_clock=0;m.eval();'+after_mark+'break;}\n')
  for direction,fields in [('input',inputs),('output',outputs)]:tables[direction].append('case Path::'+enum+':{static constexpr Field fields[]={'+','.join('{'+json.dumps(x['name'])+','+str(x['width'])+'}'for x in fields)+'};return fields;}\n')
 code+='void Paths::evaluate(std::span<const Bits>in){Select owner(impl_->context.get());impl_->evaluated=false;switch(impl_->kind){'+''.join(evaluate)+'}impl_->evaluated=true;}\n'
 code+='std::vector<Bits>Paths::sample()const{if(!impl_->evaluated)throw std::logic_error("adapter sample requires current edge");switch(impl_->kind){'+''.join(sample)+'}throw std::logic_error("bad adapter");}\n'
 code+='void Paths::validate_commit()const{if(!impl_->evaluated)throw std::logic_error("adapter commit requires fresh evaluation");switch(impl_->kind){'+''.join(preflight)+'}}\n'
 code+='void Paths::commit(){Select owner(impl_->context.get());try{validate_commit();}catch(...){impl_->evaluated=false;throw;}switch(impl_->kind){'+''.join(commit)+'}++impl_->edges;impl_->reset_seen|=impl_->evaluated_reset;impl_->evaluated=false;}\n'
 for direction in ['input','output']:code+='std::span<const Field>Paths::'+direction+'_fields()const{switch(impl_->kind){'+''.join(tables[direction])+'}throw std::logic_error("bad adapter");}\n'
 code+='}\n';generated=out/'shuttle_memory_system_paths.generated.cpp';generated.write_text(code)
 runtime=TOOL.parent.parent/'share/verilator/include';inputs=[Path(__file__),src/'extraction.json',ROOT/'timing/shuttle_memory_system_paths.hpp',TOOL,TOOL.with_name('verilator_bin'),TOOL.with_name('perl'),Path('/usr/bin/g++'),Path('/usr/bin/ar')]+sorted(runtime.rglob('*.h'))+[runtime/(n+'.cpp')for n in ['verilated','verilated_threads','verilated_save']]
 identity=hashlib.sha256(json.dumps({'inputs':{str(p):sha(p)for p in inputs},'generated_cpp_sha256':sha(generated),'contract':'actual source adapters; explicit local clock; evaluate/sample/commit; no service inference'},sort_keys=True).encode()).hexdigest();(out/'sdk/shuttle_memory_system_paths_identity.hpp').write_text('#pragma once\n#define IRIS_SHUTTLE_MEMORY_PATHS_SOURCE_ID "'+identity+'"\n')
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
  cmds.append(['/usr/bin/ar','rcs',str(out/'sdk/libiris_shuttle_memory_paths.a'),str(out/'adapters.o'),*[str(out/(name+'.o'))for name in ['verilated','verilated_threads','verilated_save']],*map(str,objects)])
  for i,cmd in enumerate(cmds):
   status=run(cmd,out/('sdk-'+str(i)+'.build.log'))
   if status:break
 result={'schema':'iris.shuttle_memory_paths_sdk_build.v1','source_identity':identity,'argv':commands,'exit_status':status,'host_seconds':time.monotonic()-begin,'input_sha256':{str(p):sha(p)for p in inputs},'source_sha256':{str(p):sha(p)for p in sorted((out/'rtl').iterdir())},'generated_cpp_sha256':sha(generated),'added_clock_edges':0,'external_service_inferred':False,'public_internal_state_access':False,'hardware_contacted':False,'timing_certified':False}
 if not status:result['library_sha256']=sha(out/'sdk/libiris_shuttle_memory_paths.a')
 (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'exit_status':status,'source_identity':identity,'host_seconds':result['host_seconds'],'library_sha256':result.get('library_sha256')}))
 if status:raise SystemExit(status)
if __name__=='__main__':main()
