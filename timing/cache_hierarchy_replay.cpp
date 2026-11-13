#include "cache_hierarchy.hpp"
#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include <zlib.h>
using namespace iris::cache;
struct Binding{unsigned frame_offset,index,words;};
struct Rule{unsigned frame_offset,index,words;int valid_offset,flag_offset,opcode_offset;unsigned kind;const char*name;};
struct Definition{const char*name;Component kind;std::vector<Binding>inputs;std::vector<Rule>outputs;unsigned reset_offset;int cpu_valid,cpu_ready,cpu_resp,cpu_nack,aux_tlb_valid;};
#include "cache_hierarchy_replay_map.hpp"
struct State{
 Definition definition;Model model;bool started=false;std::uint64_t compares=0,edges=0,requests=0,responses=0,nacks=0;
 explicit State(Definition d,unsigned seed,UnresetReplayPolicy policy):definition(std::move(d)),model(definition.kind,seed,policy){}
};
static bool qualified(const Rule&r,const std::vector<std::uint64_t>&frame){
 if(r.kind==9)return false; // Not a source-defined observation for this probe.
 if(r.valid_offset>=0&&!frame[r.valid_offset])return false;
 if(r.flag_offset>=0&&!frame[r.flag_offset])return false;
 if(r.kind==1){auto op=frame[r.opcode_offset];return op<=3;} // A: data-carrying opcodes only.
 if(r.kind==2){auto op=frame[r.opcode_offset];return op==5||op==7;} // C: ProbeAckData/ReleaseData.
 if(r.kind==3){auto op=frame[r.opcode_offset];return op==1||op==5;} // D: AccessAckData/GrantData.
 if(r.kind==4){auto op=frame[r.opcode_offset];return op==1||op==4||op==7||(op>=8&&op<=15)||op==17;}
 return true;
}
int main(int argc,char**argv){try{
 if(argc<2)throw std::invalid_argument("usage: replay trace.gz [--instance=name] [--explore-concrete-reset] [--wrong-output]");
 bool wrong=false,injected=false,explore=false;std::string selected;
 for(int i=2;i<argc;++i){std::string flag=argv[i];if(flag=="--wrong-output")wrong=true;else if(flag=="--explore-concrete-reset")explore=true;else if(flag.rfind("--instance=",0)==0)selected=flag.substr(11);else throw std::invalid_argument("unknown replay flag");}
 gzFile file=gzopen(argv[1],"rb");if(!file)throw std::runtime_error("cannot open cache boundary trace");
 std::vector<std::unique_ptr<State>> states;for(auto definition:definitions())if(selected.empty()||selected==definition.name)states.push_back(std::make_unique<State>(std::move(definition),113,explore?UnresetReplayPolicy::ExploreConcreteReset:UnresetReplayPolicy::RefuseUse));
 if(states.empty())throw std::invalid_argument("unknown cache instance selector");
 std::vector<std::uint64_t> frame(FRAME_WORDS);std::uint64_t frames=0,last_tick=0;
 for(;;){int count=gzread(file,frame.data(),frame.size()*8);if(!count)break;
  if(count!=int(frame.size()*8))throw std::runtime_error("truncated physical cache frame");
  if(frames&&frame[0]<=last_tick)throw std::runtime_error("cache frame timestamps are not ordered");last_tick=frame[0];++frames;
  for(auto &pointer:states){auto&s=*pointer;const auto&d=s.definition;
   if(!s.started&&!frame[d.reset_offset])continue;
   if(d.aux_tlb_valid>=0&&frame[d.aux_tlb_valid])throw std::runtime_error("auxiliary vector TLB request is outside scalar replay qualification");
   s.started=true;std::vector<Bits> inputs(s.model.input_fields().size());
   for(const auto&binding:d.inputs)for(unsigned limb=0;limb<binding.words;++limb)inputs[binding.index].limbs[limb]=frame[binding.frame_offset+limb];
   s.model.evaluate(inputs);auto output=s.model.sample();
   if(!frame[d.reset_offset]&&s.edges>=2){
    for(const auto&r:d.outputs){if(!qualified(r,frame))continue;
     for(unsigned limb=0;limb<r.words;++limb){auto expected=frame[r.frame_offset+limb];
      if(wrong&&!injected&&s.compares>=100){expected^=1;injected=true;}
      ++s.compares;if(output[r.index].limbs[limb]!=expected){
       std::cerr<<"CACHE_BOUNDARY_MISMATCH instance="<<d.name<<" frame="<<frames<<" tb="<<frame[0]<<" field="<<r.name<<" limb="<<limb<<" expected=0x"<<std::hex<<expected<<" model=0x"<<output[r.index].limbs[limb]<<std::dec<<'\n';return 1;}
     }
    }
    if(d.cpu_valid>=0&&frame[d.cpu_valid]&&frame[d.cpu_ready])++s.requests;
    if(d.cpu_resp>=0&&frame[d.cpu_resp])++s.responses;
    if(d.cpu_nack>=0&&frame[d.cpu_nack])++s.nacks;
   }
   s.model.commit();++s.edges;
  }
 }
 int error;const char*detail=gzerror(file,&error);if(error!=Z_OK&&error!=Z_STREAM_END)throw std::runtime_error(std::string("invalid compressed cache trace: ")+detail);
 gzclose(file);if(!frames)throw std::runtime_error("empty cache trace");if(wrong&&!injected)throw std::runtime_error("negative control was not exercised");
 std::cout<<"{\"status\":\"passed_saved_soc_cache_boundary_replay\",\"frames\":"<<frames<<",\"last_tb\":"<<last_tick<<",\"source_identity\":\""<<Model::source_identity()<<"\",\"instances\":[";
 for(unsigned i=0;i<states.size();++i){const auto&s=*states[i];if(!s.started||!s.compares)throw std::runtime_error("cache instance had no reset-qualified comparison");
  if(i)std::cout<<',';std::cout<<"{\"instance\":\""<<s.definition.name<<"\",\"edges\":"<<s.edges<<",\"compared_words\":"<<s.compares<<",\"cpu_requests\":"<<s.requests<<",\"cpu_responses\":"<<s.responses<<",\"cpu_nacks\":"<<s.nacks<<",\"concretized_unknown_replay_timing\":"<<(s.model.concretized_unknown_replay_timing()?"true":"false")<<'}';}
 std::cout<<"],\"measured_internal_state_injected\":false,\"automatic_external_service\":false,\"concrete_reset_exploration_explicit\":"<<(explore?"true":"false")<<",\"hardware_contacted\":false,\"timing_certified\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<"CACHE_REPLAY_REFUSAL: "<<e.what()<<'\n';return 2;}}
