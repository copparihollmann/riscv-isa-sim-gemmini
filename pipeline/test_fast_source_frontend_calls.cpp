// New continuous dual-peer driver; immutable alignment oracle remains unchanged.
#include "frontend_rtl_peer.hpp"
#include "fast_source_frontend.hpp"
#include "frontend_branch.hpp"
#include "shuttle_issue.hpp"
#include <array>
#include <deque>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <vector>
class DifferentialFrontend {
 using Ref=iris::frontend::SavedShuttleFrontend;
 Ref ref_;iris::frontend::FastSourceFrontend fast_;uint64_t edge_=0,checks_=0;
 public:
 using Inputs=Ref::Inputs;using Outputs=Ref::Outputs;using Uop=Ref::Uop;using DataBeat=Ref::DataBeat;
 DifferentialFrontend(uint64_t seed,unsigned reset):ref_(seed,reset),fast_(seed,reset){}
 Outputs evaluate(const Inputs& in) {
  auto a=ref_.evaluate(in),b=fast_.evaluate(in);
  auto eq=[&](auto x,auto y,const char* name){++checks_;if(x!=y)throw std::runtime_error(std::string(name)+" edge="+std::to_string(edge_)+" ref="+std::to_string(x)+" fast="+std::to_string(y));};
  eq(a.memory_request_valid,b.memory_request_valid,"A.valid");if(a.memory_request_valid)eq(a.memory_request_address,b.memory_request_address,"A.address");
  for(unsigned i=0;i<2;++i){const auto&x=a.queue[i];const auto&y=b.queue[i];eq(x.valid,y.valid,"Q.valid");if(!x.valid)continue;
   eq(x.pc,y.pc,"Q.pc");eq(x.raw,y.raw,"Q.raw");eq(x.expanded,y.expanded,"Q.expanded");eq(x.compressed,y.compressed,"Q.rvc");eq(x.edge_instruction,y.edge_instruction,"Q.edge");
   eq(x.exception,y.exception,"Q.exception");if(x.exception)eq(x.exception_cause,y.exception_cause,"Q.cause");
   eq(x.prediction_valid,y.prediction_valid,"Q.prediction");if(x.prediction_valid)eq(x.predicted_pc,y.predicted_pc,"Q.target");
   eq(x.btb_valid,y.btb_valid,"Q.btb_valid");if(x.btb_valid)eq(x.btb_entry,y.btb_entry,"Q.btb_entry");
   eq(x.bht_history,y.bht_history,"Q.history");eq(x.bht_value,y.bht_value,"Q.counter");eq(x.ras_head,y.ras_head,"Q.ras_head");eq(x.small_forward_branch,y.small_forward_branch,"Q.sfb");
  }
  return a;
 }
 void commit(){ref_.commit();fast_.commit();++edge_;}
};
using Peer=DifferentialFrontend;
using Branch=iris::frontend::ShuttleBranch;

