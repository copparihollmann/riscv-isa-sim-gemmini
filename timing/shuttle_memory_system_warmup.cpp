#include "cache_hierarchy.hpp"
#include <deque>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
namespace C=iris::cache;
namespace {
unsigned checks=0;
void need(bool ok,const char*why){++checks;if(!ok)throw std::runtime_error(why);}
std::uint64_t pattern(std::uint64_t address){return 0x93ac4e1000000000ULL^address;}
struct Request{std::uint64_t address,source;};
struct Bench{
  C::Model model;
  std::vector<C::Bits>in,out;
  std::map<std::string,unsigned>ii,oi;
  std::deque<Request>requests;
  std::map<unsigned,std::uint64_t>expected;
  std::set<unsigned>returned;
  unsigned cycle=0,nacks=0;
  bool observing=false;
  std::uint64_t previous_address=0;
  Bench(unsigned seed):model(C::Component::ShuttleL1D,seed,C::UnresetReplayPolicy::RefuseUse){
    for(auto f:model.input_fields())ii[std::string(f.name)]=ii.size();for(auto f:model.output_fields())oi[std::string(f.name)]=oi.size();in.resize(ii.size());
    set("auto_out_a_ready",1);set("auto_out_c_ready",1);set("auto_out_e_ready",1);set("reset",1);for(unsigned i=0;i<8;++i)tick();set("reset",0);for(unsigned i=0;i<160;++i)tick();need(get("io_ordered"),"cache sweep did not complete");observing=true;
  }
  void set(const std::string&n,std::uint64_t v){in[ii.at(n)]=C::Bits(v);}
  std::uint64_t get(const std::string&n)const{return out.at(oi.at(n)).limbs[0];}
  void tick(){
    set("io_s1_paddr",previous_address);model.evaluate(in);out=model.sample();
    bool accept=in[ii.at("io_req_valid")].limbs[0]&&get("io_req_ready");auto address=in[ii.at("io_req_bits_addr")].limbs[0];
    if(observing&&get("auto_out_a_valid")){need(get("auto_out_a_bits_opcode")==6&&get("auto_out_a_bits_size")==6,"unexpected initialization acquire");requests.push_back({get("auto_out_a_bits_address"),get("auto_out_a_bits_source")});}
    if(observing)nacks+=get("io_s2_nack");
    if(observing&&get("io_resp_valid")&&get("io_resp_bits_has_data")){auto tag=unsigned(get("io_resp_bits_tag"));need(expected.count(tag),"unowned initialization response");need(returned.insert(tag).second,"duplicate initialization response");need(get("io_resp_bits_data")==pattern(expected.at(tag)),"initialization load data/address changed");}
    model.commit();if(accept)previous_address=address;++cycle;
  }
  void offer(unsigned command,unsigned tag,std::uint64_t address){set("io_req_valid",1);set("io_req_bits_addr",address);set("io_req_bits_cmd",command);set("io_req_bits_tag",tag);set("io_req_bits_size",3);}
};
void run(unsigned seed){
  Bench b(seed);unsigned accepted=0;
  for(unsigned tick=0;accepted<64&&tick<2000;++tick){auto address=0x80000000ULL+(accepted/16)*64+(accepted%8)*8;b.offer(0,accepted,address);b.expected[accepted]=address;b.tick();if(b.get("io_req_ready"))++accepted;}
  need(accepted==64,"source did not accept64 initialization loads");b.set("io_req_valid",0);b.tick();b.tick();need(b.requests.size()==4,"initialization did not allocate all four cached misses");
  unsigned grants=0;
  while(!b.requests.empty()){auto q=b.requests.front();b.requests.pop_front();b.set("auto_out_d_valid",1);b.set("auto_out_d_bits_opcode",5);b.set("auto_out_d_bits_param",0);b.set("auto_out_d_bits_size",6);b.set("auto_out_d_bits_source",q.source);b.set("auto_out_d_bits_sink",0);
    for(unsigned beat=0;beat<8;++beat){b.set("auto_out_d_bits_data",pattern(q.address+8*beat));unsigned wait=0;do{b.tick();need(++wait<100,"source D receiver stalled");}while(!b.get("auto_out_d_ready"));}++grants;
  }
  b.set("auto_out_d_valid",0);for(unsigned i=0;i<200;++i)b.tick();need(b.returned.size()==64,"not all initialization requests replayed");need(!b.model.concretized_unknown_replay_timing(),"initialization silently concretized unknown replay state");
  b.offer(1,96,0x80000008);b.set("io_s1_data_data",0x55aa11ee22dd33ccULL);unsigned wait=0;do{b.tick();need(++wait<100,"post-initialization store stalled");}while(!b.get("io_req_ready"));b.set("io_req_valid",0);bool response=false;for(unsigned i=0;i<12;++i){b.tick();response|=b.get("io_resp_valid");}need(response,"post-initialization store did not respond");need(!b.model.concretized_unknown_replay_timing(),"store used a concrete unknown command");
  std::cout<<"{\"seed\":"<<seed<<",\"accepted_initialization_loads\":"<<accepted<<",\"load_responses\":"<<b.returned.size()<<",\"grants\":"<<grants<<",\"nacks\":"<<b.nacks<<",\"default_refusal_policy\":true,\"concretized_unknown_replay_timing\":false}\n";
}
}
int main(){try{for(unsigned seed:{1U,7U,31U,113U})run(seed);std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"external_service\":\"explicit withheld-D initialization stimulus, not hardware timing\"}\n";return 0;}catch(const std::exception&e){std::cerr<<"strict source warmup: "<<e.what()<<'\n';return 1;}}
