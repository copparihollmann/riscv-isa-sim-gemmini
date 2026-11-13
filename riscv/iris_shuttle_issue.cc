// Source-backed RRD classifier, unchanged from the primary source audit.
#include "../../../timing/shuttle_issue.cpp"

#include "iris_timing_adapter.h"
#include "iris_shuttle_rvc.h"
#include "processor.h"
#include <algorithm>
#include <limits>
#include <ostream>
#include <iomanip>
#include <set>
#include <stdexcept>

namespace {
using iris::shuttle::Signal;
using iris::shuttle::ResultStage;
bool base_integer(const iris::shuttle::Uop& u) {
  // Explicit first subset: known base RV64I scalar ALUs, not extension legality
  // inferred merely from a matching RTL control template.
  static const std::set<std::string> names = {
    "LUI","AUIPC","ADDI","SLTI","SLTIU","XORI","ORI","ANDI","SLLI","SRLI","SRAI",
    "ADD","SUB","SLL","SLT","SLTU","XOR","SRL","SRA","OR","AND",
    "ADDIW","SLLIW","SRLIW","SRAIW","ADDW","SUBW","SLLW","SRLW","SRAW"};
  return u.control_verified && u.uses_alu() && !u.cfi() && !u.exception &&
      names.count(u.instruction_name);
}
bool source_counter_read(const iris::shuttle::Uop& u) {
  const auto raw=u.expanded,csr=raw>>20,funct=(raw>>12)&7;
  return u.control_verified && u.has(iris::shuttle::CSR_EN) && (raw&127)==0x73 &&
      ((raw>>15)&31)==0 && (funct==2 || funct==3 || funct==6 || funct==7) &&
      (csr==0xb00 || csr==0xb02 || csr==0xc00 || csr==0xc02);
}
std::optional<iris::shuttle::Uop> pure_decode(const insn_fetch_t& fetch,bool compressed,bool counters) {
  auto insn=fetch.insn;
  const auto length=insn.length();
  uint32_t raw=uint32_t(insn.bits()),expanded=raw;
  if (length==2) {
    if (!compressed) return {};
    auto decoded=iris::shuttle::expand_compressed_alu(uint16_t(raw));
    if (!decoded) return {};
    raw=uint16_t(raw);expanded=decoded->expanded;
  } else if (length!=4) return {};
  auto uop=iris::shuttle::decode_scalar(expanded,raw,iris::shuttle::FrontendSignals::sequential_fixture());
  if (!base_integer(uop) && !(counters && length==4 && source_counter_read(uop))) return {};
  return uop;
}
uint64_t future_cycle(uint64_t now, uint64_t divider, unsigned stages) {
  const auto limit = std::numeric_limits<uint64_t>::max() - 1;
  if (divider > (limit-now)/stages) throw std::overflow_error("IRIS_PIPELINE_CYCLE_OVERFLOW");
  return now + divider*stages;
}
}

bool iris_timing_adapter::pure_candidate(unsigned hart, const insn_fetch_t& fetch) const {
  if (hart==2) return profile_.rocket_pure_pipeline && pure_decode(fetch,true,true).has_value();
  return profile_.shuttle_pure_pipeline && hart<2 && pure_decode(fetch,profile_.shuttle_rvc_pipeline,profile_.shuttle_counter_pipeline).has_value();
}

bool iris_timing_adapter::pure_begin(unsigned hart, reg_t pc, const insn_fetch_t& fetch) {
  if (!pure_candidate(hart,fetch) || clock_.now()%profile_.harts[hart].divider ||
      !cores_[hart]->iris_pipeline_can_prefetch(pc,hart==2 || profile_.shuttle_rvc_pipeline,hart==2)) return false;
  auto& p = pure_.at(hart);
  if (p.engaged || !p.packets.empty()) throw std::logic_error("IRIS_PIPELINE_ENTERED_WITH_INFLIGHT_STATE");
  if (p.next_commit != p.instructions.size()) throw std::logic_error("IRIS_PIPELINE_RETIREMENT_FRONTIER_INVALID");
  p.engaged = true; p.boundary = false; p.frontier = pc; p.deferred_fetch = {};
  p.last_writer.fill(std::nullopt);
  pure_dispatch(hart,&fetch);
  return true;
}

