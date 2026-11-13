#include "fased_backing_service_v2.hpp"
#include "verilated.h"
#include <iostream>
#include <random>
#include <string>
using namespace iris::fased_backing;
using Service=iris::fased_backing::ServiceV2;
namespace {
std::uint64_t checks=0,edges=0,bytes_checked=0;
bool wrong_latency=false,wrong_id=false,bad_wlast=false,bad_known=false,bad_address=false,unknown_address=false;
void need(bool value,const char*text){++checks;if(!value)throw std::runtime_error(text);}
constexpr std::uint64_t base=0x80010000;
void held_phase_controls(bool unprepared){
  Service s({2,2,1,1},1,{"fixed-point-phase-controls"},{{base,64}},Visibility::ExternalFencedDisjoint);
  std::vector<Byte>initial(64,{0x51,255});s.initialize(base,initial);
  Inputs in;in.reset=known(1,1);s.evaluate(in);s.commit();in.reset=known(1,0);
  in.aw_valid=known(1,1);in.aw=Request::concrete(base,3,0);s.evaluate(in);need(s.sample().aw_ready,"phase control AW ready");s.commit();
  const auto before=s.committed_edges();s.evaluate_control(in);
  // Previous-edge AWvalid is intentionally stale while a peer recomputes its
  // combinational output. It must not acquire a second owner.
  need(s.ledger().write_count()==1&&s.committed_edges()==before,"provisional control created ownership");
  if(unprepared){s.commit();throw std::runtime_error("unprepared commit was accepted");}
  bool refused=false;try{s.commit();}catch(const std::runtime_error&e){refused=std::string(e.what()).find("STALE_COMMIT")!=std::string::npos;}
  need(refused&&s.committed_edges()==before,"unprepared source edge committed");
  in.aw_valid=known(1,0);s.evaluate_control(in);s.prepare();s.commit();need(s.ledger().write_count()==1,"settled phase lost original AW");
  in.w_valid=known(1,1);in.w=WBeat::concrete(0x1112131415161718ULL,255,true);s.evaluate(in);s.commit();
  in.w_valid=known(1,0);in.b_ready=known(1,1);
  for(unsigned n=0;n<20&&!s.ledger().idle();++n){s.evaluate(in);s.commit();}
  need(s.ledger().idle(),"phase control original AW/W never completed");
  s.acknowledge_external_fence();in.ar_valid=known(1,1);in.ar=Request::concrete(base,4,0);in.ar.address.known^=1;
  s.evaluate_control(in);refused=false;try{s.prepare();}catch(const std::runtime_error&e){refused=std::string(e.what()).find("UNKNOWN_REQUIRED_FIELD")!=std::string::npos;}
  need(refused&&s.ledger().idle(),"settled unknown request escaped preparation");
  refused=false;try{s.sample();}catch(const std::runtime_error&e){refused=std::string(e.what()).find("STALE_SAMPLE")!=std::string::npos;}
  need(refused,"failed settled preparation remained sampleable");
}
struct Req {std::uint64_t address;unsigned id,len;};
struct Read {Req req;std::vector<std::uint64_t>data;unsigned beat=0;};
struct Write {Req req;std::vector<WBeat>data;};
struct Due {std::uint64_t time;unsigned id;};
struct Oracle {
  iris::fased::Parameters p;
  unsigned reads=0,aws=0,ws=0,unpaired_w=0;
  std::uint64_t cycle=0,nr=0,nw=0,nrb=0,nwb=0;
  bool rvalid=false,bvalid=false;
  std::deque<Due>rd,wd;
  std::deque<unsigned>awids;
  std::deque<Read>read_owners;
  std::deque<Req>aw;
  std::deque<std::vector<WBeat>>complete;
  std::deque<Write>write_owners;
  std::vector<WBeat>partial;
  std::optional<Read>active_r;
  std::optional<Write>active_b;
  std::vector<std::uint8_t>memory;
  explicit Oracle(iris::fased::Parameters params):p(params),memory(16384){for(unsigned i=0;i<memory.size();++i)memory[i]=std::uint8_t((i*17)^0xd9);}
  std::uint64_t word(std::uint64_t a)const{std::uint64_t v=0;for(unsigned b=0;b<8;++b)v|=std::uint64_t(memory.at(a-base+b))<<(8*b);return v;}
  void step(Service&s,const Inputs&in,const Outputs&o){
    need(o.ar_ready==(reads<p.read_max_requests),"source AR admission edge");need(o.aw_ready==(aws<p.write_max_requests),"source AW admission edge");need(o.w_ready==(ws<p.write_max_requests),"source W admission edge");
    need(o.r_valid==rvalid&&o.b_valid==bvalid,"source registered R/B phase");need(bool(active_r)==rvalid&&bool(active_b)==bvalid,"independent functional owner phase");
    if(active_r){need(o.r_id==active_r->req.id&&o.r_data==active_r->data.at(active_r->beat)&&o.r_last==(active_r->beat==active_r->req.len),"actual R ID/data/last independent byte oracle");}
    if(active_b)need(o.b_id==active_b->req.id,"actual B ID independent owner");
    need(s.source_value("tNasti_io_mmReg_totalReads")==nr&&s.source_value("tNasti_io_mmReg_totalWrites")==nw&&s.source_value("tNasti_io_mmReg_totalReadBeats")==nrb&&s.source_value("tNasti_io_mmReg_totalWriteBeats")==nwb,"actual source accepted transaction/beat counters");
    const bool ar=in.ar_valid.value&&o.ar_ready,af=in.aw_valid.value&&o.aw_ready,w=in.w_valid.value&&o.w_ready;
    const bool rf=rvalid&&in.r_ready.value,bf=bvalid&&in.b_ready.value;
    const bool last=active_r&&active_r->beat==active_r->req.len;
    if(ar){rd.push_back({cycle+p.read_latency-1,unsigned(in.ar.id.value)});Read owner{{in.ar.address.value,unsigned(in.ar.id.value),unsigned(in.ar.len.value)},{}};for(unsigned beat=0;beat<=owner.req.len;++beat)owner.data.push_back(word(owner.req.address+beat*8));read_owners.push_back(std::move(owner));}
    if(af){awids.push_back(in.aw.id.value);aw.push_back({in.aw.address.value,unsigned(in.aw.id.value),unsigned(in.aw.len.value)});}
    if(w){partial.push_back(in.w);if(in.w.last.value){complete.push_back(std::move(partial));partial.clear();++unpaired_w;}}
    if(unpaired_w&&!awids.empty()){wd.push_back({cycle+p.write_latency-1,awids.front()});awids.pop_front();--unpaired_w;}
    while(!aw.empty()&&!complete.empty()){need(complete.front().size()==aw.front().len+1,"oracle independent AW/W burst pairing");write_owners.push_back({aw.front(),std::move(complete.front())});aw.pop_front();complete.pop_front();}
    const bool rg=(!rvalid||(rf&&last))&&!rd.empty()&&rd.front().time+(wrong_latency?1:0)<=cycle;
    const bool bg=(!bvalid||bf)&&!wd.empty()&&wd.front().time<=cycle;
    need(s.source_value("tNasti_io_egressReq_r_valid")==rg&&s.source_value("tNasti_io_egressReq_b_valid")==bg,"source due/registered-egress latency phase");
    if(rf){if(last)active_r.reset();else++active_r->beat;}
    if(bf){const auto&o=*active_b;for(unsigned beat=0;beat<o.data.size();++beat)for(unsigned byte=0;byte<8;++byte)if(o.data[beat].strobe.value&(1u<<byte))memory.at(o.req.address-base+8*beat+byte)=o.data[beat].data.value>>(8*byte);active_b.reset();}
    if(rg){need(!read_owners.empty()&&read_owners.front().req.id==rd.front().id&&s.source_value("tNasti_io_egressReq_r_bits")==rd.front().id,"actual read egress FIFO/ID");active_r=std::move(read_owners.front());read_owners.pop_front();rd.pop_front();}
    if(bg){need(!write_owners.empty()&&write_owners.front().req.id==wd.front().id&&s.source_value("tNasti_io_egressReq_b_bits")==wd.front().id,"actual write egress FIFO/ID");active_b=std::move(write_owners.front());write_owners.pop_front();wd.pop_front();}
    reads+=ar;reads-=rf&&last;aws+=af;aws-=bf;ws+=w&&in.w.last.value;ws-=bf;
    nr+=ar;nw+=af;nrb+=rf;nwb+=w;rvalid=(rvalid&&!(rf&&last))||rg;bvalid=(bvalid&&!bf)||bg;++cycle;
  }
};
void scenario(unsigned latency,unsigned cap,unsigned seed,unsigned profile){
  iris::fased::Parameters params{latency,profile%2?latency+2:latency,cap,cap};VerilatedContext foreign;Verilated::threadContextp(&foreign);
  Service service(params,seed,{"FASED-write-backing-source-control"},{{base,16384}},Visibility::ExternalFencedDisjoint);need(Verilated::threadContextp()==&foreign,"service ctor context");
  need(std::string(service.source_identity())=="1d1d497a614cda9e0076368589246bceaeb2cb5dcc20c82d951c6f2566257f85","fixed frozen context SDK identity");
  Oracle ref(params);std::vector<Byte>initial;for(auto v:ref.memory)initial.push_back({v,255});service.initialize(base,initial);
  Inputs in;in.reset=known(1,1);
  for(unsigned i=0;i<2;++i){service.evaluate(in);need(Verilated::threadContextp()==&foreign,"reset evaluate context");service.commit();need(Verilated::threadContextp()==&foreign,"reset commit context");++edges;}
  in.reset=known(1,0);std::mt19937 rng(seed*37+profile);constexpr unsigned count=64;
  std::vector<Req>requests;std::vector<std::vector<WBeat>>write_data;
  for(unsigned n=0;n<count;++n){requests.push_back({base+8192+64*n,unsigned(rng()%16),n%3==0?7u:n%3==1?0u:3u});std::vector<WBeat>beats;for(unsigned b=0;b<=requests.back().len;++b)beats.push_back(WBeat::concrete(std::uint64_t(rng())|(std::uint64_t(rng())<<32),rng()%256,b==requests.back().len));write_data.push_back(std::move(beats));}
  unsigned ai=0,wi=0,wb=0,ri=0,write_start=0;bool fence=false,initial_reads_done=false;
  for(unsigned n=0;n<30000;++n){
    if(ri==64&&ref.reads==0&&!initial_reads_done){initial_reads_done=true;write_start=n;}
    const bool write_phase=ai<count||wi<count||ref.aws;
    if(!write_phase&&!fence&&service.ledger().idle()){need(service.ledger().write_count()==0&&service.ledger().complete_w_count()==0,"all write responses before checkpoint");service.acknowledge_external_fence();fence=true;}
    // Complete initial reads before W-before-AW exploration: unaddressed W
    // data cannot be proven disjoint. The external fence then precedes the64
    // writeback readouts, never an overlapping live RAW.
    in.ar_valid=known(1,ri<128&&(ri<64||fence));
    if(ri<128){const auto r=ri<64?Req{base+64*ri,unsigned(ri%16),requests[ri].len}:requests[ri-64];in.ar=Request::concrete(r.address,r.id,r.len);}
    in.aw_valid=known(1,initial_reads_done&&ai<count&&(profile%3!=0||n-write_start>=17));if(ai<count)in.aw=Request::concrete(requests[ai].address,requests[ai].id,requests[ai].len);
    in.w_valid=known(1,initial_reads_done&&wi<count&&(profile%3!=1||n-write_start>=19));if(wi<count)in.w=write_data[wi][wb];
    if(bad_wlast&&wi==0&&wb==0)in.w.last=known(1,1);
    if(bad_known&&wi==0&&wb==0){in.w.strobe=known(8,1);in.w.data.known&=~std::uint64_t(255);}
    if(bad_address&&ai==0)in.aw.address=known(33,base+16384);
    if(unknown_address&&ri==0)in.ar.address.known^=1;
    in.r_ready=known(1,n>=70&&rng()%4!=0);in.b_ready=known(1,n>=83&&rng()%3!=0);
    service.evaluate(in);need(Verilated::threadContextp()==&foreign,"source service evaluate restores context");auto out=service.sample();
    if(n%29==0){service.evaluate(in);const auto again=service.sample();need(out.r_valid==again.r_valid&&out.b_valid==again.b_valid&&out.r_data==again.r_data,"repeat evaluate added an edge");}
    const bool ar=in.ar_valid.value&&out.ar_ready,af=in.aw_valid.value&&out.aw_ready,w=in.w_valid.value&&out.w_ready;
    if(wrong_id&&out.r_valid)out.r_id^=1;
    ref.step(service,in,out);service.commit();need(Verilated::threadContextp()==&foreign,"source service commit restores context");++edges;
    if(ar)++ri;
    if(af)++ai;
    if(w&&++wb==write_data[wi].size()){++wi;wb=0;}
    if(ri==128&&ai==count&&wi==count&&service.ledger().idle()){
      for(unsigned b=0;b<ref.memory.size();++b){auto actual=service.ledger().inspect(base+b);need(actual.value==ref.memory[b]&&actual.known==255,"final all-byte independent source differential");++bytes_checked;}
      need(service.committed_edges()==service.ledger().committed_edges(),"source/functional clock ownership");return;
    }
  }
  throw std::runtime_error("finite source service failed to drain");
}
}
int main(int argc,char**argv){try{const auto mode=argc==2?std::string(argv[1]):"";held_phase_controls(mode=="--unprepared");wrong_latency=mode=="--wrong-latency";wrong_id=mode=="--wrong-id";bad_wlast=mode=="--bad-wlast";bad_known=mode=="--unknown-byte";bad_address=mode=="--unmapped";unknown_address=mode=="--unknown-address";unsigned profile=0;
 for(unsigned seed:{1u,17u})for(unsigned latency:{1u,2u,30u,37u})for(unsigned cap:{1u,4u,16u})scenario(latency,cap,seed,profile++);
 std::cout<<"{\"pass\":true,\"profiles\":"<<profile<<",\"checks\":"<<checks<<",\"actual_FASED_target_edges\":"<<edges<<",\"independent_all_byte_checks\":"<<bytes_checked<<",\"full_host_token_bridge\":false,\"hardware_or_performance_labels\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
