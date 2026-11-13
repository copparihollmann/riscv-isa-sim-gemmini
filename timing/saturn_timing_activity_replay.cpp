#include "saturn_timing.hpp"
#include "activity_qualification.hpp"
#include <zlib.h>
#include <verilated.h>
#include <array>
#include <bit>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <vector>
using namespace iris::saturn;
namespace {
void read_exact(gzFile file,void*target,std::size_t bytes){
 auto*at=static_cast<unsigned char*>(target);
 while(bytes){const auto chunk=std::min<std::size_t>(bytes,1<<20);const int got=gzread(file,at,chunk);
  if(got<=0)throw std::runtime_error("Truncated binary activity record");at+=got;bytes-=got;}
}
struct Counts{std::uint64_t edges=0,activity_checks=0,physical_checks=0,mix=1469598103934665603ULL,physical_mix=1469598103934665603ULL,reset_edges=0,scrub_edges=0;bool reset_seen=false,previous_nonreset=false;};
}
int main(int argc,char**argv){try{
 static_assert(std::endian::native==std::endian::little);
 if(argc!=3&&argc!=5&&argc!=9)throw std::invalid_argument("capture.bin.gz seed [--projection path.gz] [--mutate hart edge word]");
 const auto seed=std::stoul(argv[2]);
 gzFile projection=nullptr;int mutate_hart=-1;std::uint64_t mutate_edge=0,mutate_word=0;bool mutation_used=false;
 for(int n=3;n<argc;){const std::string op=argv[n++];if(op=="--projection"&&n<argc){projection=gzopen(argv[n++],"wb1");if(!projection)throw std::runtime_error("Cannot create projection");gzbuffer(projection,1<<20);}else if(op=="--mutate"&&n+2<argc){mutate_hart=std::stoi(argv[n++]);mutate_edge=std::stoull(argv[n++]);mutate_word=std::stoull(argv[n++]);}else throw std::invalid_argument("Invalid activity replay option");}
 VerilatedContext caller;const char*arguments[]={"foreign-activity-host","+iris_activity_owner=foreign"};caller.commandArgs(2,arguments);Verilated::threadContextp(&caller);
 const auto context_ok=[&](){if(Verilated::threadContextp()!=&caller)throw std::runtime_error("Activity API leaked owner context");};
 gzFile file=gzopen(argv[1],"rb");if(!file)throw std::invalid_argument("Cannot open capture");gzbuffer(file,1<<20);
 std::uint64_t header[4];read_exact(file,header,sizeof(header));
 if(header[0]!=0x314e494254415349ULL)throw std::invalid_argument("Wrong binary activity magic");
 std::array<std::unique_ptr<SaturnTimingCut>,3> models;
 std::array<Counts,3> totals;
 // Exercise interleaved instances; SDK must select its own Verilator context.
 for(unsigned h:{2u,0u,1u}){models[h]=std::make_unique<SaturnTimingCut>(h==2?Profile::Rocket256:Profile::Compute128,h,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);context_ok();}
 std::array<std::uint64_t,3> previous_tb{};
 for(;;){
  std::uint64_t frame[4];const int first=gzread(file,frame,sizeof(frame));
  if(first==0)break;if(first!=sizeof(frame))throw std::invalid_argument("Truncated record header");
  const auto[tb,edge,h,words]=std::array<std::uint64_t,4>{frame[0],frame[1],frame[2],frame[3]};
  if(h>2||words!=header[h+1]||edge!=totals[h].edges||(edge&&tb<=previous_tb[h]))throw std::invalid_argument("Discontinuous/source-width activity record");
  previous_tb[h]=tb;auto&model=*models[h];auto&c=totals[h];
  const auto profile=model.profile();const auto ni=model.input_fields(profile).size(),no=model.output_fields(profile).size(),na=model.activity_fields(profile).size();
  if(words!=ni+no+na)throw std::invalid_argument("SDK/source schema disagreement");
  std::vector<std::uint64_t> all(words);read_exact(file,all.data(),8*words);
  ReferenceInputs inputs{{all.begin(),all.begin()+ni}};const auto*gold_out=all.data()+ni;auto*gold_activity=all.data()+ni+no;
  if(int(h)==mutate_hart&&edge==mutate_edge){if(mutate_word>=na)throw std::invalid_argument("Mutation beyond schema");gold_activity[mutate_word]^=1;mutation_used=true;}
  model.evaluate(inputs);context_ok();const auto actual=model.sample();context_ok();const auto activity=model.sample_activity(tb);context_ok();
  if(activity.hart!=h||activity.source_edge!=edge||activity.uncore_tick!=tb||activity.source_clock_id!=model.source_clock_id(profile,h))throw std::runtime_error("Lost source clock/hart identity");
  const bool reset=inputs.words[reset_index(profile)]!=0;
  const bool qualified=c.reset_seen&&!reset;
  if(qualified){
   const auto rules=activity_rules(profile);
   for(const auto&r:rules){
    if(r.postreset&&!c.previous_nonreset)continue;
    if(r.valid>=0&&!gold_activity[r.valid])continue;
    if(!r.any.empty()){bool active=false;for(auto index:r.any)active|=gold_activity[index]!=0;if(!active)continue;}
    for(const auto&w:r.words){
     const auto a=activity.words[w.index]&w.mask,g=gold_activity[w.index]&w.mask;
     if(a!=g)throw std::runtime_error("Activity mismatch h"+std::to_string(h)+" edge"+std::to_string(edge)+" TB"+std::to_string(tb)+" "+r.name+"@"+std::to_string(w.index)+" got="+std::to_string(a)+" expected="+std::to_string(g));
     ++c.activity_checks;c.mix=(c.mix^g)*1099511628211ULL;
    }
   }
   for(const auto&r:physical_rules(profile)){
    if(r.valid>=0&&!(r.input_valid?inputs.words[r.valid]:gold_out[r.valid]))continue;
    const auto mask=physical_mask(r,profile,inputs.words,gold_out);
    if((actual.words[r.index]^gold_out[r.index])&mask)throw std::runtime_error("Physical mismatch h"+std::to_string(h)+" edge"+std::to_string(edge)+" "+r.name);
    ++c.physical_checks;c.physical_mix=(c.physical_mix^(gold_out[r.index]&mask))*1099511628211ULL;
   }
   if(gold_activity[scrub_index(profile)])++c.scrub_edges;
  }
  if(projection){
   const auto values=project_activity(profile,qualified,c.previous_nonreset,reset,activity.words);
   std::string row="["+std::to_string(h)+","+std::to_string(edge)+","+std::to_string(tb)+","+std::to_string(values.known);
   for(auto value:values.values)row+=","+std::to_string(value);row+="]\n";
   if(gzwrite(projection,row.data(),row.size())!=int(row.size()))throw std::runtime_error("Projection write failed");
  }
  if(reset){c.reset_seen=true;++c.reset_edges;}c.previous_nonreset=!reset&&c.reset_seen;
  model.commit();context_ok();++c.edges;
  // Inspecting registered dispatch metadata must not advance the clock.
  const auto dispatch=model.inspect_dispatch_registers();context_ok();if(dispatch.source_edge!=c.edges)throw std::runtime_error("Dispatch inspection changed phase");
 }
 if(gzclose(file)!=Z_OK)throw std::runtime_error("Capture decompression failed");
 if(projection&&gzclose(projection)!=Z_OK)throw std::runtime_error("Projection close failed");
 if(mutate_hart>=0&&!mutation_used)throw std::invalid_argument("Mutation point was not captured");
 std::cout<<"{\"seed\":"<<seed<<",\"harts\":[";
 for(unsigned h=0;h<3;++h){const auto&c=totals[h];if(!c.reset_seen||!c.edges)throw std::runtime_error("Missing actual per-hart reset");if(h)std::cout<<',';
  std::cout<<"{\"hart\":"<<h<<",\"source_edges\":"<<c.edges<<",\"qualified_activity_words\":"<<c.activity_checks<<",\"activity_mix64\":"<<c.mix<<",\"qualified_physical_words\":"<<c.physical_checks<<",\"physical_mix64\":"<<c.physical_mix<<",\"reset_edges\":"<<c.reset_edges<<",\"postreset_scrub_edges\":"<<c.scrub_edges<<'}';}
 std::cout<<"]}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