iris::shuttle::IssueSignals iris_timing_adapter::pure_signals(unsigned hart) const {
  const auto& p = pure_.at(hart);
  const auto divider = profile_.harts.at(hart).divider;
  const auto now = clock_.now();
  // Explicit uncalibrated fixture inputs: no frontend prediction, external
  // stall, FP/vector/long-latency writer. This is not an Iris idle default.
  auto signals = iris::shuttle::IssueSignals::empty_pipeline_fixture();
  std::vector<iris::shuttle::Bypass> bypasses;
  // Match RTL ll,WB,COM,MEM,EX override order. A held CSR remains in EX
  // beyond its original age; readiness follows its actual COM node.
  for (unsigned stage=4;stage>=1;--stage) {
    for (size_t index=p.first_live;index<p.instructions.size();++index) {
      const auto& instruction=p.instructions[index];
      if (instruction.released || instruction.exception || now<=instruction.rrd) continue;
      unsigned current=now<=instruction.ex_release ? 1 : now==instruction.com_cycle-divider ? 2 : now==instruction.com_cycle ? 3 : now==instruction.com_cycle+divider ? 4 : 0;
      if (current!=stage) continue;
      const bool ready = instruction.result && clock_.nodes().at(*instruction.result).completed;
      bypasses.push_back({instruction.uop.has(iris::shuttle::WXD),instruction.uop.rd,ready});
    }
  }
  for (unsigned reg=0;reg<32;++reg)
    signals.integer_hazard[reg] = iris::shuttle::integer_hazard(reg,true,bypasses) ? Signal::yes : Signal::no;
  for (size_t index=p.first_live;index<p.instructions.size();++index) {
    const auto& instruction=p.instructions[index];
    if (instruction.released || now<instruction.rrd) continue;
    if (now>instruction.rrd && now<=instruction.ex_release) signals.ex_busy=Signal::yes;
    if (now==instruction.com_cycle-divider) signals.mem_busy=Signal::yes;
    if (now==instruction.com_cycle) signals.com_busy=Signal::yes;
    // Source ex_fcsr_data_hazard: a CSR in EX blocks all RRD while
    // older MEM/COM registers remain valid, including their retire edge.
    if (instruction.counter && now>instruction.rrd && now<instruction.ex_release)
      signals.ex_stall=Signal::yes;
  }
  return signals;
}

