#include "frontend_cache_pipeline.hpp"
#include <array>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

using iris::frontend::ShuttleCachePipeline;
static void require(bool value,const std::string& what,uint64_t row) {
  if(!value)throw std::runtime_error(what+" row="+std::to_string(row));
}
int main(int argc,char**argv) {
  if(argc!=2)throw std::invalid_argument("expected continuous actual RTL cache interface corpus");
  std::array<ShuttleCachePipeline,2> models;
  std::array<uint64_t,2> previous_edge{};
  std::array<bool,2> initialized{};
  std::ifstream file(argv[1]);uint64_t rows=0,checks=0,requests=0,responses=0,data_beats=0,kills=0;
  std::array<uint64_t,24> v{};
  while(file>>v[0]) {
    for(unsigned i=1;i<v.size();++i)if(!(file>>v[i]))throw std::runtime_error("truncated interface row");
    const auto [h,edge,reset,valid,addr,paddr,k1,k2,inv,ar,db,s0fire,resp,miss,req,refaddr,
                s1v,s2v,s2hit,canreg,refvalid,rng,postaddr,done]=v;
    require(h<2,"unexpected hart",rows);auto& model=models[h];
    if(!initialized[h]) {require(reset,"missing observed reset",rows);initialized[h]=true;}
    if(previous_edge[h])require(edge==previous_edge[h]+1,"missing source edge",rows);
    previous_edge[h]=edge;
    ShuttleCachePipeline::Inputs in{bool(reset),bool(valid),addr,paddr,bool(k1),bool(k2),bool(inv),bool(ar),bool(db)};
    if(!reset) {
      const auto o=model.outputs(in);
      require(o.request_fire==bool(s0fire),"S0 fire mismatch",rows);
      require(o.response_valid==bool(resp),"response-valid mismatch",rows);
      require(o.miss==bool(miss),"S2 miss mismatch",rows);
      require(o.memory_request_valid==bool(req),"derived refill request mismatch",rows);
      if(req)require(o.memory_request_address==std::optional<uint64_t>(refaddr & ~uint64_t(63)),"refill address mismatch",rows);
      requests+=o.memory_request_fire;responses+=o.response_valid;data_beats+=db;kills+=k1||k2;
      checks+=4+bool(req);
    }
    model.clock(in);const auto& s=model.state();
    require(s.s1_valid==bool(s1v),"S1 valid mismatch",rows);
    require(s.s2_valid==bool(s2v),"S2 valid mismatch",rows);
    if(s2v)require(s.s2_hit==std::optional<bool>(s2hit),"required S2 hit mismatch",rows);
    if(!reset)require(s.previous_can_request==std::optional<bool>(canreg),"request-history mismatch",rows);
    require(bool(model.tags().pending())==bool(refvalid),"refill-valid mismatch",rows);
    require(model.tags().replacement_state()==rng,"replacement state mismatch",rows);
    if(model.tags().pending())require(model.tags().pending()->address==postaddr,"active refill-address mismatch",rows);
    checks+=5+bool(s2v)+bool(model.tags().pending());
    (void)done;++rows;
  }
  require(file.eof() && rows>130000,"incomplete continuous corpus",rows);
  require(requests==171 && data_beats==171*8 && responses>1000 && kills>0,"missing actual interface regimes",rows);
  // A trailing D beat steals S0 even for a resident, independent line.
  ShuttleCachePipeline control;
  control.clock({true});
  const auto idle=control.outputs({});
  require(idle.request_ready && !idle.response_valid && !idle.memory_request_valid,"reset interface",rows);
  // Data without a prior causal request is a refusal, not manufactured RAM.
  bool refused=false;
  try {ShuttleCachePipeline::Inputs in;in.memory_data_beat=true;control.clock(in);}catch(const std::logic_error& e) {
    refused=std::string(e.what())=="SHUTTLE_ICACHE_DATA_WITHOUT_REQUEST";
  }
  require(refused,"unsolicited refill accepted",rows);
  std::cout<<"PASS continuous actual RTL cache pipeline rows="<<rows<<" checks="<<checks<<" requests="<<requests
           <<" data_beats="<<data_beats<<" responses="<<responses<<" kills="<<kills<<"\n";
}
