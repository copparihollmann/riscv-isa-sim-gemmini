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
  completion_reads_.push_back(row);
}

void iris_timing_adapter::finish_counter_reads(unsigned hart,uint64_t before) {
  if(profile_.source_counter_clock)source_counter_finish(hart,retired_.at(hart)==before+1);
  if (retired_.at(hart)==before+1) {
    for (auto& row:completion_reads_) {
      row.sequence=counter_sequences_.at(hart)++;
      counter_reads_.push_back(row);
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