void iris_timing_adapter::pure_dispatch(unsigned hart, const insn_fetch_t* first) {
  if (hart==2) {rocket_dispatch(hart,first);return;}
  auto& p = pure_.at(hart);
  if (!p.engaged) return;
  const auto now=clock_.now(), divider=profile_.harts.at(hart).divider;
  if (now%divider || (p.last_attempt && *p.last_attempt==now) || p.packets.size()>=4) return;
  p.last_attempt=now;
  if (pure_signals(hart).ex_stall==Signal::yes) return;
  const bool exception_inflight=!p.instructions.empty() && p.instructions.back().exception && !p.instructions.back().released;
  if (exception_inflight) return;
  if (!cores_[hart]->iris_pipeline_context_safe())
    throw std::runtime_error("IRIS_PIPELINE_CONTEXT_CHANGED_DURING_FLIGHT hart="+std::to_string(hart));
  if (auto exception=cores_[hart]->iris_pipeline_interrupt_exception()) {
    pure_exception(hart,exception); return;
  }
  if (p.boundary) {
    if (p.packets.empty()) { p.engaged=false; p.last_writer.fill(std::nullopt); }
    return;
  }
  if (p.deferred_fetch) { pure_exception(hart,p.deferred_fetch); p.deferred_fetch={}; return; }
  std::vector<std::pair<reg_t,insn_fetch_t>> fetched;
  std::vector<iris::shuttle::Uop> uops;
  reg_t next_pc=p.frontier;
  for (unsigned lane=0;lane<2;++lane) {
    const auto pc=next_pc;
    if (!cores_[hart]->iris_pipeline_can_prefetch(pc,profile_.shuttle_rvc_pipeline)) {
      p.boundary=true; break;
    }
    insn_fetch_t fetch;
    try { fetch=(first && lane==0) ? *first : cores_[hart]->get_mmu()->load_insn(pc); }
    catch (trap_t&) {
      if (lane==0) { pure_exception(hart,std::current_exception()); return; }
      p.deferred_fetch=std::current_exception(); break;
    }
    if (!pure_candidate(hart,fetch)) { p.boundary=true; break; }
    fetched.emplace_back(pc,fetch);
    uops.push_back(*pure_decode(fetch,profile_.shuttle_rvc_pipeline,profile_.shuttle_counter_pipeline));
    next_pc+=fetch.insn.length();
  }
  if (!fetched.empty()) {
    const auto plan=iris::shuttle::select_rrd(uops,pure_signals(hart));
    for (unsigned i=0;i<plan.ready_prefix;++i)
      if (!source_counter_read(uops[i]) && plan.lanes[i].integer_result_stage!=ResultStage::ex && plan.lanes[i].integer_result_stage!=ResultStage::mem)
        throw std::runtime_error("IRIS_PIPELINE_RESULT_STAGE_UNMODELED");
    if (plan.ready_prefix) {
      auto accepted=fetched; accepted.resize(plan.ready_prefix);
      pure_accept(hart,accepted,plan);
    }
    // A boundary discovered after slot0 must not hide a source data hazard:
    // retain the unaccepted frontier until that instruction can actually issue.
    if (plan.ready_prefix<fetched.size()) p.boundary=false;
  }
  if (p.boundary && p.packets.empty()) { p.engaged=false; p.last_writer.fill(std::nullopt); }
}

