#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <deque>
#include <optional>
#include <stdexcept>

namespace iris::opu_entry {
struct Command {std::uint64_t id;unsigned tile,tm,tn;bool fp8;};
struct QueueIssue {Command command;unsigned entry,row_subtile,column_subtile;bool tail;std::uint64_t edge,macs;};
struct QueueEdge {
 bool input_ready=false,input_fire=false,vdq_dequeue=false,iq_enqueue=false,iq_dequeue=false;
 bool seq_ready=false;unsigned vdq_before=0,iq_before=0;bool seq_before=false;
 std::optional<QueueIssue>issue;
};
// Source specialization: VectorBackend VDQ4 (no flow/no pipe), first VX IQ3
// (pipe=true/no flow), one OPU sequencer. No competing units/VRF writers and
// both real OPU read ports available are explicit finite boundary conditions.
// VAT32 is an AGE table, not32 command buffers. Its live population here is
// exactly VDQ+IQ+sequencer and never exceeds8. Physical FP8 tails are separate.
class CommandQueues {
 std::deque<Command>vdq_,iq_;std::optional<Command>seq_;
 unsigned row_=0,col_=0;std::array<std::uint64_t,16>fp8_allowed_{};
 std::optional<std::uint64_t>last_edge_;
 public:
 bool empty()const{return vdq_.empty()&&iq_.empty()&&!seq_;}
 unsigned buffered()const{return vdq_.size()+iq_.size()+bool(seq_);}
 std::optional<std::uint64_t>last_edge()const{return last_edge_;}
 QueueEdge step(std::uint64_t edge,std::optional<Command>input={}){
  if(last_edge_&&(edge<=*last_edge_||(!empty()&&edge!=*last_edge_+1)))throw std::invalid_argument("source queue edge missing/repeated");
  if(input&&(input->tile>=4||!input->tm||!input->tn||input->tm>32||input->tn>32))throw std::invalid_argument("finite TK1 positive shape required");
  QueueEdge o;o.vdq_before=vdq_.size();o.iq_before=iq_.size();o.seq_before=bool(seq_);
  if(seq_){
   unsigned entry=4*seq_->tile+2*row_+col_;
   const auto eligible=seq_->fp8?fp8_allowed_[entry]:*std::max_element(fp8_allowed_.begin(),fp8_allowed_.end());
   if(edge>=eligible){const bool tail=row_+1==(seq_->tm+15)/16&&col_+1==(seq_->tn+15)/16;
    o.issue=QueueIssue{*seq_,entry,row_,col_,tail,edge,std::uint64_t(std::min(16U,seq_->tm-16*row_))*std::min(16U,seq_->tn-16*col_)};
   }
  }
  o.seq_ready=!seq_||(o.issue&&o.issue->tail);
  o.iq_dequeue=!iq_.empty()&&o.seq_ready;
  const bool iq_ready=iq_.size()<3||(!iq_.empty()&&o.seq_ready);
  o.vdq_dequeue=!vdq_.empty()&&iq_ready;o.iq_enqueue=o.vdq_dequeue;
  o.input_ready=vdq_.size()<4;o.input_fire=input&&o.input_ready;
  std::optional<Command>next_seq=o.iq_dequeue?std::optional<Command>(iq_.front()):std::nullopt;
  std::optional<Command>next_iq=o.vdq_dequeue?std::optional<Command>(vdq_.front()):std::nullopt;
  if(o.issue){if(o.issue->command.fp8)fp8_allowed_[o.issue->entry]=edge+3;
   if(o.issue->tail)seq_.reset();else if(++col_==(o.issue->command.tn+15)/16){col_=0;++row_;}}
  if(next_seq){seq_=*next_seq;row_=col_=0;}
  if(o.iq_dequeue)iq_.pop_front();if(next_iq)iq_.push_back(*next_iq);
  if(o.vdq_dequeue)vdq_.pop_front();if(o.input_fire)vdq_.push_back(*input);
  if(vdq_.size()>4||iq_.size()>3||buffered()>8)throw std::logic_error("source command capacity exceeded");
  last_edge_=edge;return o;
 }
};
}
