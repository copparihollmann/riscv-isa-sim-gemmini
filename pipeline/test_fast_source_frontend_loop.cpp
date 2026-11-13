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
struct Resolution{unsigned edge;std::array<Branch::Uop,2> packet;Peer::Uop source;};
int main(int argc,char**argv){
 if(argc!=4)throw std::invalid_argument("loop-PC N seed required");
 const uint64_t start=std::stoull(argv[1],nullptr,0);const unsigned n=std::stoul(argv[2]),seed=std::stoul(argv[3]);
 if(start&1||n<32)throw std::invalid_argument("alignedPC N>=32");
 Peer peer(seed,16);std::optional<Refill> refill;std::deque<Resolution> pending;std::vector<unsigned> branches;
 uint64_t expected=start;unsigned iteration=0,retiredbranches=0,requests=0,mispredicts=0,accepted=0,pairs=0,empty=0,blocked=0;
 auto byte=[&](uint64_t address)->uint8_t{constexpr std::array<uint8_t,8> code={0x0d,0x05,0x85,0x27,0xe3,0x9e,0xf5,0xfe};return address>=start&&address<start+8?code[address-start]:(address&1?0:1);};
 for(unsigned cycle=0;cycle<200000&&retiredbranches<n;++cycle){
  Peer::Inputs in;in.memory_request_ready=true;
  if(cycle==1024){in.redirect_flush=in.redirect_valid=true;in.redirect_pc=start;}
  if(!pending.empty()&&pending.front().edge==cycle){auto r=pending.front();pending.pop_front();const auto decision=Branch::resolve(r.packet);const auto&q=r.source;
   if(decision.predictor_update){in.btb={true,true,decision.mispredict,q.btb_valid?q.btb_entry:32,0,decision.fetch_pc,decision.next_pc&((1ULL<<39)-1),decision.branch_pc};in.bht={true,true,decision.taken,decision.mispredict,q.bht_history,q.bht_value,decision.fetch_pc};}
   if(decision.redirect){in.redirect_flush=in.redirect_valid=true;in.redirect_pc=decision.next_pc;in.redirect_ras_head=decision.redirect_ras_head;++mispredicts;expected=decision.next_pc;}
   ++retiredbranches;
  }
  const bool returning=refill&&cycle>=refill->edge+3;
  if(returning){uint64_t v=0;for(unsigned b=0;b<8;++b)v|=uint64_t(byte(refill->line+refill->beat*8+b))<<(8*b);in.memory_data=Peer::DataBeat{v};}
  auto out=peer.evaluate(in);if(std::getenv("IRIS_ALIGNMENT_DEBUG")&&cycle<100)std::cerr<<"edge="<<cycle<<" expected="<<std::hex<<expected<<" q0="<<out.queue[0].pc<<" q1="<<out.queue[1].pc<<std::dec<<" valid="<<out.queue[0].valid<<out.queue[1].valid<<" iter="<<iteration<<" pending="<<pending.size()<<" redir="<<in.redirect_flush<<"\n";std::vector<iris::shuttle::Uop> decoded;
  if(!in.redirect_flush&&iteration<n){uint64_t next=expected;
   for(unsigned lane=0;lane<2;++lane){auto&q=out.queue[lane];if(!q.valid||q.pc!=next)break;
    if(q.exception)throw std::runtime_error("unexpectedinstructionfault");const auto raw=q.compressed?uint16_t(q.raw):q.raw;
    if(q.pc==start&&raw!=0x050d||q.pc==start+2&&raw!=0x2785||q.pc==start+4&&raw!=0xfef59ee3)throw std::runtime_error("instructionbytesdiffer");
    auto u=iris::shuttle::decode_scalar(q.expanded,raw,{q.prediction_valid?iris::shuttle::Signal::yes:iris::shuttle::Signal::no,iris::shuttle::Signal::no,false});u.sfb_branch=q.small_forward_branch?iris::shuttle::Signal::yes:iris::shuttle::Signal::no;decoded.push_back(u);
    // Branch outcome is the only finite stimulus; operands are the loop count.
    if(u.has(iris::shuttle::BRANCH)){next=iteration+1<n?start:start+8;if(lane==0&&iteration+1==n)break;}else next=q.pc+(q.compressed?2:4);
   }
  }
  const auto plan=iris::shuttle::select_rrd(decoded,iris::shuttle::IssueSignals::empty_pipeline_fixture());const unsigned count=plan.ready_prefix;
  if(count){in.ready0=true;in.ready1=count==2;accepted+=count;if(count==2)++pairs;std::array<Branch::Uop,2>packet{};std::optional<Peer::Uop>branch;
   for(unsigned lane=0;lane<count;++lane){auto&q=out.queue[lane];auto&u=decoded[lane];const bool isbranch=u.has(iris::shuttle::BRANCH);auto&b=packet[lane];b.valid=true;b.expanded=q.expanded;b.pc=q.pc;b.compressed=q.compressed;b.branch=isbranch;b.predicted_valid=q.prediction_valid;b.predicted_pc=q.predicted_pc;b.sfb_branch=q.small_forward_branch;b.ras_head=q.ras_head;
    if(isbranch){if(std::getenv("IRIS_ALIGNMENT_DEBUG"))std::cerr<<"BRANCH edge="<<cycle<<" iteration="<<iteration<<" pc="<<std::hex<<q.pc<<std::dec<<" edgeinst="<<q.edge_instruction<<" pred="<<q.prediction_valid<<" btb="<<q.btb_valid<<" entry="<<q.btb_entry<<" hist="<<q.bht_history<<" value="<<q.bht_value<<"\n";b.taken=++iteration<n;expected=b.taken?start:start+8;branch=q;branches.push_back(cycle);}else expected=q.pc+(q.compressed?2:4);
   }
   if(branch)pending.push_back({cycle+2,packet,*branch});
  }else if(!out.queue[0].valid)++empty;else ++blocked;
  out=peer.evaluate(in);const bool request=out.memory_request_valid&&in.memory_request_ready;peer.commit();
  if(returning&&++refill->beat==8)refill.reset();
  if(request){if(refill)throw std::runtime_error("overlappingrefill");refill=Refill{out.memory_request_address,cycle,0};++requests;}
 }
 if(retiredbranches!=n||branches.size()!=n)throw std::runtime_error("incompletefinitebranchstimulus iter="+std::to_string(iteration)+"retired="+std::to_string(retiredbranches)+"accepted="+std::to_string(accepted)+"expected="+std::to_string(expected));
 std::cout<<"{\"loop_pc\":"<<start<<",\"n\":"<<n<<",\"seed\":"<<seed<<",\"first_branch_rrd\":"<<branches.front()<<",\"last_branch_rrd\":"<<branches.back()<<",\"steady_branch_span_after16\":"<<branches.back()-branches[15]<<",\"steady_iterations\":"<<n-16<<",\"mispredicts\":"<<mispredicts<<",\"accepted_uops\":"<<accepted<<",\"pairs\":"<<pairs<<",\"empty_edges\":"<<empty<<",\"blocked_edges\":"<<blocked<<",\"requests\":"<<requests<<",\"branch_rrd_edges\":[";
 for(unsigned i=0;i<branches.size();++i){if(i)std::cout<<',';std::cout<<branches[i];}std::cout<<"]}\n";
}