void iris_timing_adapter::pure_accept(unsigned hart,
    const std::vector<std::pair<reg_t,insn_fetch_t>>& fetched,const iris::shuttle::PacketPlan& plan) {
  auto& p=pure_.at(hart);const auto divider=profile_.harts[hart].divider;
  const auto now=clock_.now();const auto packet=p.next_packet++;
  const auto prefix="shuttle"+std::to_string(hart)+".";
  if (fetched.empty() || fetched.size()>2 || p.packets.size()>=4)
    throw std::logic_error("IRIS_PIPELINE_PACKET_CAPACITY");
  p.packets.push_back({packet,unsigned(fetched.size())});
  p.peak_packets=std::max(p.peak_packets,p.packets.size());
  for (unsigned lane=0;lane<fetched.size();++lane) {
    auto insn=fetched[lane].second.insn;
    PureInstruction instruction;
    instruction.pc=fetched[lane].first;instruction.fetch=fetched[lane].second;
    instruction.uop=*pure_decode(fetched[lane].second,profile_.shuttle_rvc_pipeline,profile_.shuttle_counter_pipeline);
    instruction.counter=source_counter_read(instruction.uop);
    instruction.result_stage=plan.lanes[lane].integer_result_stage;
    instruction.packet=packet;instruction.lane=lane;instruction.rrd=now;
    instruction.ex_release=future_cycle(now,divider,1);
    if (instruction.counter) {
      if (lane) throw std::logic_error("IRIS_COUNTER_READ_PIPE0_REQUIRED");
      for (size_t older=p.first_live;older<p.instructions.size();++older)
        if (!p.instructions[older].released)
          instruction.ex_release=std::max(instruction.ex_release,future_cycle(p.instructions[older].com_cycle,divider,1));
    }
    instruction.com_cycle=future_cycle(instruction.ex_release,divider,2);
    for (const auto& source: {std::pair{iris::shuttle::RXS1,instruction.uop.rs1},std::pair{iris::shuttle::RXS2,instruction.uop.rs2}})
      if (instruction.uop.has(source.first) && source.second && p.last_writer[source.second])
        instruction.raw_producers.push_back(*p.last_writer[source.second]);
    std::sort(instruction.raw_producers.begin(),instruction.raw_producers.end());
    instruction.raw_producers.erase(std::unique(instruction.raw_producers.begin(),instruction.raw_producers.end()),instruction.raw_producers.end());
    const auto id=p.instructions.size();p.instructions.push_back(std::move(instruction));
    auto& stored=p.instructions.at(id);
    const bool mem=stored.result_stage==ResultStage::mem;
    if (stored.counter) {
      iris::Op ex{hart,stored.uop.instruction_name+".EX-counter-hold",prefix+"CSR_EX",stored.ex_release-now,divider};
      ex.retires=false;ex.pc=stored.pc;ex.issue_period=divider;
      stored.csr_ex=clock_.issue(std::move(ex));
    } else {
      iris::Op result{hart,stored.uop.instruction_name+".result-ready",prefix+(mem?"MEM_ALU":"EX"),divider,divider};
      result.retires=false;result.pc=stored.pc;result.issue_period=divider;
      if (mem) result.earliest=future_cycle(now,divider,1);
      for (auto producer:stored.raw_producers) result.deps.push_back(*p.instructions.at(producer).result);
      stored.result=clock_.issue(std::move(result));
    }
    iris::Op commit{hart,stored.uop.instruction_name+".COM",prefix+"COM",divider,divider};
    commit.retires=false;commit.pc=stored.pc;commit.issue_period=divider;
    commit.earliest=stored.com_cycle-divider;commit.deps={stored.counter?*stored.csr_ex:*stored.result};
    commit.on_complete=[this,hart,id]{pure_commit(hart,id);};
    stored.com=clock_.issue(std::move(commit));
    if (stored.counter) stored.result=stored.com;
    iris::Op wb{hart,stored.uop.instruction_name+".WB",prefix+"WB",divider,divider};
    wb.retires=false;wb.pc=stored.pc;wb.issue_period=divider;wb.deps={*stored.com};
    wb.on_complete=[this,hart,id]{
      auto& p=pure_.at(hart);auto& row=p.instructions.at(id);
      if (p.packets.empty() || p.packets.front().id!=row.packet || !p.packets.front().remaining)
        throw std::logic_error("IRIS_PIPELINE_WB_ORDER");
      row.released=true;
      if (!--p.packets.front().remaining) p.packets.pop_front();
      while(p.first_live<p.instructions.size() && p.instructions[p.first_live].released) ++p.first_live;
    };
    stored.wb=clock_.issue(std::move(wb));previous_[hart]=stored.wb;
    if (stored.uop.rd) p.last_writer[stored.uop.rd]=id;
  }
  for (auto instruction:fetched) p.frontier+=instruction.second.insn.length();
}

void iris_timing_adapter::pure_exception(unsigned hart,std::exception_ptr exception) {
  auto& p=pure_.at(hart);const auto divider=profile_.harts[hart].divider;
  PureInstruction row;row.pc=p.frontier;row.fetch={nullptr,insn_t(0)};
  row.packet=p.next_packet++;row.rrd=clock_.now();row.exception=exception;
  row.ex_release=future_cycle(row.rrd,divider,1);row.com_cycle=future_cycle(row.rrd,divider,3);
  const auto id=p.instructions.size();p.instructions.push_back(row);
  p.packets.push_back({row.packet,1});p.peak_packets=std::max(p.peak_packets,p.packets.size());
  p.boundary=true;
  iris::Op op{hart,hart==2?"latched-ID-exception.WB":"latched-RRD-exception.COM",hart==2?"rocket2.WB":"shuttle"+std::to_string(hart)+".COM",divider,divider};
  op.pc=row.pc;op.retires=false;op.issue_period=divider;op.earliest=future_cycle(clock_.now(),divider,2);
  op.on_complete=[this,hart,id]{pure_commit(hart,id);};
  p.instructions.at(id).com=clock_.issue(std::move(op));previous_[hart]=p.instructions.at(id).com;
}

