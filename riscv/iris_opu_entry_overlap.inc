// Finite source-relative MM overlap. Architectural COM is the explicit test
// bridge's command-availability boundary, not a claim of exact CPU/VAT latency.
// Backend/VRF memory paths and interrupts are not silently synthesized here.
bool iris_timing_adapter::opu_is_mm(const insn_fetch_t*fetch)const{
 if(!fetch)return false;auto instruction=fetch->insn;const auto raw=uint32_t(instruction.bits());
 return (raw&MASK_VTMMU_TVV)==MATCH_VTMMU_TVV||(raw&MASK_VTMMS_TVV)==MATCH_VTMMS_TVV||
        (raw&MASK_VTFMM_TVV)==MATCH_VTFMM_TVV||(raw&MASK_VTFMM_ALT_TVV)==MATCH_VTFMM_ALT_TVV;
}
std::shared_ptr<iris_timing_adapter::EmpiricalAsync> iris_timing_adapter::opu_find(unsigned h,size_t id)const{
 for(const auto&a:opu_pending_[h])if(a->instruction==id)return a;return{};
}
// Exact backend queue control under the finite isolated-MM boundary. The
// architectural CPU bridge offers a successfully committed command one edge
// AFTER COM. This avoids assuming callback iteration order is an RTL phase.
// It is an explicit unqualified CPU-to-unit latency, never a fitted offset.
bool iris_timing_adapter::opu_can_dispatch(unsigned h)const{
 const auto divider=profile_.harts[h].divider;
 if(clock_.now()%divider)throw std::logic_error("IRIS_OPU_QUEUE_UNALIGNED_ADMISSION");
 const auto now=clock_.now()/divider,available=now+4;
 auto q=opu_queues_[h];const auto last=q.last_edge();
 if(last&&*last>now)throw std::logic_error("IRIS_OPU_QUEUE_FUTURE_STATE");
 auto begin=last?*last+1:now;
 // Empty source control can skip idle edges. Pending COM slots cannot.
 if(q.empty()){
  begin=now;
  for(const auto&a:opu_pending_[h])if(!a->opu_queued)begin=std::min(begin,a->opu_available);
  if(last)begin=std::max(begin,*last+1);
 }
 for(auto edge=begin;edge<=available;++edge){
  std::optional<iris::opu_entry::CommandTK>input;
  for(const auto&a:opu_pending_[h])if(!a->opu_queued&&a->opu_available==edge){if(input)throw std::logic_error("IRIS_OPU_QUEUE_MULTIPLE_INPUTS");input=a->opu_command;}
  if(edge==available){if(input)return false;input=iris::opu_entry::CommandTK{UINT64_MAX,0,1,1,false};}
  auto o=q.step(edge,input);
  if(input&&!o.input_fire){if(edge==available)return false;throw std::logic_error("IRIS_OPU_QUEUE_PRIOR_RESERVATION_OVERRUN");}
 }
 return true;
}
void iris_timing_adapter::opu_start_clock(unsigned h){
 if(opu_clock_active_[h])return;
 const auto divider=profile_.harts[h].divider;
 iris::Op tick{h,"source.opu.queue.edge","source.opu.queue.clock"+std::to_string(h),divider,divider};
 tick.retires=false;tick.cancellable=false;tick.issue_period=divider;tick.earliest=clock_.now();
 tick.on_complete=[this,h]{opu_clock_active_[h]=false;opu_tick(h);};
 opu_clock_active_[h]=true;clock_.issue(std::move(tick));
}
void iris_timing_adapter::opu_begin(unsigned h,size_t id){
 auto&r=pure_[h].instructions.at(id);auto&v=cores_[h]->VU;
 if(h>=2||!opu_is_mm(&r.fetch)||!empirical_async_can_dispatch(h,&r.fetch)||v.vsew!=8||v.widen!=4||!(profile_.empirical_opu_tk124?(v.tk==1||v.tk==2||v.tk==4):v.tk==1)||!v.tm||!v.tn()||v.tm>32||v.tn()>32)
  throw std::runtime_error(profile_.empirical_opu_tk124?"IRIS_OPU_ENTRY_MM_TK124_POSITIVE_SHAPE_SCOPE":"IRIS_OPU_ENTRY_MM_TK1_POSITIVE_SHAPE_SCOPE");
 const auto*state=cores_[h]->get_state();
 if(state->prv!=PRV_M||state->v||state->debug_mode)throw std::runtime_error("IRIS_OPU_ENTRY_MMODE_SCOPE");
 auto a=std::make_shared<EmpiricalAsync>();a->instruction=id;a->opu_pc=r.pc;a->com_cycle=r.com_cycle;a->feature=empirical_feature(h,r.fetch);a->opu_entry=true;
 const auto divider=profile_.harts[h].divider;
 if(r.com_cycle!=clock_.now()+3*divider)throw std::runtime_error("IRIS_OPU_QUEUE_FIXED_CPU_COM_PHASE_SCOPE");
 a->opu_available=r.com_cycle/divider+1;
 a->opu_command={id,unsigned((r.uop.rd>>3)&3),unsigned(v.tm),unsigned(v.tn()),a->feature.family=="vme.fp8",unsigned(v.tk)};
 // Derive the exact functional tile layout through the existing accessor;
 // logical tiles are interleaved, so contiguous tile-byte guesses are wrong.
 const unsigned td=(r.uop.rd>>1)&12;
 for(unsigned row=0;row<v.tm;++row)for(unsigned col=0;col<v.tn();++col){
  auto&cell=v.mt_elt<uint32_t>(td,row,col);const size_t off=reinterpret_cast<char*>(&cell)-v.mt.data();
  if(off+4>v.mt.size())throw std::logic_error("IRIS_OPU_ENTRY_CELL_BOUNDS");a->opu_offsets.push_back(off);
 }
 opu_pending_[h].push_back(a);empirical_async_[h]=opu_pending_[h].front();
 ++opu_accepted_[h];opu_peak_[h]=std::max<uint64_t>(opu_peak_[h],opu_pending_[h].size());
 opu_start_clock(h);
 if(async_trace_)*async_trace_<<"{\"event\":\"opu_front_accept\",\"hart\":"<<h<<",\"instruction\":"<<id<<",\"pc\":"<<r.pc<<",\"rrd\":"<<clock_.now()<<",\"com\":"<<a->com_cycle<<",\"backend_available\":"<<a->opu_available*divider<<",\"tile\":"<<(r.uop.rd>>3)<<"}\n";
}
void iris_timing_adapter::opu_before(unsigned h,const std::shared_ptr<EmpiricalAsync>&a){
 auto&v=cores_[h]->VU;
 a->before_vrf.resize(v.vlenb*32);std::memcpy(a->before_vrf.data(),v.reg_file,a->before_vrf.size());a->before_vrf_known=v.iris_vrf_definedness;
 a->before_mrf=v.mt;a->before_mrf_known=v.iris_tile_definedness;a->before_initialized=v.iris_initialized;
 // Earlier committed instructions may still own unpublished source writes.
 // Their private versions feed this younger intent without changing visible
 // state. Actual publication remains the matching per-entry physical event.
 for(const auto&older:opu_pending_[h]){
  if(older==a)break;
  if(!older->retired)throw std::logic_error("IRIS_OPU_ENTRY_COM_ORDER");
  for(size_t off:older->opu_offsets){
   std::memcpy(v.mt.data()+off,older->after_mrf.data()+off,4);
   v.iris_tile_definedness.write(off,older->after_mrf_known.read(off,4));
   v.iris_initialized[off/4]=older->after_initialized[off/4];
  }
 }
 a->opu_input_mrf=v.mt;a->opu_input_known=v.iris_tile_definedness;
}
void iris_timing_adapter::opu_after(unsigned h,const std::shared_ptr<EmpiricalAsync>&a,bool retired){
 auto&v=cores_[h]->VU;
 a->after_mrf=v.mt;a->after_mrf_known=v.iris_tile_definedness;a->after_initialized=v.iris_initialized;
 // MM has no VRF write. Refuse a changing handler rather than laundering it.
 if(std::memcmp(a->before_vrf.data(),v.reg_file,a->before_vrf.size())||v.iris_vrf_definedness.read(0,a->before_vrf.size())!=a->before_vrf_known.read(0,a->before_vrf.size()))
  throw std::logic_error("IRIS_OPU_ENTRY_MM_UNEXPECTED_VRF_WRITE");
 v.mt=a->before_mrf;v.iris_tile_definedness=a->before_mrf_known;v.iris_initialized=a->before_initialized;
 if(!retired){opu_cancel(h,a);return;}
 a->retired=true;
 a->opu_remaining=((a->opu_command.tm+15)/16)*((a->opu_command.tn+15)/16)*a->opu_command.tk;
 if(clock_.now()!=a->com_cycle)throw std::logic_error("IRIS_OPU_QUEUE_COM_PHASE_CHANGED");
 opu_start_clock(h);
}
void iris_timing_adapter::opu_tick(unsigned h){
 const auto divider=profile_.harts[h].divider;
 if(clock_.now()%divider)throw std::logic_error("IRIS_OPU_QUEUE_UNALIGNED_EDGE");
 const auto edge=clock_.now()/divider;
 std::shared_ptr<EmpiricalAsync>input;
 for(const auto&a:opu_pending_[h])if(!a->opu_queued&&a->opu_available<=edge){
  if(input||a->opu_available!=edge||!a->retired)throw std::logic_error("IRIS_OPU_QUEUE_COM_INPUT_PHASE");input=a;
 }
 auto result=opu_queues_[h].step(edge,input?std::optional<iris::opu_entry::CommandTK>(input->opu_command):std::nullopt);
 if(profile_.empirical_opu_fence)opu_fence_observe(h,result);
 if(input){if(!result.input_fire)throw std::logic_error("IRIS_OPU_QUEUE_RESERVED_INPUT_NOT_READY");input->opu_queued=true;}
 opu_queue_peak_[h]=std::max<uint64_t>(opu_queue_peak_[h],opu_queues_[h].buffered());
 if(!result.input_ready)++opu_full_edges_[h];
 if(async_trace_)*async_trace_<<"{\"event\":\"opu_queue_edge\",\"hart\":"<<h<<",\"cycle\":"<<clock_.now()<<",\"vdq_before\":"<<result.vdq_before<<",\"iq_before\":"<<result.iq_before<<",\"seq_before\":"<<result.seq_before<<",\"input_ready\":"<<result.input_ready<<",\"input_fire\":"<<result.input_fire<<",\"microissue\":"<<bool(result.issue)<<"}\n";
 if(result.issue){
  const auto&m=*result.issue;auto a=opu_find(h,m.command.id);
  if(!a||!a->retired||!a->opu_queued)throw std::logic_error("IRIS_OPU_QUEUE_UNOWNED_MICROISSUE");
  auto&v=cores_[h]->VU;
  std::vector<size_t>offsets;const unsigned td=4*m.command.tile;
  for(unsigned row=16*m.row_subtile;row<std::min<unsigned>(m.command.tm,16*(m.row_subtile+1));++row)
   for(unsigned col=16*m.column_subtile;col<std::min<unsigned>(m.command.tn,16*(m.column_subtile+1));++col){
    auto&cell=v.mt_elt<uint32_t>(td,row,col);offsets.push_back(reinterpret_cast<char*>(&cell)-v.mt.data());
   }
  if(profile_.empirical_opu_tk124&&async_trace_)*async_trace_<<"{\"event\":\"opu_K_microissue\",\"hart\":"<<h<<",\"instruction\":"<<a->instruction<<",\"entry\":"<<m.entry<<",\"k\":"<<m.k_index<<",\"last_k\":"<<m.last_k<<",\"tk\":"<<m.command.tk<<",\"cycle\":"<<clock_.now()<<",\"macs\":"<<m.macs<<"}\n";
  const auto write_edge=edge+(m.command.fp8?3:1);
  iris::Op write{h,"source.opu.write-clock-callback","source.opu.callback.clock"+std::to_string(h),divider,divider};
  write.retires=false;write.pc=a->opu_pc;write.macs=0;write.earliest=(write_edge-1)*divider;write.issue_period=divider;write.cancellable=false;
  write.on_complete=[this,h,a,offsets=std::move(offsets),pc=a->opu_pc,macs=m.macs,last_k=m.last_k,k=m.k_index]{opu_write(h,a,offsets,last_k,k);iris::PhysicalOp point{h,profile_.empirical_opu_tk124?"source.opu.K.write":"source.opu.entry.write","source.opu.mrf.write"+std::to_string(h),pc,0,macs,{},"OuterProductSequencer+Backend.controlReg+OuterProductCell;VDQ4-IQ3;COMplus1-bridge-unqualified",true};clock_.record_physical_edge(std::move(point));};
  const auto node=clock_.issue(std::move(write));a->backend=node;
  if(async_trace_)*async_trace_<<"{\"event\":\"opu_microissue_reserved\",\"hart\":"<<h<<",\"instruction\":"<<a->instruction<<",\"pc\":"<<a->opu_pc<<",\"entry\":"<<m.entry<<",\"seq\":"<<edge*divider<<",\"array\":"<<(edge+1)*divider<<",\"write\":"<<write_edge*divider<<",\"tail\":"<<m.tail<<",\"macs\":"<<m.macs<<",\"backend_node\":"<<node<<"}\n";
 }
 bool waiting=false;for(const auto&a:opu_pending_[h])waiting|=!a->opu_queued;
 if(waiting||!opu_queues_[h].empty())opu_start_clock(h);
}
void iris_timing_adapter::opu_write(unsigned h,const std::shared_ptr<EmpiricalAsync>&a,const std::vector<size_t>&offsets,bool last_k,unsigned k){
 if(!a->retired||!a->opu_remaining)throw std::logic_error("IRIS_OPU_ENTRY_UNOWNED_WRITE");
 if(last_k!=(k+1==a->opu_command.tk))throw std::logic_error("IRIS_OPU_ENTRY_WRONG_K_PUBLICATION_PHASE");
 auto&v=cores_[h]->VU;
 if(std::memcmp(a->before_vrf.data(),v.reg_file,a->before_vrf.size())||v.iris_vrf_definedness.read(0,a->before_vrf.size())!=a->before_vrf_known.read(0,a->before_vrf.size()))
  throw std::logic_error("IRIS_OPU_ENTRY_OPERAND_CHANGED_BEFORE_SOURCE_READ");
 for(size_t off:offsets){
  if(std::memcmp(v.mt.data()+off,a->opu_input_mrf.data()+off,4)||v.iris_tile_definedness.read(off,4)!=a->opu_input_known.read(off,4))
   throw std::logic_error("IRIS_OPU_ENTRY_MRF_VERSION_CHANGED hart="+std::to_string(h)+" instruction="+std::to_string(a->instruction)+" off="+std::to_string(off)+" now="+std::to_string(clock_.now()));
  if(last_k){std::memcpy(v.mt.data()+off,a->after_mrf.data()+off,4);v.iris_tile_definedness.write(off,a->after_mrf_known.read(off,4));v.iris_initialized[off/4]=a->after_initialized[off/4];}
 }
 ++opu_writes_[h];if(last_k)++opu_final_writes_[h];--a->opu_remaining;
 if(profile_.empirical_opu_tk124&&async_trace_)*async_trace_<<"{\"event\":\"opu_K_completion\",\"hart\":"<<h<<",\"instruction\":"<<a->instruction<<",\"cycle\":"<<clock_.now()<<",\"k\":"<<k<<",\"last_k\":"<<last_k<<",\"projected_MRF_published\":"<<last_k<<",\"cells\":"<<offsets.size()<<"}\n";
 if(last_k&&async_trace_)*async_trace_<<"{\"event\":\"opu_entry_publish\",\"hart\":"<<h<<",\"instruction\":"<<a->instruction<<",\"cycle\":"<<clock_.now()<<",\"cells\":"<<offsets.size()<<",\"remaining\":"<<a->opu_remaining<<"}\n";
 if(!a->opu_remaining){a->done=true;auto&pending=opu_pending_[h];auto it=std::find(pending.begin(),pending.end(),a);if(it==pending.end())throw std::logic_error("IRIS_OPU_ENTRY_MISSING_OWNER");pending.erase(it);empirical_async_[h]=pending.empty()?nullptr:pending.front();}
}
void iris_timing_adapter::opu_cancel(unsigned h,const std::shared_ptr<EmpiricalAsync>&a){
 if(a->retired||a->backend)throw std::logic_error("IRIS_OPU_ENTRY_ACCEPTED_WRITE_CANNOT_SQUASH");
 auto&pending=opu_pending_[h];auto it=std::find(pending.begin(),pending.end(),a);if(it!=pending.end())pending.erase(it);empirical_async_[h]=pending.empty()?nullptr:pending.front();
 if(async_trace_)*async_trace_<<"{\"event\":\"opu_front_cancel\",\"hart\":"<<h<<",\"instruction\":"<<a->instruction<<",\"cycle\":"<<clock_.now()<<"}\n";
}
void iris_timing_adapter::opu_check_irq()const{
 for(unsigned h=0;h<opu_pending_.size();++h)if(!opu_pending_[h].empty()&&cores_[h]->iris_pipeline_interrupt_exception())
  throw std::runtime_error("IRIS_OPU_ENTRY_ACTIVE_IRQ_CONTEXT_PHASE_UNMODELED");
}
void iris_timing_adapter::opu_write_totals(std::ostream&out)const{
 if(profile_.empirical_opu_fence)opu_fence_write_totals(out);
 if(profile_.empirical_opu_tk124)out<<",\"opu_K_scope\":\"source-K-outer-loop-TK1/2/4;per-K-physical-MACpoints;architectural-MRF-final-K-projection-only;allnonMMreads-drain;partialK-MRF-values-unavailable;COMplus1-conservative\"";
 if(profile_.empirical_opu_tk124)out<<",\"opu_entry_scope\":\"opt-in-source-VDQ4-IQ3-MM-entry-history;TK1/2/4-finalK-projection-only;stable-defined-VRF;M-mode;COMplus1-as-command-available-bridge-unqualified;predictive-admission-conservative-noCPUreplay;zero-move-discard-config-memory-drain-boundaries;activeIRQ-refused;unsupportedMM-CPUfetch-boundary-refused;all-conservative-fallbacks-drain;MM-family-effective-costs-not-applied\",\"opu_entry_metrics\":[";
 else out<<",\"opu_entry_scope\":\"opt-in-source-VDQ4-IQ3-MM-entry-history;TK1;stable-defined-VRF;M-mode;COMplus1-as-command-available-bridge-unqualified;predictive-admission-conservative-noCPUreplay;zero-move-discard-config-memory-drain-boundaries;activeIRQ-refused;unsupportedMM-CPUfetch-boundary-refused;all-conservative-fallbacks-drain;MM-family-effective-costs-not-applied\",\"opu_entry_metrics\":[";
 for(unsigned h=0;h<opu_pending_.size();++h){if(h)out<<',';out<<"{\"accepted\":"<<opu_accepted_[h]<<",\"entry_writes\":"<<(profile_.empirical_opu_tk124?opu_final_writes_[h]:opu_writes_[h])<<",\"peak_owned_commands\":"<<opu_peak_[h]<<",\"backend_queue_peak\":"<<opu_queue_peak_[h]<<",\"VDQ_full_edges\":"<<opu_full_edges_[h]<<",\"pending\":"<<opu_pending_[h].size()<<'}';}out<<']';
 if(profile_.empirical_opu_tk124){out<<",\"opu_K_completion_metrics\":[";for(unsigned h=0;h<opu_writes_.size();++h){if(h)out<<',';out<<"{\"completed_K_writes\":"<<opu_writes_[h]<<",\"final_entry_publications\":"<<opu_final_writes_[h]<<'}';}out<<']';}
}