struct Refill{uint64_t line;unsigned edge,beat=0;};
struct Resolution{unsigned edge;std::array<Branch::Uop,2>packet;Peer::Uop source;};
uint32_t jal(unsigned rd,int imm){const unsigned v=unsigned(imm);return((v&0x100000)<<11)|((v&0x7fe)<<20)|((v&0x800)<<9)|(v&0xff000)|(rd<<7)|0x6f;}
int main(int argc,char**argv){
 if(argc!=3)throw std::invalid_argument("depth seed required");
 unsigned depth=std::stoul(argv[1]),seed=std::stoul(argv[2]);if(depth<1||depth>12)throw std::invalid_argument("depth1..12");
 constexpr uint64_t start=0x80002000;Peer peer(seed,16);std::optional<Refill>refill;std::deque<Resolution>pending;std::vector<uint64_t>returns;
 uint64_t expected=start;unsigned rounds=0,calls=0,rets=0,resolutions=0,requests=0,accepted=0,mispredicts=0;
 auto word=[&](uint64_t addr){
  if(addr<start||addr>=start+(depth+1)*32)return uint32_t(0x00000013);
  const auto off=addr-start,level=off/32,within=off%32;
  if(within==0&&level<depth)return jal(1,32);
  if((within==0&&level==depth)||(within==4&&level>0))return uint32_t(0x00008067);
  if(within==4&&level==0)return jal(0,-4);
  return uint32_t(0x00150513);
 };
 auto byte=[&](uint64_t addr){return uint8_t(word(addr&~uint64_t(3))>>(8*(addr&3)));};
 for(unsigned cycle=0;cycle<200000&&rounds<128;++cycle){
  Peer::Inputs in;in.memory_request_ready=cycle%11!=0;
  if(cycle<6)in.ras={true,cycle,0x80003000+8*cycle};
  if(cycle==1024){in.redirect_flush=in.redirect_valid=true;in.redirect_pc=start;in.redirect_ras_head=5;}
  if(!pending.empty()&&pending.front().edge==cycle){auto r=pending.front();pending.pop_front();const auto decision=Branch::resolve(r.packet);const auto&q=r.source;
   const auto&u=r.packet[decision.lane];const unsigned rd=(u.expanded>>7)&31,rs1=(u.expanded>>15)&31;
   const unsigned type=(u.jal||u.jalr)&&(rd&1)?2:u.jalr&&(rs1==1||rs1==5)?3:1;
   if(decision.predictor_update){in.btb={true,true,decision.mispredict,q.btb_valid?q.btb_entry:32,type,decision.fetch_pc,decision.next_pc&((1ULL<<39)-1),decision.branch_pc};in.bht={true,false,decision.taken,decision.mispredict,q.bht_history,q.bht_value,decision.fetch_pc};}
   if(decision.ras_update)in.ras={true,decision.ras_update_head,decision.ras_address};
   if(decision.redirect){in.redirect_flush=in.redirect_valid=true;in.redirect_pc=decision.next_pc;in.redirect_ras_head=decision.redirect_ras_head;expected=decision.next_pc;++mispredicts;}
   ++resolutions;
  }
  const bool returning=refill&&cycle>=refill->edge+3&&cycle%7!=0;
  if(returning){uint64_t data=0;for(unsigned i=0;i<8;++i)data|=uint64_t(byte(refill->line+refill->beat*8+i))<<(8*i);in.memory_data=Peer::DataBeat{data};}
  auto out=peer.evaluate(in);std::vector<iris::shuttle::Uop>decoded;
  if(cycle>=1024&&!in.redirect_flush&&cycle%9!=0){uint64_t next=expected;
   for(unsigned lane=0;lane<2;++lane){const auto&q=out.queue[lane];if(!q.valid||q.pc!=next)break;if(q.exception)throw std::runtime_error("unexpectedfetchfault");
    auto u=iris::shuttle::decode_scalar(q.expanded,q.raw,{q.prediction_valid?iris::shuttle::Signal::yes:iris::shuttle::Signal::no,iris::shuttle::Signal::no,false});u.sfb_branch=q.small_forward_branch?iris::shuttle::Signal::yes:iris::shuttle::Signal::no;decoded.push_back(u);next=q.pc+4;if(u.cfi())break;
   }
  }
  const auto plan=iris::shuttle::select_rrd(decoded,iris::shuttle::IssueSignals::empty_pipeline_fixture());unsigned count=plan.ready_prefix;
  if(count){in.ready0=true;in.ready1=count==2;std::array<Branch::Uop,2>packet{};std::optional<Peer::Uop>cfi;
   for(unsigned lane=0;lane<count;++lane){const auto&q=out.queue[lane];const auto&u=decoded[lane];auto&b=packet[lane];b.valid=true;b.expanded=q.expanded;b.pc=q.pc;b.compressed=q.compressed;b.jal=u.has(iris::shuttle::JAL);b.jalr=u.has(iris::shuttle::JALR);b.predicted_valid=q.prediction_valid;b.predicted_pc=q.predicted_pc;b.ras_head=q.ras_head;b.sfb_branch=q.small_forward_branch;
    if(b.jal){b.wdata=q.pc+4;if(((q.expanded>>7)&31)==1){returns.push_back(q.pc+4);expected=q.pc+32;++calls;}else{expected=start;++rounds;}}
    else if(b.jalr){if(returns.empty())throw std::runtime_error("stimulusreturnunderflow");b.wdata=returns.back();returns.pop_back();expected=b.wdata;++rets;}
    else expected=q.pc+4;
    if(u.cfi())cfi=q;++accepted;
   }
   if(cfi)pending.push_back({cycle+2,packet,*cfi});
  }
  out=peer.evaluate(in);const bool request=out.memory_request_valid&&in.memory_request_ready;peer.commit();
  if(returning&&++refill->beat==8)refill.reset();
  if(request){if(refill)throw std::runtime_error("overlappingrefill");refill=Refill{out.memory_request_address,cycle,0};++requests;}
 }
 if(rounds!=128||calls!=depth*128||rets!=calls||!returns.empty())throw std::runtime_error("incompletecalls rounds="+std::to_string(rounds)+" calls="+std::to_string(calls)+" returns="+std::to_string(rets));
 std::cout<<"{\"pass\":true,\"depth\":"<<depth<<",\"seed\":"<<seed<<",\"rounds\":"<<rounds<<",\"calls\":"<<calls<<",\"returns\":"<<rets<<",\"mispredicts\":"<<mispredicts<<",\"accepted\":"<<accepted<<",\"requests\":"<<requests<<"}\n";
}