void iris_timing_adapter::pure_commit(unsigned hart,size_t id) {
  auto& p=pure_.at(hart);auto& row=p.instructions.at(id);
  if (id!=p.next_commit || cores_[hart]->get_state()->pc!=row.pc)
    throw std::runtime_error("IRIS_PIPELINE_PRECISE_COM_PC_MISMATCH hart="+std::to_string(hart));
  if (!cores_[hart]->iris_pipeline_context_safe())
    throw std::runtime_error("IRIS_PIPELINE_DEBUG_OR_PRIVILEGE_CHANGED_BEFORE_COM");
  completing_=hart;completing_pure_=id;completing_node_=row.com;completion_reads_.clear();const auto before=retired_[hart];
  try {cores_[hart]->step(1);} catch (...) {completion_reads_.clear();completing_node_.reset();completing_pure_.reset();completing_.reset();throw;}
  finish_counter_reads(hart,before);
  completing_pure_.reset();completing_.reset();++p.next_commit;++completions_;
  if (row.exception) {
    if (retired_[hart]!=before || p.packets.empty() || p.packets.front().id!=row.packet || p.packets.front().remaining!=1)
      throw std::logic_error("IRIS_PIPELINE_EXCEPTION_ORDER_OR_RETIREMENT");
    row.released=true;p.packets.pop_front();p.engaged=false;p.last_writer.fill(std::nullopt);
    while(p.first_live<p.instructions.size() && p.instructions[p.first_live].released) ++p.first_live;
    queue_trap(hart);
  } else {
    if (retired_[hart]!=before+1)
      throw std::runtime_error("IRIS_PIPELINE_UNEXPECTED_PURE_TRAP: timing subset refused");
    if (clock_.now()!=row.com_cycle)
      throw std::runtime_error("IRIS_PIPELINE_RETIREMENT_EDGE_CHANGED");
    row.retired=true;
    if (hart==2) {
      if (p.packets.empty() || p.packets.front().id!=row.packet || p.packets.front().remaining!=1)
        throw std::logic_error("IRIS_ROCKET_PIPELINE_WB_ORDER");
      row.released=true;p.packets.pop_front();
      while(p.first_live<p.instructions.size() && p.instructions[p.first_live].released) ++p.first_live;
    }
  }
}

void iris_timing_adapter::write_pure_json(std::ostream& out) const {
  out<<",\"shuttle_pipeline\":{\"enabled\":"<<(profile_.shuttle_pure_pipeline?"true":"false")
     <<",\"domain\":"<<std::quoted(profile_.shuttle_counter_pipeline ? "experimental-RV64IC-counter-read-sequential-frontend" : profile_.shuttle_rvc_pipeline ? "experimental-base-RV64IC-pure-sequential-frontend" : "experimental-base-RV64I-pure-32bit-sequential-frontend")
     <<",\"compressed_ALU_enabled\":"<<(profile_.shuttle_rvc_pipeline?"true":"false")
     <<",\"counter_reads_enabled\":"<<(profile_.shuttle_counter_pipeline?"true":"false")<<",\"calibrated\":false,\"peak_packets\":[";
  for(size_t h=0;h<pure_.size();++h){if(h)out<<',';out<<(h<2?pure_[h].peak_packets:0);}
  out<<"],\"instructions\":[";bool first=true;
  for(size_t h=0;h<std::min(size_t(2),pure_.size());++h) for(size_t i=0;i<pure_[h].instructions.size();++i){
    const auto& row=pure_[h].instructions[i];auto insn=row.fetch.insn;if(!first)out<<',';first=false;
    out<<"{\"hart\":"<<h<<",\"sequence\":"<<i<<",\"packet\":"<<row.packet<<",\"lane\":"<<row.lane
       <<",\"pc\":"<<row.pc<<",\"raw\":"<<(row.uop.compressed?uint16_t(insn.bits()):uint32_t(insn.bits()))
       <<",\"length\":"<<(row.exception?0:insn.length())<<",\"expanded\":"<<row.uop.expanded<<",\"RRD\":"<<row.rrd
       <<",\"result_stage\":"<<std::quoted(row.counter?"COM":iris::shuttle::stage_name(row.result_stage))
       <<",\"counter_read\":"<<(row.counter?"true":"false")<<",\"EX_release\":"<<row.ex_release
       <<",\"CSR_EX_node\":"<<(row.csr_ex?std::to_string(*row.csr_ex):"null")
       <<",\"result_node\":"<<(row.result?std::to_string(*row.result):"null")
       <<",\"COM_node\":"<<(row.com?std::to_string(*row.com):"null")<<",\"WB_node\":"<<(row.wb?std::to_string(*row.wb):"null")
       <<",\"retired\":"<<(row.retired?"true":"false")<<",\"released\":"<<(row.released?"true":"false")
       <<",\"latched_exception\":"<<(row.exception?"true":"false")<<",\"raw_producers\":[";
    for(size_t j=0;j<row.raw_producers.size();++j){if(j)out<<',';out<<row.raw_producers[j];}out<<"]}";
  }
  out<<"]}";
}

