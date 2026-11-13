#include "noc_router.hpp"
#include <iostream>
#include <charconv>
#include <sstream>
#include <stdexcept>
#include <string>
#include <memory>
using namespace iris::noc;
static std::uint64_t take(std::istringstream& s){std::string word;if(!(s>>word))throw std::invalid_argument("Incomplete router input");std::uint64_t v=0;auto r=std::from_chars(word.data(),word.data()+word.size(),v);if(r.ec!=std::errc{}||r.ptr!=word.data()+word.size())throw std::invalid_argument("Router expects unsigned integer");return v;}
static unsigned small(std::istringstream& s){auto x=take(s);if(x>63)throw std::invalid_argument("Router small field outside representable range");return unsigned(x);}
static bool flag(std::istringstream& s){auto x=take(s);if(x>1)throw std::invalid_argument("Router flag must be0or1");return bool(x);}

static Flit flit(std::istringstream& s){Flit f;for(auto& w:f.words){auto x=take(s);if(x>0xffffffffULL)throw std::invalid_argument("Flit word overflow");w=x;}if(f.words[2]>0x7ff)throw std::invalid_argument("Flit wider than75bits");return f;}
static Fifo fifo(std::istringstream& s,unsigned depth){Fifo q{small(s),small(s),flag(s),{}};for(unsigned j=0;j<depth;j++)q.memory.push_back(flit(s));return q;}
static void value(std::uint64_t x){std::cout<<' '<<x;}
int main(){try{
 std::unique_ptr<ReturnRouter> model;RouterParameters p{};bool profiled=false;std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream s(line);std::string op;if(!(s>>op))continue;
  if(op=="profile"){
   p.arbitration.input_virtual_channels=small(s);p.input_fifo_depth=small(s);p.egress_fifo_depth=small(s);p.node_id=small(s);p.local_egress_id=small(s);p.arbitration.router_input_units=small(s);p.arbitration.output_virtual_channels=small(s);p.arbitration.local_input_unit=small(s);p.local_output_bit=small(s);if(p.arbitration.input_virtual_channels!=6||p.input_fifo_depth!=5||p.egress_fifo_depth!=2||p.node_id!=5||p.local_egress_id!=0||p.arbitration.router_input_units!=4||p.arbitration.output_virtual_channels!=13||p.arbitration.local_input_unit!=0||p.local_output_bit!=12)throw std::invalid_argument("Driver requires exact source-qualified node5 return profile");profiled=true;
  }else if(op=="seed"){
   if(!profiled)throw std::invalid_argument("Explicit sourced profile required");
   ReturnState initial;
   initial.arbitration={take(s),take(s),take(s)};initial.switch_mask=take(s);initial.switch_lock=take(s);initial.egress_sa_mask=take(s);initial.egress_sa_lock=take(s);initial.egress_empty=flag(s);
   for(unsigned k=0;k<p.arbitration.input_virtual_channels;k++){auto g=small(s);auto local=flag(s);initial.vcs.push_back({g,local,fifo(s,p.input_fifo_depth)});}initial.egress=fifo(s,p.egress_fifo_depth);model=std::make_unique<ReturnRouter>(p,std::move(initial));
  }else if(op=="step"){
   if(!model)throw std::invalid_argument("Explicit captured seed required");
   auto tb=take(s);ReturnInputs i{};i.arrival_valid=flag(s);i.arrival_vc=small(s);i.arrival_dest=small(s);i.arrival_dest_id=small(s);i.arrival=flit(s);i.downstream_ready=flag(s);for(unsigned k=0;k<3;k++){i.peer_eligible[k]=flag(s);i.peer_eligible_outputs[k]=take(s);}i.route_fire=flag(s);i.route_vc=small(s);i.route_local=flag(s);
   auto old=model->state();auto r=model->step(i);std::cout<<tb;
   for(auto x:{old.arbitration.input_unit_mask,old.arbitration.single_vc_input_mask,old.arbitration.islip_output_mask,old.switch_mask,old.switch_lock,old.egress_sa_mask,old.egress_sa_lock}){value(x);}
   value(old.egress_empty);
   for(auto& vc:old.vcs){value(vc.state);value(vc.local);value(vc.fifo.enq);value(vc.fifo.deq);value(vc.fifo.maybe_full);value(vc.fifo.count());if(vc.fifo.count())for(auto w:vc.fifo.front().words)value(w);else for(unsigned k=0;k<3;k++)value(0);}
   value(old.egress.enq);value(old.egress.deq);value(old.egress.maybe_full);value(old.egress.count());
   for(auto x:{r.waiting,r.selected_vc,r.input_grants,r.output_grants,r.popped_vcs,r.freed_vcs}){value(x);}
   value(r.egress_push);value(r.egress_pop);value(bool(r.output));
   if(r.output)for(auto w:r.output->words)value(w);else for(unsigned k=0;k<3;k++)value(0);std::cout<<'\n';
  }else throw std::invalid_argument("Unknown router command");
  std::string extra;if(s>>extra)throw std::invalid_argument("Extra router input");
 }
 return 0;
}catch(const std::exception& e){std::cerr<<"Router component refused: "<<e.what()<<'\n';return 2;}}
