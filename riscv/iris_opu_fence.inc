// Finite source FM0 FENCE admission. Numeric ownership remains unchanged.
// Source proofs: build/opu-fence-source-v1/report.json.
bool iris_timing_adapter::opu_fence_eligible(unsigned h,const insn_fetch_t&fetch){
 if(!profile_.empirical_opu_fence||h>=2)return false;
 opu_fence_retry_[h].reset();
 auto instruction=fetch.insn;const auto word=uint32_t(instruction.bits());
 if(word!=0x0ff0000fU&&word!=0x0330000fU)return false;
 if(opu_pending_[h].empty())return false;
 const auto*state=cores_[h]->get_state();
 if(state->prv!=PRV_M||state->v||state->debug_mode)return false;
 // Existing IRQ/FADD/scalar-memory restrictions remain. Do not infer physical
 // idle from a numeric tail alone or accelerate an unqualified memory domain.
 if(cores_[h]->iris_pipeline_interrupt_exception()||scalar_fadd_pending(h)||store_deferred_[h]||pending_[h])return false;
 if(pure_[h].values&&pure_[h].values->pending_external_count())return false;
 if(empirical_cache_->pending())return false;
 for(const auto&a:opu_pending_[h])if(!a->opu_entry||!a->retired||!a->opu_queued)return false;
 if(!pure_[h].packets.empty()||!opu_queues_[h].empty())return false;
 const auto divider=profile_.harts[h].divider;
 if(clock_.now()%divider)return false;
 const auto edge=clock_.now()/divider;const auto last=opu_queues_[h].last_edge();
 // Queue::step consumes the edge. A tail consumed at E still made the source
 // busy BEFORE E; its now-empty poststate is only available to RRD at E+1.
 if(last&&*last==edge&&opu_fence_prebusy_[h]){
  if(divider>=UINT64_MAX-clock_.now())throw std::overflow_error("IRIS_OPU_FENCE_RETRY_HORIZON");
  opu_fence_retry_[h]=clock_.now()+divider;return false;
 }
 if(last&&*last>edge)throw std::logic_error("IRIS_OPU_FENCE_FUTURE_QUEUE_EDGE");
 return true;
}
void iris_timing_adapter::opu_fence_observe(unsigned h,const iris::opu_entry::QueueEdgeTK&o){
 opu_fence_prebusy_[h]=o.vdq_before||o.iq_before||o.seq_before;
}
void iris_timing_adapter::opu_fence_write_totals(std::ostream&out)const{
 out<<",\"opu_FM0_fence_scope_override\":\"default-OFF;only0330000f/0ff0000f;sourceMM-only-front-VDQ-IQ-SEQ-busy-clear;preedge-tail-guard;conservative-memory-FADD-IRQ-and-CPU-drain;numeric-MRF-tail-kept;all-other-boundaries-and-consumers-drain;COMplus1-input-bridge-unchanged;no-full-CPU-memorywire-certificate\",\"opu_FM0_fence_admissions\":[";
 for(unsigned h=0;h<opu_fence_admissions_.size();++h){if(h)out<<',';out<<opu_fence_admissions_[h];}out<<']';
}
