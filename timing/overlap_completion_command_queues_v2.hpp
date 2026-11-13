#pragma once
#include "overlap_completion_command_queues.hpp"
namespace iris::opu_entry {
// Source VDQ has neither flow nor pipe. Its input can be supplied after the
// same-edge old-state transition without affecting any dequeue/microissue.
// Re-evaluate the saved preedge controller with the committed input, then
// replace state. This is pure controller evaluation, NOT a second source edge
// or a second physical callback. It reuses the frozen, source-qualified model.
class CommandQueuesPhased {
 CommandQueues current_,before_;
 std::optional<std::uint64_t>edge_;
 QueueEdge output_{};bool committed_=false;
 static bool same_issue(const std::optional<QueueIssue>&a,const std::optional<QueueIssue>&b){
  if(bool(a)!=bool(b))return false;if(!a)return true;
  return a->command.id==b->command.id&&a->command.tile==b->command.tile&&a->command.tm==b->command.tm&&a->command.tn==b->command.tn&&a->command.fp8==b->command.fp8&&a->entry==b->entry&&a->row_subtile==b->row_subtile&&a->column_subtile==b->column_subtile&&a->tail==b->tail&&a->edge==b->edge&&a->macs==b->macs;
 }
 public:
 bool empty()const{return current_.empty();}
 unsigned buffered()const{return current_.buffered();}
 std::optional<std::uint64_t>last_edge()const{return current_.last_edge();}
 static bool same_old_state_events(const QueueEdge&a,const QueueEdge&b){return a.input_ready==b.input_ready&&a.vdq_dequeue==b.vdq_dequeue&&a.iq_enqueue==b.iq_enqueue&&a.iq_dequeue==b.iq_dequeue&&a.seq_ready==b.seq_ready&&a.vdq_before==b.vdq_before&&a.iq_before==b.iq_before&&a.seq_before==b.seq_before&&same_issue(a.issue,b.issue);}
 QueueEdge advance(std::uint64_t edge){
  if(edge_&&edge<=*edge_)throw std::logic_error("OPU_QUEUE_EDGE_REPEATED_OR_STALE");
  before_=current_;output_=current_.step(edge);edge_=edge;committed_=false;return output_;
 }
 QueueEdge commit_input(std::uint64_t edge,const Command&input){
  if(!edge_||edge!=*edge_)throw std::logic_error("OPU_QUEUE_INPUT_EDGE_MISMATCH");
  if(committed_)throw std::logic_error("OPU_QUEUE_INPUT_ALREADY_COMMITTED");
  auto proposed=before_;auto next=proposed.step(edge,input);
  if(!same_old_state_events(output_,next))throw std::logic_error("OPU_QUEUE_INPUT_CHANGED_OLD_STATE_EVENTS");
  current_=std::move(proposed);output_=next;committed_=true;return output_;
 }
 QueueEdge step(std::uint64_t edge,std::optional<Command>input={}){auto o=advance(edge);return input?commit_input(edge,*input):o;}
};
}
