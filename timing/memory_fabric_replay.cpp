#include "memory_fabric.hpp"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <zlib.h>
using namespace iris::fabric;
struct Binding {unsigned frame,index,words,width;};
struct Rule {unsigned frame,index,words;int valid,flag,opcode;unsigned kind;const char*name;};
#include "memory_fabric_replay_schema.hpp"
static bool qualified(const Rule&r,const std::vector<std::uint64_t>&f){
 if(r.kind==9)return false;
 if(r.valid>=0&&!f[r.valid])return false;
 if(r.flag>=0&&!f[r.flag])return false;
 if(r.kind==1)return f[r.opcode]<=3;
 if(r.kind==2)return f[r.opcode]==5||f[r.opcode]==7;
 if(r.kind==3)return f[r.opcode]==1||f[r.opcode]==5;
 if(r.kind==4){auto op=f[r.opcode];return op==1||op==4||op==7||(op>=8&&op<=15)||op==17;}
 return true;
}
static Bits known(unsigned width){Bits x;for(unsigned bit=0;bit<width;++bit)x.limbs[bit/64]|=std::uint64_t(1)<<(bit%64);return x;}
int main(int argc,char**argv){try{
 if(argc<2)throw std::invalid_argument("usage: replay trace.gz [--wrong-output|--wrong-data]");bool wrong=false,data=false,injected=false;for(int n=2;n<argc;++n){std::string s=argv[n];if(s=="--wrong-output")wrong=true;else if(s=="--wrong-data")data=true;else throw std::invalid_argument("unknown replay flag");}
 gzFile z=gzopen(argv[1],"rb");if(!z)throw std::runtime_error("trace unavailable");MemoryFabric model(113);std::vector<std::uint64_t>frame(FRAME_WORDS);std::vector<Input>in(MemoryFabric::input_fields().size());for(const auto&b:bindings)in[b.index].known=known(b.width);std::uint64_t frames=0,words=0,last=0,qualified_frames=0;
 for(;;){int n=gzread(z,frame.data(),frame.size()*8);if(!n)break;if(n!=int(frame.size()*8))throw std::runtime_error("truncated fabric frame");if(frames&&frame[0]<=last)throw std::runtime_error("unordered physical clock frames");last=frame[0];++frames;
  for(const auto&b:bindings)for(unsigned limb=0;limb<b.words;++limb)in[b.index].value.limbs[limb]=frame[b.frame+limb];
  if(frame[AUX_TLB_VALID])throw std::runtime_error("active auxiliary TLB request outside this scalar reference corpus");
  model.evaluate(in);auto actual=model.sample();bool reset=false;for(auto offset:reset_offsets)reset|=frame[offset]!=0;
  if(!reset&&frames>=2){++qualified_frames;for(const auto&r:rules){if(!qualified(r,frame))continue;for(unsigned limb=0;limb<r.words;++limb){auto expected=frame[r.frame+limb];if(!injected&&((wrong&&words>=100)||(data&&(r.kind==1||r.kind==2||r.kind==3)))){expected^=1;injected=true;}++words;if(actual[r.index].limbs[limb]!=expected){std::cerr<<"MEMORY_FABRIC_MISMATCH frame="<<frames<<" tb="<<frame[0]<<" field="<<r.name<<" limb="<<limb<<" expected=0x"<<std::hex<<expected<<" model=0x"<<actual[r.index].limbs[limb]<<std::dec<<"\n";return 1;}}}}
  model.commit({true,true});
 }
 int error;const char*detail=gzerror(z,&error);if(error!=Z_OK&&error!=Z_STREAM_END)throw std::runtime_error(std::string("invalid compressed fabric trace: ")+detail);gzclose(z);if(!frames||!words)throw std::runtime_error("empty/unqualified trace");if((wrong||data)&&!injected)throw std::runtime_error("negative control not exercised");
 std::cout<<"{\"status\":\"passed_closed_boundary_source_coupling\",\"frames\":"<<frames<<",\"qualified_frames\":"<<qualified_frames<<",\"compared_words\":"<<words<<",\"last_tb\":"<<last<<",\"rocket_edges\":"<<model.rocket_edges()<<",\"uncore_edges\":"<<model.uncore_edges()<<",\"external_fields\":"<<in.size()<<",\"source_identity\":\""<<MemoryFabric::source_identity()<<"\",\"joined_ready_or_state_injected\":false,\"service\":\"external physical reference boundary only; not a fitted service model\",\"hardware_contacted\":false,\"timing_certified\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<"MEMORY_FABRIC_REPLAY_REFUSAL "<<e.what()<<"\n";return 2;}}
