#!/usr/bin/env python3
"""Generate same-edge source-net coupling of frozen cache/NoC/adaptor SDKs."""
import argparse,hashlib,json,subprocess,time,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--graph',type=Path,default=R/'build/memory-fabric-graph-v1/graph.json');p.add_argument('--adapters',type=Path,default=R/'build/memory-fabric-adapters-native-v2');p.add_argument('--cache',type=Path,default=R/'build/cache-hierarchy-native-v5');p.add_argument('--noc',type=Path,default=R/'build/noc-network-sdk-v1');p.add_argument('--output',type=Path,default=R/'build/memory-fabric-coupled-native-v1');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh composite output required')
 g=json.loads(a.graph.read_text());ad=a.adapters.resolve();cache=a.cache.resolve();noc=a.noc.resolve();sdk=[cache/'sdk',noc/'sdk',ad/'sdk'];libs=[cache/'sdk/libiris_cache_hierarchy.a',noc/'sdk/libiris_noc.a',ad/'sdk/libiris_memory_adapters.a']
 out.mkdir();(out/'sdk').mkdir();shutil.copyfile(R/'timing/memory_fabric.hpp',out/'sdk/memory_fabric.hpp');shutil.copyfile(R/'timing/memory_fabric_adapters.hpp',out/'sdk/memory_fabric_adapters.hpp')
 components=list(g['components']);cindex={n:i for i,n in enumerate(components)};nets={}
 def gather(e):
  if e['op']=='net':
   if e['name']in nets:assert nets[e['name']]==e['width']
   nets[e['name']]=e['width']
  elif e['op']=='slice':gather(e['value'])
  elif e['op']=='concat':
   for v in e['values']:gather(v)
  elif e['op']not in ['literal','unconnected']:raise ValueError(e)
 for c in g['components'].values():
  for f in c['physical_ports']:gather(f['global'])
 names=sorted(nets);idx={n:i for i,n in enumerate(names)};producers={}
 for cn,c in g['components'].items():
  for f in c['physical_ports']:
   if f['direction']=='output'and f['global']['op']=='net':
    n=f['global']['name'];assert n not in producers;producers[n]=(cn,f['index'])
 external=sorted(n for n in nets if n not in producers);extidx={n:i for i,n in enumerate(external)};outputs=[(cn,f)for cn,c in g['components'].items()for f in c['physical_ports']if f['direction']=='output'];outputidx={(cn,f['name']):i for i,(cn,f)in enumerate(outputs)}
 def expression(e):
  if e['op']=='net':return 'wire['+str(idx[e['name']])+']'
  if e['op']=='slice':return 'slice('+expression(e['value'])+','+str(e['low'])+','+str(e['width'])+')'
  if e['op']=='literal':return 'Bits('+str(e['value'])+'ULL)'
  raise ValueError(e)
 def table(fields):return ','.join('{'+json.dumps(n)+','+str(w)+'}'for n,w in fields)
 code='''#include "memory_fabric.hpp"
#include "cache_hierarchy.hpp"
#include "noc_network.hpp"
#include <algorithm>
#include <stdexcept>
#include <string>
namespace iris::fabric {
static Bits slice(const Bits&in,unsigned lo,unsigned width){Bits out;for(unsigned bit=0;bit<width;++bit)if((in.limbs[(lo+bit)/64]>>((lo+bit)%64))&1)out.limbs[bit/64]|=std::uint64_t(1)<<(bit%64);return out;}
static bool fits(const Bits&x,unsigned width){for(unsigned bit=width;bit<256;++bit)if((x.limbs[bit/64]>>(bit%64))&1)return false;return true;}
static bool fully_known(const Bits&x,unsigned width){for(unsigned bit=0;bit<width;++bit)if(!((x.limbs[bit/64]>>(bit%64))&1))return false;return fits(x,width);}
struct MemoryFabric::Impl {
 cache::Model rocket{cache::Component::RocketL1D,1};
 cache::Model l2{cache::Component::InclusiveL2,1};
 noc::IrisNoCNetwork noc_model{1};
 Adapters rocket_tile{Adapter::RocketTile,1},rocket_source{Adapter::RocketClockSource,1},rocket_sink{Adapter::RocketClockSink,1},manager{Adapter::CoherenceManager,1};
 bool evaluated=false;unsigned iterations=0;std::uint64_t rocket_edge_count=0,uncore_edge_count=0;
'''
 # Construction uses explicit same seed per independently isolated source model.
 code=code.replace('cache::Model rocket{cache::Component::RocketL1D,1};','cache::Model rocket;').replace('cache::Model l2{cache::Component::InclusiveL2,1};','cache::Model l2;').replace('noc::IrisNoCNetwork noc_model{1};','noc::IrisNoCNetwork noc_model;').replace('Adapters rocket_tile{Adapter::RocketTile,1},rocket_source{Adapter::RocketClockSource,1},rocket_sink{Adapter::RocketClockSink,1},manager{Adapter::CoherenceManager,1};','Adapters rocket_tile,rocket_source,rocket_sink,manager;')
 code+='std::vector<Bits>wire=std::vector<Bits>('+str(len(names))+'),observed=std::vector<Bits>('+str(len(outputs))+');\n'
 constructor='Impl(unsigned seed):rocket(cache::Component::RocketL1D,seed),l2(cache::Component::InclusiveL2,seed),noc_model(seed),rocket_tile(Adapter::RocketTile,seed),rocket_source(Adapter::RocketClockSource,seed),rocket_sink(Adapter::RocketClockSink,seed),manager(Adapter::CoherenceManager,seed){\n'
 for build,owner in [(cache,'cache::Model'),(noc,'noc::IrisNoCNetwork'),(ad,'Adapters')]:
  expected=json.loads((build/'build.json').read_text())['source_identity'];constructor+='if(std::string('+owner+'::source_identity())!='+json.dumps(expected)+')throw std::runtime_error("IRIS_MEMORY_FABRIC_SDK_IDENTITY_MISMATCH");\n'
 owner_members={'rocket_cache':'rocket','l2':'l2','noc':'noc_model','rocket_tile':'rocket_tile','rocket_source':'rocket_source','rocket_sink':'rocket_sink','manager':'manager'}
 for cn,c in g['components'].items():
  for direction in ['input','output']:
   fields=[f for f in c['physical_ports']if f['direction']==direction];constructor+='{auto fields='+owner_members[cn]+'.'+direction+'_fields();if(fields.size()!='+str(len(fields))+')throw std::runtime_error("IRIS_MEMORY_FABRIC_SCHEMA_COUNT_MISMATCH");\n'
   for f in fields:constructor+='if(fields['+str(f['index'])+'].name!='+json.dumps(f['name'])+'||fields['+str(f['index'])+'].width!='+str(f['width'])+')throw std::runtime_error("IRIS_MEMORY_FABRIC_SCHEMA_FIELD_MISMATCH");\n'
   constructor+='}\n'
 code+=constructor+'}\n};\n'
 code+='MemoryFabric::MemoryFabric(std::uint32_t seed):impl_(std::make_unique<Impl>(seed)){}\nMemoryFabric::~MemoryFabric()=default;\nstd::uint64_t MemoryFabric::rocket_edges()const{return impl_->rocket_edge_count;}\nstd::uint64_t MemoryFabric::uncore_edges()const{return impl_->uncore_edge_count;}\nunsigned MemoryFabric::last_settle_iterations()const{return impl_->iterations;}\n'
 code+='std::span<const Field>MemoryFabric::input_fields(){static constexpr Field f[]={'+table([(n,nets[n])for n in external])+'};return f;}\n'
 code+='std::span<const Field>MemoryFabric::output_fields(){static constexpr Field f[]={'+table([(cn+"::"+f['name'],f['width'])for cn,f in outputs])+'};return f;}\n'
 code+='unsigned MemoryFabric::external_input_index(std::string_view component,std::string_view name){\n'
 for cn,c in g['components'].items():
  for f in c['physical_ports']:
   e=f['global']
   if f['direction']=='input'and e['op']=='net'and e['name']in extidx:code+='if(component=='+json.dumps(cn)+'&&name=='+json.dumps(f['name'])+')return '+str(extidx[e['name']])+';\n'
 code+='throw std::invalid_argument("field is unknown or internally joined; external drive forbidden");}\n'
 code+='unsigned MemoryFabric::output_index(std::string_view component,std::string_view name){\n'
 for cn,f in outputs:code+='if(component=='+json.dumps(cn)+'&&name=='+json.dumps(f['name'])+')return '+str(outputidx[cn,f['name']])+';\n'
 code+='throw std::invalid_argument("unknown source output");}\n'
 code+='void MemoryFabric::evaluate(std::span<const Input>in){impl_->evaluated=false;impl_->iterations=0;const auto fields=input_fields();if(in.size()!=fields.size())throw std::invalid_argument("memory fabric external input count");for(unsigned i=0;i<in.size();++i){if(!fits(in[i].value,fields[i].width))throw std::invalid_argument("memory fabric external width: "+std::string(fields[i].name));if(!fully_known(in[i].known,fields[i].width))throw std::runtime_error("IRIS_MEMORY_FABRIC_UNKNOWN_EXTERNAL_INPUT "+std::string(fields[i].name));}\nauto&wire=impl_->wire;\n'
 for n in external:code+='wire['+str(idx[n])+']=in['+str(extidx[n])+'].value;\n'
 code+='for(unsigned iteration=0;iteration<128;++iteration){auto previous=wire;\n'
 members={'rocket_cache':'rocket','l2':'l2','noc':'noc_model','rocket_tile':'rocket_tile','rocket_source':'rocket_source','rocket_sink':'rocket_sink','manager':'manager'}
 for cn,c in g['components'].items():
  fields=[f for f in c['physical_ports']if f['direction']=='input'];outs=[f for f in c['physical_ports']if f['direction']=='output'];member=members[cn]
  if cn=='noc':
   code+='{noc::NetworkInputs pins{};\n'
   for f in fields:code+='pins.values['+str(f['index'])+']='+expression(f['global'])+'.limbs[0];\n'
   code+='impl_->noc_model.evaluate(pins);auto result=impl_->noc_model.sample();\n'
   for f in outs:
    value='Bits(result.values['+str(f['index'])+'])';code+='impl_->observed['+str(outputidx[cn,f['name']])+']='+value+';\n'
    if f['global']['op']=='net':code+='wire['+str(idx[f['global']['name']])+']='+value+';\n'
  else:
   ty='cache::Bits'if cn in ['rocket_cache','l2']else'Bits';code+='{std::vector<'+ty+'>pins('+str(len(fields))+');\n'
   for f in fields:code+='pins['+str(f['index'])+'].limbs='+expression(f['global'])+'.limbs;\n'
   code+='impl_->'+member+'.evaluate(pins);auto result=impl_->'+member+'.sample();\n'
   for f in outs:
    value='result['+str(f['index'])+'].limbs';code+='impl_->observed['+str(outputidx[cn,f['name']])+'].limbs='+value+';\n'
    if f['global']['op']=='net':code+='wire['+str(idx[f['global']['name']])+'].limbs='+value+';\n'
  code+='}\n'
 code+='impl_->iterations=iteration+1;if(wire==previous){impl_->evaluated=true;return;}}throw std::runtime_error("IRIS_MEMORY_FABRIC_NO_COMBINATIONAL_FIXED_POINT");}\n'
 code+='std::vector<Bits>MemoryFabric::sample()const{if(!impl_->evaluated)throw std::logic_error("memory fabric sample requires fixed-point evaluation");return impl_->observed;}\n'
 code+='void MemoryFabric::commit(ClockEdges edges){if(!impl_->evaluated)throw std::logic_error("memory fabric commit requires fresh fixed point");if(!edges.rocket&&!edges.uncore){impl_->evaluated=false;throw std::invalid_argument("memory fabric commit requires a clock edge");}if(edges.rocket){impl_->rocket.commit();impl_->rocket_tile.commit();impl_->rocket_source.commit();++impl_->rocket_edge_count;}if(edges.uncore){impl_->l2.commit();impl_->noc_model.commit();impl_->rocket_sink.commit();impl_->manager.commit();++impl_->uncore_edge_count;}impl_->evaluated=false;}\nstd::vector<Bits>MemoryFabric::step(std::span<const Input>in,ClockEdges edges){evaluate(in);auto out=sample();commit(edges);return out;}\n'
 identity_inputs=[Path(__file__),R/'timing/memory_fabric.hpp',a.graph,ad/'build.json',cache/'build.json',noc/'build.json']
 identity_inputs=identity_inputs+[p for d in sdk for p in d.iterdir()if p.is_file()]+[Path('/usr/bin/g++'),Path('/usr/bin/ar')]
 identity=hashlib.sha256(json.dumps({'inputs':{str(p):sha(p)for p in identity_inputs},'generated_body_sha256':hashlib.sha256(code.encode()).hexdigest(),'clock_contract':'settle every source peer, then simultaneous preedge input sampling; commit only selected source domains'},sort_keys=True).encode()).hexdigest()
 code+='const char*MemoryFabric::source_identity(){return "'+identity+'";}\n}\n';generated=out/'memory_fabric.generated.cpp';generated.write_text(code)
 cmd=['/usr/bin/g++','-O3','-std=c++20','-I'+str(out/'sdk'),*['-I'+str(d)for d in sdk],'-c',str(generated),'-o',str(out/'memory_fabric.o')];begin=time.monotonic()
 with(out/'compile.log').open('w')as f:status=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 commands=[cmd]
 if not status:
  cmd=['/usr/bin/ar','rcs',str(out/'sdk/libiris_memory_fabric.a'),str(out/'memory_fabric.o')];commands.append(cmd);status=subprocess.run(cmd).returncode
 result={'schema':'iris.memory_fabric_composition_build.v1','source_identity':identity,'exit_status':status,'argv':commands,'input_sha256':{str(p):sha(p)for p in identity_inputs},'generated_cpp_sha256':sha(generated),'required_link_libraries':[str(p)for p in libs],'external_fields':len(external),'physical_outputs':len(outputs),'source_net_joins':len(g['joins']),'host_seconds':time.monotonic()-begin,'source_clock_domains':['rocket','uncore'],'added_clock_edges':0,'external_service_inferred':False,'all_external_input_bits_require_knownness':True,'full_internal_knownness_certified':False,'hardware_contacted':False,'timing_certified':False}
 if not status:result['library_sha256']=sha(out/'sdk/libiris_memory_fabric.a')
 (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k]for k in ['exit_status','source_identity','external_fields','physical_outputs','host_seconds']}))
 if status:raise SystemExit(status)
if __name__=='__main__':main()
