#include "cache_hierarchy.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>
using namespace iris::cache;
int main(){try{
 constexpr std::uint64_t cycles=200000;bool comma=false;std::cout<<"{\"schema\":\"iris.cache_component_idle_speed.v1\",\"source_identity\":\""<<Model::source_identity()<<"\",\"rows\":[";
 for(auto kind:{Component::ShuttleL1D,Component::RocketL1D,Component::InclusiveL2}){
  Model m(kind,1);std::vector<Bits> input(m.input_fields().size());unsigned reset=0;
  for(unsigned i=0;i<m.input_fields().size();++i)if(m.input_fields()[i].name=="reset")reset=i;
  input[reset]=Bits(1);for(unsigned i=0;i<8;++i)m.step(input);input[reset]=Bits(0);for(unsigned i=0;i<600;++i)m.step(input);
  auto start=std::chrono::steady_clock::now();std::uint64_t checksum=0;
  for(std::uint64_t i=0;i<cycles;++i){auto out=m.step(input);for(const auto &value:out)checksum^=value.limbs[0];}
  double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  if(comma)std::cout<<',';comma=true;std::cout<<"{\"component\":\""<<(kind==Component::ShuttleL1D?"shuttle":kind==Component::RocketL1D?"rocket":"l2")<<"\",\"edges\":"<<cycles<<",\"host_seconds\":"<<seconds<<",\"idle_edges_per_second\":"<<cycles/seconds<<",\"output_checksum\":"<<checksum<<'}';
 }
 std::cout<<"],\"scope\":\"In-process idle component edges including public input/output handling; no instructions retired; not simulator MIPS or workload throughput\",\"hardware_contacted\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
