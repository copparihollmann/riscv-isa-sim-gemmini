#include "iris_timing_adapter.h"
#include "processor.h"
#include <iomanip>
#include <ostream>
#include <stdexcept>

bool iris_timing_adapter::source_counter_pre_edge(unsigned hart,Cycle cycle) {
  if(!profile_.source_counter_clock)throw std::logic_error("IRIS_SOURCE_COUNTER_POLICY_NOT_ENABLED");
  auto* core=cores_.at(hart);auto* state=core->get_state();
  // Device lines are sampled before sim_t advances the devices for this edge.
  // The native functional delivery path supplies these inputs; this method
  // does not invent an interrupt-crossing delay or infer global MIE gating.
  iris::frontend::SourceCounterClock::Input input;
  try {core->iris_validate_interrupts();}catch(...) {input.unknown_pending=std::current_exception();}
  input.locally_enabled_pending=(state->mip->read()&state->mie->read())!=0;
  const auto edge=source_counter_clocks_.at(hart).sample(cycle,input);
  if(edge.stall_before && !edge.stall_after)core->clear_waiting_for_interrupt();
  if(edge.stall_before!=edge.stall_after)
    counter_clock_transitions_.push_back({hart,cycle,edge.stall_before,edge.stall_after,"source-locally-enabled-interrupt-wake"});
  return edge.count_enable;
}

void iris_timing_adapter::source_counter_finish(unsigned hart,bool retired) {
  auto& clock=source_counter_clocks_.at(hart);const auto cycle=clock_.now();const bool before=clock.stalled();
  if(!retired)clock.exception(cycle);
  else {
    const auto* fetch=completion_fetch(hart);
    if(!fetch)throw std::logic_error("IRIS_SOURCE_COUNTER_RETIREMENT_WITHOUT_INSTRUCTION");
    auto insn=fetch->insn;const uint32_t raw=insn.bits();
    if(raw==0x10500073)clock.retire_wfi(cycle);
    if(raw==0x30500073)clock.retire_cease(cycle);
  }
  const bool after=clock.stalled();
  if(before!=after)counter_clock_transitions_.push_back({hart,cycle,before,after,retired?"source-successful-system-COM":"source-exception-COM"});
  // Spike's architectural waiting flag is a transport detail. An already
  // pending locally enabled IRQ wins over WFI entry in the source CSR unit.
  if(!after && cores_[hart]->is_waiting_for_interrupt())cores_[hart]->clear_waiting_for_interrupt();
}

void iris_timing_adapter::write_source_counter_json(std::ostream& out) const {
  if(!profile_.source_counter_clock)return;
  out<<",\"source_counter_clock\":{\"policy\":\"CSRFile-ungated-pre-edge-stall\",\"source\":\"rocket-chip-fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0-CSR.scala650-1093-1231\","
     <<"\"numeric_count_wfi\":\"legacy-synthetic-only-rejected-in-this-policy\",\"interrupt_phase\":\"native-device-lines-before-device-edge-update\",\"interrupt_sync_crossing_timing_qualified\":false,\"idle_skipping\":false,\"transitions\":[";
  for(size_t i=0;i<counter_clock_transitions_.size();++i) {
    if(i)out<<',';const auto& t=counter_clock_transitions_[i];
    out<<"{\"hart\":"<<t.hart<<",\"cycle\":"<<t.cycle<<",\"stall_before\":"<<(t.before?"true":"false")<<",\"stall_after\":"<<(t.after?"true":"false")<<",\"reason\":"<<std::quoted(t.reason)<<'}';
  }
  out<<"]}";
}
