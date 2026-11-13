#include "iris_timing_adapter.h"
#include <iomanip>
#include <stdexcept>

void iris_timing_adapter::counter_read(unsigned hart,reg_t pc,uint32_t raw,unsigned csr,reg_t value,unsigned destination,const char* phase) {
  if (!completing_ || *completing_!=hart || !completing_node_)
    throw std::logic_error("IRIS_COUNTER_READ_OUTSIDE_INSTRUCTION_COMPLETION");
  const auto* fetch=completion_fetch(hart);
  if (!fetch) throw std::logic_error("IRIS_COUNTER_READ_WITHOUT_PREPARED_INSTRUCTION");
  auto instruction=fetch->insn;
  const auto& node=clock_.nodes().at(*completing_node_);
  if (instruction.length()!=4 || uint32_t(instruction.bits())!=raw || node.op.pc!=pc || node.op.hart!=hart ||
      !node.issued || node.end!=clock_.now() || (raw>>20)!=csr || ((raw>>7)&31)!=destination)
    throw std::logic_error("IRIS_COUNTER_READ_INSTRUCTION_CONTEXT_MISMATCH");
  if (!completion_reads_.empty()) throw std::logic_error("IRIS_MULTIPLE_COUNTER_READS_IN_ONE_INSTRUCTION");
  CounterRead row;row.node=*completing_node_;row.hart=hart;row.pc=pc;row.raw=raw;row.csr=csr;
  row.value=value;row.destination=destination;row.read_cycle=clock_.now();row.phase=phase;
  if(profile_.empirical){row.features=features_[hart];row.memory=memory_features_[hart];row.retired=retired_[hart];row.busy=clock_.completed_busy_by_resource();row.occupancy=clock_.occupancy_prefix();for(const auto&actor:{empirical_async_[hart],empirical_async_next_[hart]})if(actor){row.async_pending=true;++row.async_pending_count;const auto node=actor->backend;if(node){const auto&n=clock_.nodes().at(*node);row.async_backend_end=std::max(row.async_backend_end,n.issued?n.end:0);}}}
  if(profile_.empirical_fadd_eg&&hart<2&&!fadd_eg_pending_[hart].empty()){row.async_pending=true;row.async_pending_count=fadd_eg_pending_[hart].size();row.async_backend_end=0;} // source queue has no guessed whole-command end
  if(profile_.empirical_opu_entry&&!opu_pending_[hart].empty()){row.async_pending=true;row.async_pending_count=opu_pending_[hart].size();for(const auto&actor:opu_pending_[hart])if(actor->backend){const auto&n=clock_.nodes().at(*actor->backend);row.async_backend_end=std::max(row.async_backend_end,n.issued?n.end:0);}}
  if(profile_.empirical_scalar_fadd)for(const auto&a:scalar_fadd_[hart])if(!a->done&&!a->killed){if(a->accepted)++row.scalar_fp_accepted;else ++row.scalar_fp_queued;row.scalar_fp_next_write=std::max(row.scalar_fp_next_write,a->write);}
  if(profile_.empirical&&frontend_enabled(hart)&&frontend_[hart].active_refill){
    const auto&f=frontend_[hart];const auto&refill=f.refills.at(*f.active_refill);
    if(!refill.cache_owner||refill.beats.size()!=8||refill.returned>=8)
      throw std::logic_error("IRIS_SOURCE_ICACHE_PREFIX_OWNER_MISSING");
    const auto id=refill.beats.back();const auto&n=clock_.nodes().at(id);
    row.pending_fetch=EmpiricalFetchObservation{*refill.cache_owner,id,refill.address,64,1,refill.l2_misses,n.submitted,n.start,n.end,n.issued};
    row.source_fetch_sampled_beats=refill.returned;
    row.source_fetch_next_edge=f.next_edge;row.source_fetch_period=profile_.harts[hart].divider;
    row.source_fetch_final_graph_completed=n.completed;
    if(!row.source_fetch_period||row.source_fetch_next_edge<row.source_fetch_period||row.source_fetch_next_edge<row.read_cycle)
      throw std::logic_error("IRIS_SOURCE_ICACHE_PREFIX_CLOCK_PHASE_UNKNOWN");
    row.source_fetch_final_input_present=refill.returned==7&&bool(f.inputs.memory_data);
  }else if(profile_.empirical&&empirical_fetch_[hart].owner){const auto&f=empirical_fetch_[hart];const auto id=cache_nodes_.at(*f.owner);const auto&n=clock_.nodes().at(id);row.pending_fetch=EmpiricalFetchObservation{*f.owner,id,f.address,f.bytes,f.l1_misses,f.l2_misses,n.submitted,n.start,n.end,n.issued};}
  completion_reads_.push_back(std::move(row));
}

void iris_timing_adapter::finish_counter_reads(unsigned hart,uint64_t before) {
  if(profile_.source_counter_clock)source_counter_finish(hart,retired_.at(hart)==before+1);
  if (retired_.at(hart)==before+1) {
    for (auto& row:completion_reads_) {
      row.sequence=counter_sequences_.at(hart)++;
      if(profile_.empirical)empirical_write_prefix(row);
      if(profile_.keep_history)counter_reads_.push_back(row);
    }
  } else if (retired_.at(hart)!=before)
    throw std::logic_error("IRIS_COUNTER_READ_RETIREMENT_COUNT_INVALID");
  // A read made by an instruction that traps before architectural retirement
  // must never look like an observable guest result. Exceptions clear this
  // buffer too, including C++ model refusals rather than architectural traps.
  completion_reads_.clear();completing_node_.reset();
}

void iris_timing_adapter::write_counter_reads(std::ostream& out) const {
  out<<",\"counter_read_observations\":{\"schema_version\":1,\"complete\":true,"
     <<"\"source\":\"native processor get_csr non-peek evaluations; per-read named model phase; emitted only after architectural retirement; Iris source counter-edge policy v1 when enabled\",\"reads\":[";
  bool first=true;
  for (const auto& row:counter_reads_) {
    if (!first) out<<',';first=false;
    out<<"{\"sequence\":"<<row.sequence<<",\"node\":"<<row.node<<",\"hart\":"<<row.hart
       <<",\"pc\":"<<row.pc<<",\"raw\":"<<row.raw<<",\"csr\":"<<row.csr<<",\"value\":"<<row.value
       <<",\"destination\":"<<row.destination<<",\"result_discarded\":"<<(row.destination==0?"true":"false")
       <<",\"read_cycle\":"<<row.read_cycle<<",\"read_phase\":"<<std::quoted(row.phase)<<"}";
  }
  out<<"]}";
}