void iris_timing_adapter::rocket_dispatch(unsigned hart,const insn_fetch_t* first) {
  if (hart!=2 || !profile_.rocket_pure_pipeline) throw std::logic_error("IRIS_ROCKET_PIPELINE_HART_CONFIG");
  auto& p=pure_.at(hart);const auto now=clock_.now(),divider=profile_.harts[hart].divider;
  if (!p.engaged || now%divider || (p.last_attempt && *p.last_attempt==now) || p.packets.size()>=3) return;
  p.last_attempt=now;
  if (!p.instructions.empty() && p.instructions.back().exception && !p.instructions.back().released) return;
  if (!cores_[hart]->iris_pipeline_context_safe())
    throw std::runtime_error("IRIS_ROCKET_PIPELINE_CONTEXT_CHANGED_DURING_FLIGHT");
  if (auto exception=cores_[hart]->iris_pipeline_interrupt_exception()) {pure_exception(hart,exception);return;}
  if (p.boundary) {
    if (p.packets.empty()) {p.engaged=false;p.last_writer.fill(std::nullopt);}
    return;
  }
  const auto pc=p.frontier;
  if (!cores_[hart]->iris_pipeline_can_prefetch(pc,true,true)) {p.boundary=true;return;}
  insn_fetch_t fetch;
  try {fetch=first?*first:cores_[hart]->get_mmu()->load_insn(pc);}
  catch (trap_t&) {pure_exception(hart,std::current_exception());return;}
  auto uop=pure_decode(fetch,true,true);
  if (!uop) {p.boundary=true;return;}
  // Rocket ID interlocks CSR RAW/WAW in EX and MEM. Integer ALUs can
  // bypass through those stages; a CSR becomes available at WB, whose RF
  // write-through also supplies ID on that edge. No Shuttle packet rules.
  for (size_t index=p.first_live;index<p.instructions.size();++index) {
    const auto& older=p.instructions[index];
    if (older.released || older.exception || !older.counter || !older.uop.rd || now>=older.com_cycle) continue;
    const auto rd=older.uop.rd;
    if ((uop->has(iris::shuttle::RXS1) && uop->rs1==rd) ||
        (uop->has(iris::shuttle::RXS2) && uop->rs2==rd) ||
        (uop->has(iris::shuttle::WXD) && uop->rd==rd)) return;
  }
  rocket_accept(hart,pc,fetch);
}

