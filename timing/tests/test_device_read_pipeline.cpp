#include "memory.hpp"
#include <cassert>
#include <map>
using namespace spike_timing;
struct Result{merlin_timing::Cycle cold,hit,dirty_probe,clean_probe,device_write,cpu;std::uint64_t applied;};
Result check(const char*path){
 Model model(path);merlin_timing::Engine engine(model.max_values,model.resources);
 std::uint64_t next=0;std::map<std::string,std::uint64_t>features;unsigned unknown=0;
 MemorySystem m(model,engine,[&](std::size_t n){auto out=next;next+=n;return out;},
   [&](const auto&k,auto n){features[k]+=n;},[&](const auto&){++unknown;});
 auto access=[&](std::uint64_t address,bool write,const char*name){auto out=m.access({{address,16,write}},name);assert(out.latency);return *out.latency;};
 auto cold=access(0x81000000,false,"device"),hit=access(0x81000000,false,"device");
 access(0x81001000,true,"cpu_data");auto dirty=access(0x81001000,false,"device");
 access(0x81002000,false,"cpu_data");auto clean=access(0x81002000,false,"device");
 auto write=access(0x81000000,true,"device"),cpu=access(0x81003000,false,"cpu_data");
 assert(!unknown);return {cold,hit,dirty,clean,write,cpu,features["modeled.cache.l2.source_read_pipeline_applied"]};
}
int main(int argc,char**argv){
 assert(argc==4);const auto old=check(argv[1]),source=check(argv[2]);
 assert(source.cold==old.cold+3&&source.hit==old.hit+3);
 // Coherent protocol dominates: pipeline belongs BEFORE the existing max.
 // Adding three cycles to the final SharedEffects would fail BOTH checks.
 assert(source.dirty_probe==old.dirty_probe&&source.clean_probe==old.clean_probe);
 assert(source.device_write==old.device_write&&source.cpu==old.cpu);
 assert(old.applied==0&&source.applied==4);
 bool refused=false;try{check(argv[3]);}catch(const std::invalid_argument&){refused=true;}assert(refused);
}
