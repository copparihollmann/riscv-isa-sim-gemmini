#include "serial_memory_system.hpp"
#include "serial_memory_system_identity.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>
namespace iris::memory_system {
namespace F=iris::fabric;
namespace S=iris::serial_memory;
namespace {
constexpr unsigned absent=std::numeric_limits<unsigned>::max();
std::uint64_t width_mask(unsigned width){return width==64?~std::uint64_t(0):(std::uint64_t(1)<<width)-1;}
Bits known(unsigned width){Bits bits;for(unsigned b=0;b<width;++b)bits.limbs[b/64]|=std::uint64_t(1)<<(b%64);return bits;}
struct Join {unsigned output,input,width;};
}
struct System::Impl {
  F::MemoryFabric fabric;
  S::Model path;
  std::vector<F::Input> fabric_in;
  std::vector<S::Bits> path_in;
  std::vector<Bits> fabric_out;
  std::vector<std::uint64_t>path_out;
  std::vector<Join>to_path,to_fabric;
  std::vector<unsigned>fabric_projection,path_projection;
  std::vector<std::string>input_names,output_names;
  std::vector<Field>inputs,outputs;
  bool evaluated=false;
  unsigned iterations=0;
  std::uint64_t phases=0;
  Impl(unsigned seed,const std::vector<std::string>&args,S::AssertionPolicy policy):fabric(seed),path(seed+7,args,policy){
    auto ff=F::MemoryFabric::input_fields();fabric_in.resize(ff.size());fabric_projection.resize(ff.size(),absent);
    auto sf=path.input_fields();path_in.resize(sf.size());path_projection.resize(sf.size(),absent);
    for(unsigned i=0;i<ff.size();++i)fabric_in[i].known=known(ff[i].width);
    for(unsigned i=0;i<sf.size();++i)path_in[i]={0,width_mask(sf[i].width)};
    auto path_index=[](std::span<const S::Field>fs,const std::string&name){for(unsigned i=0;i<fs.size();++i)if(name==fs[i].name)return i;throw std::invalid_argument("IRIS_MEMORY_SYSTEM_MISSING_SOURCE_PORT "+name);};
    for(unsigned bank=0;bank<4;++bank){
      auto fp="auto_coupler_to_bus_named_mbus_bus_xing_out_"+std::to_string(bank)+"_",sp="iris_mbus_auto_bus_xing_in_"+std::to_string(bank)+"_";
      for(const auto*field:{"a_valid","a_bits_opcode","a_bits_param","a_bits_size","a_bits_source","a_bits_address","a_bits_mask","a_bits_data","a_bits_corrupt","d_ready"}){
        auto output=F::MemoryFabric::output_index("manager",fp+field),input=path_index(sf,sp+field);auto width=F::MemoryFabric::output_fields()[output].width;
        if(width!=sf[input].width)throw std::runtime_error("IRIS_MEMORY_SYSTEM_SOURCE_PORT_WIDTH_DISAGREES");to_path.push_back({output,input,width});
      }
      for(const auto*field:{"a_ready","d_valid","d_bits_opcode","d_bits_param","d_bits_size","d_bits_source","d_bits_data","d_bits_denied","d_bits_corrupt"}){
        auto output=path_index(path.output_fields(),sp+field),input=F::MemoryFabric::external_input_index("manager",fp+field);auto width=path.output_fields()[output].width;
        if(width!=ff[input].width)throw std::runtime_error("IRIS_MEMORY_SYSTEM_SOURCE_PORT_WIDTH_DISAGREES");to_fabric.push_back({output,input,width});
      }
    }
    std::vector<bool>joined_f(ff.size()),joined_s(sf.size());for(auto j:to_fabric)joined_f[j.input]=true;for(auto j:to_path)joined_s[j.input]=true;
    for(unsigned i=0;i<ff.size();++i)if(!joined_f[i]){fabric_projection[i]=input_names.size();input_names.push_back("fabric/"+std::string(ff[i].name));}
    for(unsigned i=0;i<sf.size();++i)if(!joined_s[i]){path_projection[i]=input_names.size();input_names.push_back("path/"+std::string(sf[i].name));}
    for(unsigned i=0;i<ff.size();++i)if(!joined_f[i])inputs.push_back({input_names[fabric_projection[i]],ff[i].width});
    for(unsigned i=0;i<sf.size();++i)if(!joined_s[i])inputs.push_back({input_names[path_projection[i]],sf[i].width});
    for(auto f:F::MemoryFabric::output_fields())output_names.push_back("fabric/"+std::string(f.name));for(auto f:path.output_fields())output_names.push_back("path/"+std::string(f.name));
    unsigned index=0;for(auto f:F::MemoryFabric::output_fields())outputs.push_back({output_names[index++],f.width});for(auto f:path.output_fields())outputs.push_back({output_names[index++],f.width});
  }
};
System::System(unsigned seed,std::vector<std::string>args,S::AssertionPolicy p):impl_(std::make_unique<Impl>(seed,args,p)){}
System::~System()=default;
const char*System::source_identity(){return IRIS_SERIAL_MEMORY_SYSTEM_SOURCE_ID;}
std::span<const Field>System::input_fields()const{return impl_->inputs;}
std::span<const Field>System::output_fields()const{return impl_->outputs;}
unsigned System::external_input_index(std::string_view c,std::string_view f)const{
  if(c=="path"){auto fields=impl_->path.input_fields();for(unsigned i=0;i<fields.size();++i)if(f==fields[i].name&&impl_->path_projection[i]!=absent)return impl_->path_projection[i];}
  else{auto i=F::MemoryFabric::external_input_index(c,f);if(impl_->fabric_projection[i]!=absent)return impl_->fabric_projection[i];}
  throw std::invalid_argument("IRIS_MEMORY_SYSTEM_PORT_IS_JOINED_OR_UNKNOWN");
}
unsigned System::output_index(std::string_view c,std::string_view f)const{
  if(c=="path"){auto fields=impl_->path.output_fields();for(unsigned i=0;i<fields.size();++i)if(f==fields[i].name)return F::MemoryFabric::output_fields().size()+i;throw std::invalid_argument("IRIS_MEMORY_SYSTEM_UNKNOWN_OUTPUT");}
  return F::MemoryFabric::output_index(c,f);
}
unsigned System::last_settle_iterations()const{return impl_->iterations;}
std::uint64_t System::committed_phases()const{return impl_->phases;}
void System::evaluate(std::span<const Input>in){
  impl_->evaluated=false;if(in.size()!=impl_->inputs.size())throw std::invalid_argument("IRIS_MEMORY_SYSTEM_INPUT_COUNT");
  for(unsigned i=0;i<in.size();++i){auto required=known(impl_->inputs[i].width);for(unsigned limb=0;limb<4;++limb){if((in[i].known.limbs[limb]&required.limbs[limb])!=required.limbs[limb])throw std::runtime_error("IRIS_MEMORY_SYSTEM_UNKNOWN_EXTERNAL_INPUT "+std::string(impl_->inputs[i].name));if(in[i].value.limbs[limb]&~required.limbs[limb])throw std::invalid_argument("IRIS_MEMORY_SYSTEM_INPUT_WIDTH "+std::string(impl_->inputs[i].name));}}
  for(unsigned i=0;i<impl_->fabric_projection.size();++i)if(impl_->fabric_projection[i]!=absent)impl_->fabric_in[i]=in[impl_->fabric_projection[i]];
  for(unsigned i=0;i<impl_->path_projection.size();++i)if(impl_->path_projection[i]!=absent){auto&v=in[impl_->path_projection[i]];impl_->path_in[i]={v.value.limbs[0],v.known.limbs[0]};}
  for(unsigned iteration=0;iteration<32;++iteration){
    auto previous_f=impl_->fabric_out;auto previous_s=impl_->path_out;
    impl_->fabric.evaluate(impl_->fabric_in);impl_->fabric_out=impl_->fabric.sample();
    for(auto j:impl_->to_path)impl_->path_in[j.input]={impl_->fabric_out[j.output].limbs[0],width_mask(j.width)};
    impl_->path.evaluate(impl_->path_in);impl_->path_out=impl_->path.sample();bool changed=false;
    for(auto j:impl_->to_fabric){auto value=Bits(impl_->path_out[j.output]);changed|=impl_->fabric_in[j.input].value!=value;impl_->fabric_in[j.input]={value,known(j.width)};}
    impl_->iterations=iteration+1;
    if(!changed&&previous_f==impl_->fabric_out&&previous_s==impl_->path_out){impl_->evaluated=true;return;}
  }
  throw std::runtime_error("IRIS_MEMORY_SYSTEM_SOURCE_FIXED_POINT_DID_NOT_SETTLE");
}
std::vector<Bits>System::sample()const{
  if(!impl_->evaluated)throw std::logic_error("IRIS_MEMORY_SYSTEM_SAMPLE_REQUIRES_EVALUATION");auto out=impl_->fabric_out;for(auto value:impl_->path_out)out.emplace_back(value);return out;
}
void System::commit(ClockEdges edges){
  if(!impl_->evaluated)throw std::logic_error("IRIS_MEMORY_SYSTEM_COMMIT_REQUIRES_EVALUATION");
  impl_->evaluated=false;
  if(!edges.rocket&&!edges.uncore&&!edges.bringup&&!edges.serial)throw std::invalid_argument("IRIS_MEMORY_SYSTEM_EMPTY_EDGE_SET");
  // Neither peer is re-evaluated after the first commit. Both consume the
  // exact same settled pre-edge inputs, including simultaneous clock edges.
  if(edges.rocket||edges.uncore)impl_->fabric.commit({edges.rocket,edges.uncore});
  if(edges.uncore||edges.bringup||edges.serial)impl_->path.commit({edges.uncore,edges.bringup,edges.serial});
  ++impl_->phases;
}
}
