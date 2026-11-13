#include "noc_router.hpp"
#include <stdexcept>
#include <string>

namespace iris::noc {
namespace {
std::uint64_t mask(unsigned n){if(!n||n>63)throw std::invalid_argument("Router width unsupported");return (std::uint64_t{1}<<n)-1;}
std::uint64_t rr(std::uint64_t valid,std::uint64_t m){auto a=valid&~m;auto b=a?a:valid;return b&(~b+1);}
unsigned index(std::uint64_t one){if(!one||(one&(one-1)))throw std::logic_error("Not one-hot");unsigned n=0;while((one>>n)!=1)++n;return n;}
std::uint64_t idle_mask(std::uint64_t m,unsigned width){auto all=mask(width);return m==all?0:((m<<1)|1)&all;}
std::uint64_t prefix(std::uint64_t one){return (one<<1)-1;}
void fifo_valid(const Fifo& q,unsigned depth){if(q.memory.size()!=depth||q.enq>=depth||q.deq>=depth)throw std::invalid_argument("Router FIFO seed dimensions invalid");}
}
unsigned Fifo::count()const {auto depth=unsigned(memory.size());if(enq==deq)return maybe_full?depth:0;return enq>deq?enq-deq:depth+enq-deq;}
const Flit& Fifo::front()const {if(!count())throw std::logic_error("Undefined empty FIFO read");return memory.at(deq);}
void Fifo::commit(std::optional<Flit> push,bool pop) {
 const auto old=count();const auto depth=unsigned(memory.size());
 if(push&&old==depth)throw std::logic_error("Source non-pipelined FIFO overflow");
 if(pop&&!old)throw std::logic_error("Source FIFO underflow");
 if(push){memory.at(enq)=*push;enq=(enq+1)%depth;}
 if(pop)deq=(deq+1)%depth;
 if(bool(push)!=pop)maybe_full=bool(push);
}
ReturnRouter::ReturnRouter(RouterParameters p,ReturnState s):parameters_(p),state_(std::move(s)) {
 if(p.arbitration.router_input_units!=4||p.arbitration.local_input_unit!=0||p.arbitration.output_virtual_channels!=13||p.local_output_bit!=12)
  throw std::invalid_argument("Return branch requires source-qualified4inputs/13outputVCs/local0/egressbit12");
 if(state_.vcs.size()!=p.arbitration.input_virtual_channels)throw std::invalid_argument("VC seed count mismatch");
 for(const auto& vc:state_.vcs){fifo_valid(vc.fifo,p.input_fifo_depth);if(vc.state>3)throw std::invalid_argument("Unsupported input stage in seed");if(vc.state==3&&!vc.local)throw std::invalid_argument("Nonlocal active VC is outside return branch");}
 fifo_valid(state_.egress,p.egress_fifo_depth);
 (void)Arbiter(p.arbitration,state_.arbitration);
 if((state_.switch_mask|state_.switch_lock)&~mask(p.arbitration.input_virtual_channels))throw std::invalid_argument("Input switch seed width");
 if((state_.egress_sa_mask|state_.egress_sa_lock)&~mask(p.arbitration.router_input_units))throw std::invalid_argument("Egress switch seed width");
}
ReturnResult ReturnRouter::step(const ReturnInputs& i) {
 auto& s=state_;const auto n=parameters_.arbitration.input_virtual_channels;const auto local=std::uint64_t{1}<<parameters_.local_output_bit;
 if(i.arrival_valid) {
  if(i.arrival_vc>=n||i.arrival_dest!=parameters_.node_id||i.arrival_dest_id!=parameters_.local_egress_id)
   throw std::invalid_argument("Unmodelled nonlocal physical input flow");
  if(s.vcs[i.arrival_vc].fifo.count()==parameters_.input_fifo_depth)throw std::logic_error("Accepted flit with no input FIFO credit");
  if(i.arrival.head()&&s.vcs[i.arrival_vc].state!=0)throw std::logic_error("Source head arrived on nonidle VC");
 }
 std::uint64_t routed=0;
 if(i.route_fire){if(i.route_vc>=n||s.vcs[i.route_vc].state!=1||!i.route_local)throw std::invalid_argument("Unmodelled or inconsistent external route completion");routed=std::uint64_t{1}<<i.route_vc;}
 ReturnResult r{};
 for(unsigned k=0;k<n;k++)if(s.vcs[k].state==2)r.waiting|=std::uint64_t{1}<<k;
 r.waiting|=routed; // Source combines routing and VC allocation.
 Arbiter arb(parameters_.arbitration,s.arbitration);
 auto preview=arb.preview({r.waiting,i.route_fire,i.route_vc,0,0});
 std::array<std::uint64_t,4> eligible{};
 if(preview.selected_vc){auto k=index(preview.selected_vc);if((s.vcs[k].local||bool(routed&preview.selected_vc))&&s.egress_empty)eligible[0]=local;}
 std::uint64_t inputs=0,all_outputs=0;
 for(unsigned k=1;k<4;k++)if(i.peer_eligible[k-1]){
  eligible[k]=i.peer_eligible_outputs[k-1];
  if(eligible[k]&local)throw std::invalid_argument("Peer local-egress contender needs additional input-unit model");
 }
 for(unsigned k=0;k<4;k++)if(eligible[k]){inputs|=std::uint64_t{1}<<k;all_outputs|=eligible[k];}
 auto first=arb.preview({r.waiting,i.route_fire,i.route_vc,inputs,all_outputs});
 const auto outputs=first.input_unit_grants?eligible[index(first.input_unit_grants)]:0;
 auto grant=arb.step({r.waiting,i.route_fire,i.route_vc,inputs,outputs});
 r.selected_vc=grant.selected_vc;r.input_grants=grant.input_unit_grants;r.output_grants=grant.output_vc_grants;
 // Only old-state g_a VCs can enter switch allocation; newly granted VCs wait an edge.
 std::uint64_t switch_valids=0;
 const bool credit=s.egress.count()==0;
 for(unsigned k=0;k<n;k++)if(s.vcs[k].state==3&&s.vcs[k].local&&credit&&s.vcs[k].fifo.count())switch_valids|=std::uint64_t{1}<<k;
 auto chosen=(switch_valids&s.switch_lock)?s.switch_lock:rr(switch_valids&~s.switch_lock,s.switch_mask);
 const bool request=bool(switch_valids&chosen);
 const auto egress_valids=request?1u:0u;
 auto echoice=(egress_valids&s.egress_sa_lock)?s.egress_sa_lock:rr(egress_valids&~s.egress_sa_lock,s.egress_sa_mask);
 const bool send=request&&bool(echoice&1);
 std::optional<Flit> transferred;
 if(send){auto k=index(chosen);transferred=s.vcs[k].fifo.front();r.popped_vcs=chosen;if(transferred->tail())r.freed_vcs=chosen;}
 if(s.egress.count())r.output=s.egress.front();else r.output=transferred; // Queue flow=true.
 r.egress_pop=s.egress.count()!=0&&i.downstream_ready;
 r.egress_push=bool(transferred)&&!(s.egress.count()==0&&i.downstream_ready);
 if(i.route_fire){s.vcs[i.route_vc].state=2;s.vcs[i.route_vc].local=true;}
 if(grant.local_request_accepted){auto k=index(grant.selected_vc);if(!(r.output_grants&local))throw std::logic_error("Return request allocated nonlocal output");s.vcs[k].state=3;s.vcs[k].local=true;}
 if(r.freed_vcs)s.vcs[index(r.freed_vcs)].state=0;
 if(i.arrival_valid&&i.arrival.head()){s.vcs[i.arrival_vc].state=2;s.vcs[i.arrival_vc].local=true;}
 for(unsigned k=0;k<n;k++)s.vcs[k].fifo.commit(i.arrival_valid&&i.arrival_vc==k?std::optional<Flit>(i.arrival):std::nullopt,bool(r.popped_vcs&(std::uint64_t{1}<<k)));
 s.egress.commit(r.egress_push?transferred:std::nullopt,r.egress_pop);
 s.egress_empty=!(r.output_grants&local)&&(bool(r.freed_vcs)||s.egress_empty);
 if(send)s.switch_lock=transferred->tail()?0:chosen;
 s.switch_mask=send?prefix(chosen):idle_mask(s.switch_mask,n);
 if(send)s.egress_sa_lock=transferred->tail()?0:echoice;
 s.egress_sa_mask=send?prefix(echoice):idle_mask(s.egress_sa_mask,parameters_.arbitration.router_input_units);
 s.arbitration=grant.next;
 return r;
}
} // namespace iris::noc
