// New source-only causal witness. No CPU timings, memory or fitted costs.
#include "opu_sequencer.hpp"
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
using namespace iris::opu;

int main(int argc,char**argv){try{
 if(argc!=6)throw std::invalid_argument("kind size count pattern seed required");
 const std::string kind=argv[1],pattern=argv[4];unsigned size=std::stoul(argv[2]),count=std::stoul(argv[3]),seed=std::stoul(argv[5]);
 if((kind!="fp8"&&kind!="int8")||(pattern!="same"&&pattern!="rotate")||(size!=8&&size!=16&&size!=32)||(count!=16&&count!=64))throw std::invalid_argument("finite supported witness only");
 IrisOPUSequencer model(seed);std::map<std::string,size_t>ix,ox;
 auto inf=IrisOPUSequencer::input_fields();auto outf=IrisOPUSequencer::output_fields();
 for(size_t k=0;k<inf.size();++k)ix[std::string(inf[k].name)]=k;
 for(size_t k=0;k<outf.size();++k)ox[std::string(outf[k].name)]=k;
 unsigned next=0,issues=0;const unsigned micro=count*(size==32?4:1);int last=-1;
 for(unsigned edge=0;edge<4096;++edge){
  SequencerInputs in{};auto set=[&](const char*n,uint64_t v){in.values.at(ix.at(n))=v;};
  set("reset",edge<2);set("io_rvs1_ready",1);set("io_rvs2_ready",1);set("io_pipe_write_req_available",1);
  // No older external VRF reader/writer. Always-ready VRF/write resources are
  // explicit synthetic peers, not replayed or measured source ready signals.
  if(edge>=3&&next<count){
   unsigned tile=pattern=="rotate"?next%4:0;
   set("io_dis_valid",1);set("io_dis_bits_bits",(kind=="fp8"?0xf0001077U:0xf0000077U)|(16U<<20)|(8U<<15)|(tile<<10));
   set("io_dis_bits_vconfig_vl",size);set("io_dis_bits_vconfig_vtype_tm",size);set("io_dis_bits_vconfig_vtype_tk",1);
   set("io_dis_bits_vat",next%32);
  }
  model.evaluate(in);auto out=model.sample();
  auto get=[&](const char*n){auto k=ox.at(n);if(!out.defined[k])throw std::runtime_error("undefined active source output");return out.values[k];};
  bool accepted=edge>=3&&next<count&&get("io_dis_ready");
  bool issued=edge>=3&&get("io_iss_valid");
  std::cout<<"{\"edge\":"<<edge<<",\"input\":[";
  for(size_t k=0;k<in.values.size();++k){if(k)std::cout<<',';std::cout<<in.values[k];}
  std::cout<<"],\"accepted\":"<<(accepted?"true":"false")<<",\"command_index\":"<<next<<",\"issued\":"<<(issued?"true":"false");
  if(edge>=2)std::cout<<",\"dis_ready\":"<<get("io_dis_ready");
  if(issued){std::cout<<",\"entry\":"<<get("io_iss_bits_mrf_idx_0")<<",\"vat\":"<<get("io_vat")<<",\"fp8\":"<<get("io_iss_bits_fp8");++issues;last=edge;}
  std::cout<<"}\n";model.commit();if(accepted)++next;
  if(next==count&&issues==micro&&last>=0&&edge>=unsigned(last+6))return 0;
 }
 throw std::runtime_error("source witness did not drain");
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
