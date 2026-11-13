#include "fased_service.hpp"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <deque>
#include <iostream>
#include <map>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
using namespace iris::fased;
namespace {
std::uint64_t checks=0,edges=0,restorations=0,hist_gap_edges=0;
bool corrupt=false;
void require(bool ok,const std::string& message){++checks;if(!ok)throw std::runtime_error(message);}
template<class F>void rejects(F f,const char* name){bool caught=false;try{f();}catch(const std::exception&){caught=true;}require(caught,name);}
std::uint64_t mask(unsigned bits){return bits==64?~std::uint64_t(0):(std::uint64_t(1)<<bits)-1;}
struct Ports {
  Model model;
  std::vector<Bits> in;
  std::map<std::string,unsigned> ii,oi;
  explicit Ports(Parameters p,unsigned seed):model(p,seed,{"fased-service-test","+owned=explicit"}){
    for(const auto& f:model.input_fields()){ii.emplace(f.name,ii.size());in.push_back({0,mask(f.width)});}
    for(const auto& f:model.output_fields())oi.emplace(f.name,oi.size());
  }
  void set(const std::string& name,std::uint64_t value){in.at(ii.at(name)).value=value;}
  void set_axi(const std::string& name,std::uint64_t value){set("tNasti_io_tNasti_"+name,value);}
  std::uint64_t get(const std::vector<std::uint64_t>& out,const std::string& name)const{return out.at(oi.at(name));}
  std::vector<std::uint64_t> evaluate(VerilatedContext& foreign){Verilated::threadContextp(&foreign);model.evaluate(in);require(Verilated::threadContextp()==&foreign,"evaluate leaked owner context");++restorations;auto out=model.sample();require(Verilated::threadContextp()==&foreign,"sample leaked owner context");++restorations;return out;}
  void commit(VerilatedContext& foreign){Verilated::threadContextp(&foreign);model.commit();require(Verilated::threadContextp()==&foreign,"commit leaked owner context");++restorations;++edges;}
};
struct Request {unsigned id,beats;};
struct Timed {std::uint64_t release;unsigned id;};
struct Reference {
  Parameters p;
  std::uint64_t cycle=0;
  unsigned reads=0,aws=0,ws=0,unpaired_w=0;
  bool read_current=false,write_current=false;
  std::deque<Timed> read_due,write_due;
  std::deque<unsigned> aw_ids;
  std::array<std::uint32_t,4> rh{},wh{};
  std::uint32_t nr=0,nw=0,nrb=0,nwb=0;
  explicit Reference(Parameters params):p(params){}
  static void histogram(std::array<std::uint32_t,4>& h,unsigned count){const unsigned upper[]={0,2,4,8};for(unsigned b=0;b<4;++b)if(count<=upper[b]){++h[b];return;}}
  // This reference is a transaction ledger, independent of generated queue
  // pointers or internal model state. AW and final-W may arrive in either order.
  void step(Ports& peer,const std::vector<std::uint64_t>& out,bool ar,bool aw,bool w,bool last,bool rr,bool br,bool rlast,unsigned rid,unsigned wid){
    auto expect=[&](const std::string& field,std::uint64_t value){auto actual=peer.get(out,"tNasti_io_"+field);require(actual==value,"edge "+std::to_string(cycle)+" "+field+" actual="+std::to_string(actual)+" expected="+std::to_string(value));};
    const bool ar_ready=reads<p.read_max_requests,aw_ready=aws<p.write_max_requests,w_ready=ws<p.write_max_requests;
    const bool arf=ar&&ar_ready,awf=aw&&aw_ready,wf=w&&w_ready;
    const bool rf=read_current&&rr,bf=write_current&&br;
    const bool read_slot=!read_current||(rf&&rlast),write_slot=!write_current||bf;
    auto next_read=read_due;
    if(arf)next_read.push_back({cycle+p.read_latency-1,rid});
    auto next_aw=aw_ids;if(awf)next_aw.push_back(wid);
    auto available_w=unpaired_w+unsigned(wf&&last);
    auto next_write=write_due;
    if(available_w&&!next_aw.empty()){
      next_write.push_back({cycle+p.write_latency-1,next_aw.front()});next_aw.pop_front();--available_w;
    }
    const bool rgrant=!next_read.empty()&&next_read.front().release+(corrupt?1:0)<=cycle&&read_slot;
    const bool bgrant=!next_write.empty()&&next_write.front().release<=cycle&&write_slot;
    expect("tNasti_ar_ready",ar_ready);expect("tNasti_aw_ready",aw_ready);expect("tNasti_w_ready",w_ready);
    expect("tNasti_r_valid",read_current);expect("tNasti_b_valid",write_current);
    expect("egressReq_r_valid",rgrant);expect("egressReq_b_valid",bgrant);
    if(rgrant)expect("egressReq_r_bits",next_read.front().id);
    if(bgrant)expect("egressReq_b_bits",next_write.front().id);
    expect("egressResp_rReady",rr);expect("egressResp_bReady",br);
    expect("mmReg_totalReads",nr);expect("mmReg_totalWrites",nw);expect("mmReg_totalReadBeats",nrb);expect("mmReg_totalWriteBeats",nwb);
    for(unsigned b=0;b<4;++b){expect("mmReg_readOutstandingHistogram_"+std::to_string(b),rh[b]);expect("mmReg_writeOutstandingHistogram_"+std::to_string(b),wh[b]);}
    histogram(rh,reads);histogram(wh,aws);if(reads>8||aws>8)++hist_gap_edges;
    reads+=unsigned(arf);reads-=unsigned(rf&&rlast);aws+=unsigned(awf);aws-=unsigned(bf);ws+=unsigned(wf&&last);ws-=unsigned(bf);
    nr+=arf;nw+=awf;nrb+=rf;nwb+=wf;
    read_current=(read_current&&!(rf&&rlast))||rgrant;
    write_current=(write_current&&!bf)||bgrant;
    if(rgrant)next_read.pop_front();if(bgrant)next_write.pop_front();
    read_due=std::move(next_read);write_due=std::move(next_write);aw_ids=std::move(next_aw);unpaired_w=available_w;++cycle;
  }
};
void scenario(Parameters params,unsigned seed,unsigned profile){
  VerilatedContext foreign;foreign.commandArgs(0,static_cast<const char**>(nullptr));foreign.randSeed(seed+99);
  Verilated::threadContextp(&foreign);Ports peer(params,seed);require(Verilated::threadContextp()==&foreign,"constructor leaked owner context");++restorations;
  rejects([&]{peer.model.sample();},"sample before evaluate accepted");
  rejects([&]{peer.model.commit();},"commit before evaluate accepted");
  rejects([&]{peer.model.evaluate(peer.in);},"active operation without committed reset accepted");
  peer.set("reset",1);peer.evaluate(foreign);peer.commit(foreign);peer.set("reset",0);
  Reference reference(params);std::mt19937 random(seed*173+profile);
  std::vector<Request> rq,wq;constexpr unsigned count=128;
  for(unsigned i=0;i<count;++i){rq.push_back({unsigned(random()%16),1+unsigned(random()%8)});wq.push_back({unsigned(random()%16),1+unsigned(random()%8)});}
  unsigned ari=0,awi=0,wi=0,wbeat=0;bool ar_held=false,aw_held=false,w_held=false;
  std::deque<Request> accepted_reads,accepted_writes;
  std::optional<Request> response_read,response_write;unsigned rbeat=0;
  for(unsigned cycle=0;cycle<24000;++cycle){
    bool ar=ar_held||(ari<count&&(random()%5!=0)),aw=aw_held||(awi<count&&(random()%4!=0)),w=w_held||(wi<count&&(random()%3!=0));
    // Profiles exercise AW-leading, W-leading and both-channel pairing.
    if(profile%3==0&&cycle<20&&!aw_held)aw=false;
    if(profile%3==1&&cycle<20&&!w_held)w=false;
    bool rr=cycle>=96&&(random()%4!=0),br=cycle>=80&&(random()%4!=0);
    if(profile%3==2&&cycle<160)rr=br=false;
    bool last=w&&wbeat+1==wq[wi].beats;
    unsigned rid=ari<count?rq[ari].id:0,wid=awi<count?wq[awi].id:0;
    bool rlast=response_read&&rbeat+1==response_read->beats;
    std::uint64_t rdata=response_read?(0x9e3779b97f4a7c15ULL*(response_read->id+1)^(rbeat*0x0102040810204081ULL)):0;
    peer.set_axi("ar_valid",ar);peer.set_axi("ar_bits_id",rid);peer.set_axi("ar_bits_len",ari<count?rq[ari].beats-1:0);peer.set_axi("ar_bits_burst",1);
    peer.set_axi("aw_valid",aw);peer.set_axi("aw_bits_id",wid);peer.set_axi("aw_bits_len",awi<count?wq[awi].beats-1:0);peer.set_axi("aw_bits_burst",1);
    peer.set_axi("w_valid",w);peer.set_axi("w_bits_last",last);peer.set_axi("r_ready",rr);peer.set_axi("b_ready",br);
    peer.set("tNasti_io_egressResp_rBits_data",rdata);peer.set("tNasti_io_egressResp_rBits_last",rlast);peer.set("tNasti_io_egressResp_rBits_id",response_read?response_read->id:0);peer.set("tNasti_io_egressResp_bBits_id",response_write?response_write->id:0);
    auto out=peer.evaluate(foreign);
    if(cycle%31==0){auto repeated=peer.evaluate(foreign);require(out==repeated,"repeat evaluate introduced a target edge");}
    const bool arf=ar&&reference.reads<params.read_max_requests,awf=aw&&reference.aws<params.write_max_requests,wf=w&&reference.ws<params.write_max_requests;
    ar_held=ar&&!arf;aw_held=aw&&!awf;w_held=w&&!wf;
    const bool rf=reference.read_current&&rr,bf=reference.write_current&&br;
    const bool rg=peer.get(out,"tNasti_io_egressReq_r_valid"),bg=peer.get(out,"tNasti_io_egressReq_b_valid");
    require(bool(response_read)==reference.read_current,"functional read fixture lost request ownership");require(bool(response_write)==reference.write_current,"functional write fixture lost request ownership");
    if(reference.read_current){require(peer.get(out,"tNasti_io_tNasti_r_bits_data")==rdata,"read functional data changed");require(peer.get(out,"tNasti_io_tNasti_r_bits_id")==response_read->id,"read response ID changed");require(peer.get(out,"tNasti_io_tNasti_r_bits_last")==rlast,"read response last changed");}
    if(reference.write_current)require(peer.get(out,"tNasti_io_tNasti_b_bits_id")==response_write->id,"write response ID changed");
    reference.step(peer,out,ar,aw,w,last,rr,br,rlast,rid,wid);
    if(arf)accepted_reads.push_back(rq[ari++]);if(awf)accepted_writes.push_back(wq[awi++]);
    if(wf&&++wbeat==wq[wi].beats){++wi;wbeat=0;}
    if(rf&&rlast){response_read.reset();rbeat=0;}else if(rf)++rbeat;
    if(bf)response_write.reset();
    if(rg){require(!accepted_reads.empty(),"unowned read release");response_read=accepted_reads.front();accepted_reads.pop_front();rbeat=0;require(peer.get(out,"tNasti_io_egressReq_r_bits")==response_read->id,"read FIFO order broken");}
    if(bg){require(!accepted_writes.empty(),"unowned write release");response_write=accepted_writes.front();accepted_writes.pop_front();require(peer.get(out,"tNasti_io_egressReq_b_bits")==response_write->id,"write FIFO order broken");}
    peer.commit(foreign);
    rejects([&]{peer.model.sample();},"stale sample accepted");rejects([&]{peer.model.commit();},"duplicate commit accepted");
    if(ari==count&&awi==count&&wi==count&&!reference.reads&&!reference.aws&&!reference.ws){require(reference.nr==count&&reference.nw==count,"missing transactions");return;}
  }
  throw std::runtime_error("transaction ledger did not drain");
}
void negative_controls(){
  rejects([]{Model m({0,1,1,1},1,{"test"});},"zero latency accepted");
  rejects([]{Model m({1,1,17,1},1,{"test"});},"max requests beyond physical capacity accepted");
  rejects([]{Model m({1,1,1,0},1,{"test"});},"unqualified zero admission accepted");
  VerilatedContext foreign;Ports peer({1,2,16,16},113);peer.set("reset",1);peer.evaluate(foreign);peer.commit(foreign);peer.set("reset",0);
  auto bad=peer.in;bad.pop_back();rejects([&]{peer.model.evaluate(bad);},"wrong field count accepted");
  bad=peer.in;bad[0].known=0;rejects([&]{peer.model.evaluate(bad);},"unknown reset accepted");
  for(unsigned i=0;i<peer.in.size();++i){bad=peer.in;bad[i].known&=~std::uint64_t(1);rejects([&]{peer.model.evaluate(bad);},"unknown input accepted");}
  peer.set_axi("ar_valid",1);peer.set_axi("ar_bits_burst",2);rejects([&]{peer.model.evaluate(peer.in);},"WRAP burst accepted");
  peer.set_axi("ar_bits_burst",1);peer.set_axi("ar_bits_len",8);rejects([&]{peer.model.evaluate(peer.in);},"nine-beat read accepted");
  peer.set_axi("ar_valid",0);peer.set_axi("aw_valid",1);peer.set_axi("aw_bits_burst",1);peer.set_axi("aw_bits_len",8);rejects([&]{peer.model.evaluate(peer.in);},"nine-beat write accepted");
  peer.set_axi("aw_valid",0);peer.set_axi("ar_valid",1);
  peer.set_axi("ar_bits_burst",0);peer.set_axi("ar_bits_len",1);rejects([&]{peer.model.evaluate(peer.in);},"multi-beat FIXED burst accepted");
  peer.set_axi("ar_bits_len",0);peer.set_axi("ar_bits_id",16);rejects([&]{peer.model.evaluate(peer.in);},"ID truncation accepted");
  peer.set_axi("ar_bits_id",1);peer.evaluate(foreign);peer.commit(foreign); // legal fixed len0
}
void reset_inflight(){
  VerilatedContext foreign;Ports peer({30,33,16,16},31);
  peer.set("reset",1);peer.evaluate(foreign);peer.commit(foreign);peer.set("reset",0);
  for(unsigned i=0;i<8;++i){peer.set_axi("ar_valid",1);peer.set_axi("ar_bits_burst",1);peer.set_axi("ar_bits_len",7);peer.set_axi("ar_bits_id",i);peer.set_axi("aw_valid",1);peer.set_axi("aw_bits_burst",1);peer.set_axi("aw_bits_id",i);peer.set_axi("w_valid",1);peer.set_axi("w_bits_last",1);peer.evaluate(foreign);peer.commit(foreign);}
  peer.set_axi("ar_valid",0);peer.set_axi("aw_valid",0);peer.set_axi("w_valid",0);peer.set("reset",1);peer.evaluate(foreign);peer.commit(foreign);peer.set("reset",0);
  Reference ref({30,33,16,16});
  for(unsigned i=0;i<80;++i){auto out=peer.evaluate(foreign);ref.step(peer,out,false,false,false,false,false,false,false,0,0);peer.commit(foreign);}
}
void interleaved_instances(){
  constexpr unsigned count=320;
  auto trace=[](unsigned seed,bool interleave){
    VerilatedContext foreign;foreign.commandArgs(0,static_cast<const char**>(nullptr));
    Verilated::threadContextp(&foreign);Ports first({3,7,16,16},seed);Ports second({30,2,4,8},seed+113);
    require(Verilated::threadContextp()==&foreign,"second constructor clobbered caller context");
    std::vector<std::uint64_t> rows;rows.reserve(count*32);
    auto cycle=[&](Ports& peer,unsigned n,bool capture){
      peer.set("reset",n<2);peer.set_axi("ar_valid",n==2);peer.set_axi("ar_bits_id",3);peer.set_axi("ar_bits_burst",1);peer.set_axi("ar_bits_len",0);
      peer.set_axi("r_ready",n>80);peer.set("tNasti_io_egressResp_rBits_last",1);peer.set("tNasti_io_egressResp_rBits_id",3);peer.set("tNasti_io_egressResp_rBits_data",0x123456789ULL);
      auto out=peer.evaluate(foreign);
      if(capture&&n>=2)for(unsigned k=0;k<out.size();++k){auto name=peer.model.output_fields()[k].name;std::string field(name);if(field.find("egressReq_r_bits")!=std::string::npos&&!peer.get(out,"tNasti_io_egressReq_r_valid"))continue;if(field.find("egressReq_b_bits")!=std::string::npos&&!peer.get(out,"tNasti_io_egressReq_b_valid"))continue;rows.push_back(out[k]);}
      peer.commit(foreign);
    };
    for(unsigned n=0;n<count;++n){if(interleave&&n%2==0)cycle(second,n,false);cycle(first,n,true);if(interleave&&n%2!=0)cycle(second,n,false);}
    return rows;
  };
  for(unsigned seed:{1U,31U,113U})require(trace(seed,false)==trace(seed,true),"foreign model interleave altered qualified fields");
}
void peak_bandwidth(){
  VerilatedContext foreign;Ports peer({30,30,16,16},7);
  peer.set("reset",1);peer.evaluate(foreign);peer.commit(foreign);peer.set("reset",0);
  unsigned read_beats=0,write_responses=0,read_releases=0,write_releases=0;
  for(unsigned cycle=0;cycle<180;++cycle){
    peer.set_axi("ar_valid",cycle<16);peer.set_axi("ar_bits_id",cycle%16);peer.set_axi("ar_bits_len",7);peer.set_axi("ar_bits_burst",1);
    peer.set_axi("aw_valid",cycle<16);peer.set_axi("aw_bits_id",cycle%16);peer.set_axi("aw_bits_len",0);peer.set_axi("aw_bits_burst",1);
    peer.set_axi("w_valid",cycle<16);peer.set_axi("w_bits_last",1);peer.set_axi("r_ready",1);peer.set_axi("b_ready",1);
    const bool rvalid=cycle>=30&&cycle<158,bvalid=cycle>=30&&cycle<46;
    peer.set("tNasti_io_egressResp_rBits_id",rvalid?(cycle-30)/8:0);peer.set("tNasti_io_egressResp_rBits_last",rvalid&&(cycle-30)%8==7);peer.set("tNasti_io_egressResp_rBits_data",0x123456789abcdef0ULL);
    peer.set("tNasti_io_egressResp_bBits_id",bvalid?cycle-30:0);
    auto out=peer.evaluate(foreign);require(peer.get(out,"tNasti_io_tNasti_r_valid")==rvalid,"R burst bandwidth has an extra/missing target edge");require(peer.get(out,"tNasti_io_tNasti_b_valid")==bvalid,"B bandwidth has an extra/missing target edge");
    const bool rrelease=cycle>=29&&cycle<=149&&(cycle-29)%8==0,brelease=cycle>=29&&cycle<45;
    require(peer.get(out,"tNasti_io_egressReq_r_valid")==rrelease,"read releaser registered compensation differs");require(peer.get(out,"tNasti_io_egressReq_b_valid")==brelease,"write releaser registered compensation differs");
    if(rrelease)require(peer.get(out,"tNasti_io_egressReq_r_bits")==read_releases++,"peak read ID order differs");
    if(brelease)require(peer.get(out,"tNasti_io_egressReq_b_bits")==write_releases++,"peak write ID order differs");
    read_beats+=rvalid;write_responses+=bvalid;peer.commit(foreign);
  }
  require(read_beats==128&&write_responses==16&&read_releases==16&&write_releases==16,"peak witness incomplete");
}
}
int main(int argc,char**argv){try{
  corrupt=argc==2&&std::string(argv[1])=="--wrong-latency";
  unsigned profile=0;
  for(unsigned seed:{1U,7U,31U,113U})for(unsigned latency:{1U,2U,3U,30U,37U})for(unsigned maximum:{1U,2U,4U,8U,16U})scenario({latency,latency+2,maximum,maximum},seed,profile++);
  negative_controls();reset_inflight();interleaved_instances();peak_bandwidth();require(hist_gap_edges>0,"occupancy>8 histogram witness missing");
  std::cout<<"{\"status\":\"passed\",\"profiles\":"<<profile<<",\"checks\":"<<checks<<",\"target_edges\":"<<edges<<",\"caller_context_restorations\":"<<restorations<<",\"non_exhaustive_histogram_edges\":"<<hist_gap_edges<<",\"peak_read_beats_per_target_edge\":1,\"functional_host_service\":false,\"calibration_usable\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
