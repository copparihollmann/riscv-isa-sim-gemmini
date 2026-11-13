#!/usr/bin/env python3
"""Compose both exact Shuttle paths and guarded caches with the frozen System."""
import argparse,hashlib,json,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--graph',type=Path,required=True);p.add_argument('--paths',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--parent',type=Path,default=R/'build/serial-memory-system-native-v2');p.add_argument('--cache',type=Path,default=R/'build/memory-fabric-context-sdk-v2/cache');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh composition required')
 g=json.loads(a.graph.read_text());pb=a.paths.resolve();base=a.parent.resolve();br=json.loads((base/'build.json').read_text());cache=a.cache.resolve();out.mkdir();(out/'sdk').mkdir();shutil.copy2(R/'timing/shuttle_memory_system.hpp',out/'sdk/shuttle_memory_system.hpp')
 includes=[out/'sdk',pb/'sdk',*[Path(x)for x in br['required_include_directories']],base/'sdk']
 libs=[pb/'sdk/libiris_shuttle_memory_paths.a',base/'sdk/libiris_serial_memory_system.a',*[Path(x)for x in br['required_static_libraries_in_link_order']]]
 # Parent build records its own library in the link order; use it once only.
 libs=list(dict.fromkeys(libs))
 nets={}
 def gather(e):
  if e['op']=='net':
   if e['name']in nets:assert nets[e['name']]==e['width']
   nets[e['name']]=e['width']
  elif e['op']=='slice':gather(e['value'])
  elif e['op']=='concat':
   for x in e['values']:gather(x)
  elif e['op']not in ['literal','unconnected']:raise ValueError(e)
 for c in g['components'].values():
  for f in c['physical_ports']:gather(f['global'])
 names=sorted(nets);idx={n:i for i,n in enumerate(names)};producers={}
 for cn,c in g['components'].items():
  for f in c['physical_ports']:
   e=f['global']
   if f['direction']=='output'and e['op']=='net':producers.setdefault(e['name'],(cn,f['index']))
 external=sorted(set(nets)-producers.keys());extidx={n:i for i,n in enumerate(external)};outputs=[(cn,f)for cn,c in g['components'].items()for f in c['physical_ports']if f['direction']=='output'];oidx={(cn,f['name']):i for i,(cn,f)in enumerate(outputs)}
 def expr(e):
  if e['op']=='net':return 'wire['+str(idx[e['name']])+']'
  if e['op']=='slice':return 'slice('+expr(e['value'])+','+str(e['low'])+','+str(e['width'])+')'
  if e['op']=='literal':return 'Bits('+str(e['value'])+'ULL)'
  if e['op']=='concat':
   value='Bits{}'
   for x in e['values']:value='append('+value+','+expr(x)+','+str(x['width'])+')'
   return value
  raise ValueError(e)
 def table(fs):return ','.join('{'+json.dumps(n)+','+str(w)+'}'for n,w in fs)
 code='''#include "shuttle_memory_system.hpp"
#include "shuttle_memory_system_paths.hpp"
#include "cache_hierarchy.hpp"
#include <stdexcept>
#include <string>
namespace iris::shuttle_system {
static Bits slice(const Bits&v,unsigned lo,unsigned width){Bits out;for(unsigned b=0;b<width;++b)if((v.limbs[(lo+b)/64]>>((lo+b)%64))&1)out.limbs[b/64]|=1ULL<<(b%64);return out;}
static Bits append(const Bits&hi,const Bits&lo,unsigned width){Bits out=lo;for(unsigned b=0;b+width<256;++b)if((hi.limbs[b/64]>>(b%64))&1)out.limbs[(b+width)/64]|=1ULL<<((b+width)%64);return out;}
static Bits known(unsigned width){Bits out;for(unsigned b=0;b<width;++b)out.limbs[b/64]|=1ULL<<(b%64);return out;}
struct System::Impl {
 memory_system::System system;
 cache::Model shuttle0_cache,shuttle1_cache;
 shuttle_memory::Paths shuttle0_tile,shuttle0_prci,shuttle0_uncore,shuttle1_tile,shuttle1_prci,shuttle1_uncore;
 bool evaluated=false;unsigned iterations=0;
'''
 code+='std::vector<Bits>wire=std::vector<Bits>('+str(len(names))+'),observed=std::vector<Bits>('+str(len(outputs))+');\n'
 code+='Impl(unsigned seed,const std::vector<std::string>&args,serial_memory::AssertionPolicy policy):system(seed,args,policy),shuttle0_cache(cache::Component::ShuttleL1D,seed+11),shuttle1_cache(cache::Component::ShuttleL1D,seed+19),'
 code+=','.join('shuttle'+str(h)+'_'+k+'(shuttle_memory::Path::'+v+',seed+'+str(31+h*7)+')'for h in range(2)for k,v in [('tile','Tile'),('prci','PRCI'),('uncore','Uncore')])+'{\n'
 for owner,identity in [('memory_system::System',br['source_identity']),('shuttle_memory::Paths',json.loads((pb/'build.json').read_text())['source_identity']),('cache::Model',json.loads((cache/'build.json').read_text())['source_identity'])]:code+='if(std::string('+owner+'::source_identity())!='+json.dumps(identity)+')throw std::runtime_error("IRIS_SHUTTLE_SYSTEM_IDENTITY_MISMATCH");\n'
 for cn,c in g['components'].items():
  for direction in ['input','output']:
   fs=[f for f in c['physical_ports']if f['direction']==direction];code+='{auto fields='+cn+'.'+direction+'_fields();if(fields.size()!='+str(len(fs))+')throw std::runtime_error("IRIS_SHUTTLE_SYSTEM_SCHEMA_COUNT");\n'
   for f in fs:code+='if(fields['+str(f['index'])+'].name!='+json.dumps(f['name'])+'||fields['+str(f['index'])+'].width!='+str(f['width'])+')throw std::runtime_error("IRIS_SHUTTLE_SYSTEM_SCHEMA_FIELD");\n'
   code+='}\n'
 code+='}\n};\nSystem::System(unsigned seed,std::vector<std::string>args,serial_memory::AssertionPolicy p):impl_(std::make_unique<Impl>(seed,args,p)){}\nSystem::~System()=default;\n'
 code+='std::span<const Field>System::input_fields(){static constexpr Field f[]={'+table([(n,nets[n])for n in external])+'};return f;}\n'
 code+='std::span<const Field>System::output_fields(){static constexpr Field f[]={'+table([(cn+"::"+f['name'],f['width'])for cn,f in outputs])+'};return f;}\n'
 code+='unsigned System::external_input_index(std::string_view c,std::string_view n){\n'
 for cn,c in g['components'].items():
  for f in c['physical_ports']:
   e=f['global']
   if f['direction']=='input'and e['op']=='net'and e['name']in extidx:code+='if(c=='+json.dumps(cn)+'&&n=='+json.dumps(f['name'])+')return '+str(extidx[e['name']])+';\n'
 code+='throw std::invalid_argument("IRIS_SHUTTLE_SYSTEM_JOINED_OR_UNKNOWN_INPUT");}\n'
 code+='unsigned System::output_index(std::string_view c,std::string_view n){\n'
 for cn,f in outputs:code+='if(c=='+json.dumps(cn)+'&&n=='+json.dumps(f['name'])+')return '+str(oidx[cn,f['name']])+';\n'
 code+='throw std::invalid_argument("IRIS_SHUTTLE_SYSTEM_UNKNOWN_OUTPUT");}\nunsigned System::last_settle_iterations()const{return impl_->iterations;}\nbool System::concretized_unknown_replay_timing()const{return impl_->shuttle0_cache.concretized_unknown_replay_timing()||impl_->shuttle1_cache.concretized_unknown_replay_timing();}\n'
 code+='void System::evaluate(std::span<const Input>in){impl_->evaluated=false;auto fields=input_fields();if(in.size()!=fields.size())throw std::invalid_argument("IRIS_SHUTTLE_SYSTEM_INPUT_COUNT");auto&wire=impl_->wire;for(unsigned i=0;i<in.size();++i){auto mask=known(fields[i].width);for(unsigned j=0;j<4;++j){if((in[i].known.limbs[j]&mask.limbs[j])!=mask.limbs[j])throw std::runtime_error("IRIS_SHUTTLE_SYSTEM_UNKNOWN_INPUT "+std::string(fields[i].name));if((in[i].value.limbs[j]|in[i].known.limbs[j])&~mask.limbs[j])throw std::invalid_argument("IRIS_SHUTTLE_SYSTEM_INPUT_WIDTH "+std::string(fields[i].name));}}\n'
 for n in external:code+='wire['+str(idx[n])+']=in['+str(extidx[n])+'].value;\n'
 code+='for(unsigned iteration=0;iteration<128;++iteration){auto previous=wire;\n'
 for cn,c in g['components'].items():
  fs=[f for f in c['physical_ports']if f['direction']=='input'];ofs=[f for f in c['physical_ports']if f['direction']=='output'];ty='Input'if cn=='system'else'cache::Bits'if cn.endswith('_cache')else'shuttle_memory::Bits';code+='{std::vector<'+ty+'>pins('+str(len(fs))+');\n'
  for f in fs:
   target='pins['+str(f['index'])+']';v=expr(f['global'])
   if cn=='system':code+=target+'={'+v+',known('+str(f['width'])+')};\n'
   else:code+=target+'.limbs='+v+'.limbs;\n'
  code+='impl_->'+cn+'.evaluate(pins);auto result=impl_->'+cn+'.sample();\n'
  for f in ofs:
   v='result['+str(f['index'])+'].limbs';code+='impl_->observed['+str(oidx[cn,f['name']])+'].limbs='+v+';\n';e=f['global']
   if e['op']=='net'and producers[e['name']]==(cn,f['index']):code+='wire['+str(idx[e['name']])+'].limbs='+v+';\n'
  code+='}\n'
 code+='impl_->iterations=iteration+1;if(wire==previous){impl_->evaluated=true;return;}}throw std::runtime_error("IRIS_SHUTTLE_SYSTEM_NO_FIXED_POINT");}\nstd::vector<Bits>System::sample()const{if(!impl_->evaluated)throw std::logic_error("IRIS_SHUTTLE_SYSTEM_SAMPLE_WITHOUT_EVAL");return impl_->observed;}\n'
 code+='void System::commit(ClockEdges e){if(!impl_->evaluated)throw std::logic_error("IRIS_SHUTTLE_SYSTEM_COMMIT_WITHOUT_EVAL");impl_->evaluated=false;if(!e.rocket&&!e.uncore&&!e.bringup&&!e.serial)throw std::invalid_argument("IRIS_SHUTTLE_SYSTEM_NO_CLOCK_EDGE");if(e.uncore){impl_->shuttle0_tile.validate_commit();impl_->shuttle1_tile.validate_commit();}impl_->system.commit(e);if(e.uncore){'
 code+=''.join('impl_->shuttle'+str(h)+'_'+k+'.commit();'for h in range(2)for k in ['cache','tile','prci','uncore'])+'}}\n'
 inputs=[Path(__file__),R/'timing/shuttle_memory_system.hpp',a.graph,pb/'build.json',base/'build.json',cache/'build.json',Path('/usr/bin/g++'),Path('/usr/bin/ar')]+[p for d in includes for p in d.glob('*.hpp')]+libs;identity=hashlib.sha256(json.dumps({'inputs':{str(p):sha(p)for p in inputs},'generated_body_sha256':hashlib.sha256(code.encode()).hexdigest(),'clock_contract':'both Shuttle memory tiles synchronous uncore; simultaneous preedge samples across all peers, no service inferred'},sort_keys=True).encode()).hexdigest();code+='const char*System::source_identity(){return "'+identity+'";}\n}\n';cpp=out/'shuttle_memory_system.generated.cpp';cpp.write_text(code)
 cmd=['/usr/bin/g++','-O3','-std=c++20',*['-I'+str(d)for d in includes],'-c',str(cpp),'-o',str(out/'system.o')];commands=[cmd];begin=time.monotonic()
 with(out/'compile.stdout').open('w')as stdout,(out/'compile.stderr').open('w')as stderr:status=subprocess.run(cmd,stdout=stdout,stderr=stderr).returncode
 if not status:
  cmd=['/usr/bin/ar','rcs',str(out/'sdk/libiris_shuttle_memory_system.a'),str(out/'system.o')];commands.append(cmd);status=subprocess.run(cmd).returncode
 report={'schema':'iris.shuttle_memory_system_build.v1','exit_status':status,'source_identity':identity,'input_sha256':{str(p):sha(p)for p in inputs},'generated_cpp_sha256':sha(cpp),'argv':commands,'required_static_libraries_in_link_order':[str(out/'sdk/libiris_shuttle_memory_system.a'),*map(str,libs)],'required_include_directories':list(map(str,includes)),'input_count':len(external),'output_count':len(outputs),'host_seconds':time.monotonic()-begin,'default_unreset_replay_policy':'RefuseUse','all_external_input_bits_require_knownness':True,'full_internal_knownness_certified':False,'hardware_contacted':False,'timing_certified':False,'calibration_usable':False}
 if not status:report['library_sha256']=sha(out/'sdk/libiris_shuttle_memory_system.a')
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k]for k in ['exit_status','source_identity','input_count','output_count']}))
 if status:raise SystemExit(status)
if __name__=='__main__':main()
