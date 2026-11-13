#pragma once
#include <cstdint>
#include <deque>
#include <optional>
#include <stdexcept>
namespace iris::rvv_eg {
struct Command {uint64_t id;unsigned vd,vs1,vs2,beats;};
struct Micro {Command command;unsigned index,destination,source1,source2;uint64_t edge;bool tail;};
struct Edge {bool input_ready=false,input_fire=false,vdq_dequeue=false,iq_dequeue=false,seq_ready=false;unsigned vdq_before=0,iq_before=0;bool seq_before=false;std::optional<Micro>issue,write;};
// Conditional saved compute integer VADD specialization: VDQ4 no flow/pipe,
// IQ3 pipe/no flow, one sequencer, one-cycle integer write. No competing
// sequencer/VRF writer, full-VLmax unmasked aligned register groups, all ports
// available after actual reset scrub. This is control, never payload state.
class Queues {
 std::deque<Command>vdq_,iq_;std::optional<Command>seq_;unsigned index_=0;std::optional<Micro>pipe_;std::optional<uint64_t>last_;
 public:
 bool empty()const{return vdq_.empty()&&iq_.empty()&&!seq_&&!pipe_;}
 unsigned buffered()const{return vdq_.size()+iq_.size()+bool(seq_);}
 Edge step(uint64_t now,std::optional<Command>input={}){
  if(last_&&(now<=*last_||(!empty()&&now!=*last_+1)))throw std::invalid_argument("RVV source edge repeated/missing");
  if(input&&(input->vd>=32||input->vs1>=32||input->vs2>=32||(input->beats!=2&&input->beats!=4&&input->beats!=8&&input->beats!=16)))throw std::invalid_argument("full-VL VADD finite geometry");
  Edge e;e.vdq_before=vdq_.size();e.iq_before=iq_.size();e.seq_before=bool(seq_);e.write=pipe_;
  if(seq_){const unsigned d=2*seq_->vd+index_,a=2*seq_->vs1+index_,b=2*seq_->vs2+index_;const bool hazard=pipe_&&pipe_->command.id!=seq_->id&&(pipe_->destination==d||pipe_->destination==a||pipe_->destination==b);if(!hazard)e.issue=Micro{*seq_,index_,d,a,b,now,index_+1==seq_->beats};}
  e.seq_ready=!seq_||(e.issue&&e.issue->tail);e.iq_dequeue=!iq_.empty()&&e.seq_ready;const bool iq_ready=iq_.size()<3||e.iq_dequeue;e.vdq_dequeue=!vdq_.empty()&&iq_ready;e.input_ready=vdq_.size()<4;e.input_fire=input&&e.input_ready;
  auto next_seq=e.iq_dequeue?std::optional<Command>(iq_.front()):std::nullopt;auto next_iq=e.vdq_dequeue?std::optional<Command>(vdq_.front()):std::nullopt;
  pipe_=e.issue;if(e.issue){if(e.issue->tail)seq_.reset();else ++index_;}if(next_seq){seq_=*next_seq;index_=0;}
  if(e.iq_dequeue)iq_.pop_front();if(next_iq)iq_.push_back(*next_iq);if(e.vdq_dequeue)vdq_.pop_front();if(e.input_fire)vdq_.push_back(*input);
  if(vdq_.size()>4||iq_.size()>3||buffered()>8)throw std::logic_error("RVV source queue capacity");last_=now;return e;
 }
};
}