void iris_timing_adapter::rocket_accept(unsigned hart,reg_t pc,const insn_fetch_t& fetch) {
  auto& p=pure_.at(hart);const auto now=clock_.now(),divider=profile_.harts[hart].divider;
  auto decoded=pure_decode(fetch,true,true);
  if (hart!=2 || !decoded || p.packets.size()>=3) throw std::logic_error("IRIS_ROCKET_PIPELINE_ACCEPT_DOMAIN");
  PureInstruction row;row.pc=pc;row.fetch=fetch;row.uop=*decoded;row.counter=source_counter_read(row.uop);
  row.packet=p.next_packet++;row.rrd=now;row.ex_release=future_cycle(now,divider,1);row.com_cycle=future_cycle(now,divider,3);
  row.result_stage=row.counter?ResultStage::wb:ResultStage::ex;
  for (const auto& source:{std::pair{iris::shuttle::RXS1,row.uop.rs1},std::pair{iris::shuttle::RXS2,row.uop.rs2}})
    if (row.uop.has(source.first) && source.second && p.last_writer[source.second]) row.raw_producers.push_back(*p.last_writer[source.second]);
  std::sort(row.raw_producers.begin(),row.raw_producers.end());row.raw_producers.erase(std::unique(row.raw_producers.begin(),row.raw_producers.end()),row.raw_producers.end());
  const auto id=p.instructions.size();p.instructions.push_back(std::move(row));auto& stored=p.instructions.at(id);
  p.packets.push_back({stored.packet,1});p.peak_packets=std::max(p.peak_packets,p.packets.size());
  iris::Op ex{hart,stored.uop.instruction_name+(stored.counter?".EX-operands":".result-ready"),"rocket2.EX",divider,divider};
  ex.retires=false;ex.pc=pc;ex.issue_period=divider;
  for (auto producer:stored.raw_producers) ex.deps.push_back(*p.instructions.at(producer).result);
  stored.csr_ex=clock_.issue(std::move(ex));if (!stored.counter) stored.result=stored.csr_ex;
  iris::Op mem{hart,stored.uop.instruction_name+".MEM","rocket2.MEM",divider,divider};
  mem.retires=false;mem.pc=pc;mem.issue_period=divider;mem.deps={*stored.csr_ex};stored.mem=clock_.issue(std::move(mem));
  iris::Op wb{hart,stored.uop.instruction_name+".WB","rocket2.WB",divider,divider};
  wb.retires=false;wb.pc=pc;wb.issue_period=divider;wb.deps={*stored.mem};wb.on_complete=[this,hart,id]{pure_commit(hart,id);};
  stored.com=clock_.issue(std::move(wb));stored.wb=stored.com;if (stored.counter) stored.result=stored.com;
  previous_[hart]=stored.com;if (stored.uop.rd) p.last_writer[stored.uop.rd]=id;
  auto instruction=fetch.insn;p.frontier+=instruction.length();
}

void iris_timing_adapter::write_rocket_json(std::ostream& out) const {
  out<<",\"rocket_pipeline\":{\"enabled\":"<<(profile_.rocket_pure_pipeline?"true":"false")
     <<",\"domain\":\"experimental-RV64IC-counter-read-sequential-frontend\",\"calibrated\":false,\"peak_packets\":"
     <<(pure_.size()>2?pure_[2].peak_packets:0)<<",\"instructions\":[";
  bool first=true;
  if (pure_.size()>2) for(size_t i=0;i<pure_[2].instructions.size();++i) {
    const auto& row=pure_[2].instructions[i];auto insn=row.fetch.insn;if(!first)out<<',';first=false;
    out<<"{\"hart\":2,\"sequence\":"<<i<<",\"packet\":"<<row.packet<<",\"pc\":"<<row.pc
       <<",\"raw\":"<<(row.uop.compressed?uint16_t(insn.bits()):uint32_t(insn.bits()))<<",\"length\":"<<(row.exception?0:insn.length())
       <<",\"expanded\":"<<row.uop.expanded<<",\"ID\":"<<row.rrd<<",\"result_stage\":"<<std::quoted(row.counter?"WB":"EX")
       <<",\"counter_read\":"<<(row.counter?"true":"false")
       <<",\"EX_node\":"<<(row.csr_ex?std::to_string(*row.csr_ex):"null")<<",\"MEM_node\":"<<(row.mem?std::to_string(*row.mem):"null")
       <<",\"result_node\":"<<(row.result?std::to_string(*row.result):"null")<<",\"WB_node\":"<<(row.wb?std::to_string(*row.wb):row.com?std::to_string(*row.com):"null")
       <<",\"retired\":"<<(row.retired?"true":"false")<<",\"released\":"<<(row.released?"true":"false")
       <<",\"latched_exception\":"<<(row.exception?"true":"false")<<",\"raw_producers\":[";
    for(size_t j=0;j<row.raw_producers.size();++j){if(j)out<<',';out<<row.raw_producers[j];}out<<"]}";
  }
  out<<"]}";
}
