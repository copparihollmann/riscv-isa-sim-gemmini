// Visit an already-permitted future RRD edge. No actor/cost/queue is changed.
void iris_timing_adapter::empirical_async_RRD_deadline(std::optional<Cycle>&event){
 if(!event)return;
 for(unsigned h=0;h<std::min(size_t(2),pure_.size());++h){
  const auto&p=pure_[h];const auto&head=empirical_async_[h];
  if(!p.engaged||p.boundary||!p.packets.empty()||blocked_[h]||empirical_branch_recovery_[h]||!head||head->done||!head->backend||empirical_async_next_[h]||cores_[h]->is_waiting_for_interrupt())continue;
  if(profile_.source_counter_clock&&source_counter_clocks_[h].blocks_rrd(clock_.now()))continue;
  if(cores_[h]->iris_pipeline_interrupt_exception())continue;
  const auto&node=clock_.nodes().at(*head->backend);if(node.id!=*head->backend||node.op.hart!=h||!node.issued||node.completed||node.cancelled||node.physical)continue;
  const auto d=profile_.harts[h].divider;const auto first=std::max(head->com_cycle,node.end);if(first<d)continue;
  auto retry=first-d;if(const auto rem=retry%d){if(retry>UINT64_MAX-(d-rem))throw std::overflow_error("IRIS_ASYNC_RRD_WAKE_HORIZON");retry+=d-rem;}
  if(retry<=clock_.now()||retry>=*event)continue;
  cpu_event(h,"async_RRD_wake",p.frontier,0,SIZE_MAX,"\"old_next_event\":"+std::to_string(*event)+",\"retry_edge\":"+std::to_string(retry)+",\"backend_node\":"+std::to_string(*head->backend)+",\"backend_end\":"+std::to_string(node.end)+",\"head_COM\":"+std::to_string(head->com_cycle));
  event=retry;
 }
}
