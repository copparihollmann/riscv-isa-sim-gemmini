// Source-backed RRD classifier, unchanged from the primary source audit.
#include "../iris/timing/shuttle_issue.cpp"

#include "iris_timing_adapter.h"
#include "../iris/pipeline/empirical_hazards.hpp"
#include "iris_shuttle_rvc.h"
#include "../iris/pipeline/fast_source_rvc_table.hpp"
#include "processor.h"
#include <algorithm>
#include <limits>
#include <ostream>
#include <iomanip>
#include <set>
#include <sstream>
#include <fstream>
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
std::optional<iris::shuttle::Uop> empirical_unit_decode(uint32_t raw,bool fadd=false){
 const unsigned op=raw&127,f3=(raw>>12)&7,f6=raw>>26;
 const bool matrix=(raw&MASK_VTMMU_TVV)==MATCH_VTMMU_TVV||(raw&MASK_VTMMS_TVV)==MATCH_VTMMS_TVV||(raw&MASK_VTFMM_TVV)==MATCH_VTFMM_TVV||(raw&MASK_VTFMM_ALT_TVV)==MATCH_VTFMM_ALT_TVV||(raw&MASK_VTZERO)==MATCH_VTZERO||(raw&MASK_VTMV_T_V)==MATCH_VTMV_T_V||(raw&MASK_VTMV_V_T)==MATCH_VTMV_V_T||(raw&MASK_VTDISCARD)==MATCH_VTDISCARD;
 const bool integer=op==0x57&&(f3==0||f3==3||f3==4)&&(f6==0||f6==2||f6==9||f6==10||f6==11||f6==0x17||f6==0x25||f6==0x28||f6==0x29);
 const bool fp_add=fadd&&op==0x57&&f3==1&&f6==0;
 if(!matrix&&!integer&&!fp_add)return{};
 iris::shuttle::Uop u;u.expanded=u.raw=raw;u.controls=iris::shuttle::VECTOR;if(op==0x57&&(f3==4||f3==6))u.controls|=iris::shuttle::RXS1;u.rs1=(raw>>15)&31;u.rs2=(raw>>20)&31;u.rd=(raw>>7)&31;u.control_verified=true;u.instruction_name=matrix?"empirical-VME-front":fp_add?"empirical-RVV-FADD-front":"empirical-RVV-integer-front";u.predicted_next_pc_valid=iris::shuttle::Signal::no;u.sfb_branch=iris::shuttle::Signal::no;u.decode_note="finite EarlyVectorDecode override; empirical backend timing";return u;
}
std::optional<iris::shuttle::Uop> pure_decode_uncached(const insn_fetch_t& fetch,bool compressed,bool counters,bool branches=false,bool asynchronous=false,bool loads=false,bool fadd=false,bool scalar_fadd=false,bool stores=false) {
  auto insn=fetch.insn;
  const auto length=insn.length();
  uint32_t raw=uint32_t(insn.bits()),expanded=raw;
  if (length==2) {
    if (!compressed) return {};
    auto decoded=iris::shuttle::expand_compressed_alu(uint16_t(raw));
    if(!decoded&&loads){insn_t ci{uint16_t(raw)};const unsigned q=raw&3,f=(raw>>13)&7,rd=(raw>>7)&31;const bool word=f==2;uint32_t out=0;if(q==0&&(f==2||f==3)){const uint32_t imm=word?ci.rvc_lw_imm():ci.rvc_ld_imm();out=(imm<<20)|((8+((raw>>7)&7))<<15)|((word?2:3)<<12)|((8+((raw>>2)&7))<<7)|3;}else if(q==2&&(f==2||f==3)&&rd){const uint32_t imm=word?ci.rvc_lwsp_imm():ci.rvc_ldsp_imm();out=(imm<<20)|(2<<15)|((word?2:3)<<12)|(rd<<7)|3;}if(out)decoded=iris::shuttle::CompressedAlu{out,"experimental-RVC-load"};}
    if(!decoded&&stores){const auto x=iris::frontend::expand_source_rvc(uint16_t(raw));if((x&127)==0x23&&((x>>12)&7)<=3)decoded=iris::shuttle::CompressedAlu{x,"experimental-RVC-integer-store"};}
    if (!decoded && branches){insn_t ci{uint16_t(raw)};const auto q=raw&3,funct=raw>>13,rs1=(raw>>7)&31,rs2=(raw>>2)&31;uint32_t out=0;
      if(q==1&&funct==5){const uint32_t imm=ci.rvc_j_imm();out=((imm&0x100000)<<11)|((imm&0x7fe)<<20)|((imm&0x800)<<9)|(imm&0xff000)|0x6f;}
      else if(q==1&&(funct==6||funct==7)){const uint32_t imm=ci.rvc_b_imm();out=((imm&0x1000)<<19)|((imm&0x7e0)<<20)|((8+((raw>>7)&7))<<15)|((funct==7?1:0)<<12)|((imm&0x1e)<<7)|((imm&0x800)>>4)|0x63;}
      else if(q==2&&funct==4&&rs1&&rs2==0)out=(rs1<<15)|(((raw>>12)&1)<<7)|0x67;
      if(out)decoded=iris::shuttle::CompressedAlu{out,"experimental-CFI"};
    }
    if (!decoded) return {};
    raw=uint16_t(raw);expanded=decoded->expanded;
  } else if (length!=4) return {};
  if(asynchronous&&length==4)if(auto u=empirical_unit_decode(raw,fadd))return u;
  auto uop=iris::shuttle::decode_scalar(expanded,raw,iris::shuttle::FrontendSignals::sequential_fixture());
  const bool scalar_add=scalar_fadd && length==4 && ((raw&0xfe00007f)==0x53 || (raw&0xfe00007f)==0x02000053 || (raw&0xfe00007f)==0x04000053);
  if (!scalar_add && !base_integer(uop) && !(counters && length==4 && source_counter_read(uop)) && !(branches&&uop.cfi()) && !(loads&&uop.has(iris::shuttle::MEM)&&(expanded&127)==3&&((expanded>>12)&7)<=6) && !(stores&&uop.has(iris::shuttle::MEM)&&(expanded&127)==0x23&&((expanded>>12)&7)<=3)) return {};
  return uop;
}
// The decoder below has only immutable raw bits and explicit fixed frontend
// flags as inputs. A bounded direct-mapped host cache changes no model state,
// timestamps or legality decisions. In particular no PC/config/CSR enters it.
std::optional<iris::shuttle::Uop> pure_decode(const insn_fetch_t& fetch,bool compressed,bool counters,bool branches=false,bool asynchronous=false,bool loads=false,bool fadd=false,bool scalar_fadd=false,bool stores=false) {
  if(!branches)return pure_decode_uncached(fetch,compressed,counters,branches,asynchronous,loads,fadd,scalar_fadd,stores);
  struct Entry{uint64_t key=0;bool valid=false;std::optional<iris::shuttle::Uop> value;};
  static thread_local std::array<Entry,2048> memo;
  const uint64_t flags=uint64_t(compressed)|(uint64_t(counters)<<1)|(uint64_t(branches)<<2)|(uint64_t(asynchronous)<<3)|(uint64_t(loads)<<4)|(uint64_t(fadd)<<5)|(uint64_t(scalar_fadd)<<6)|(uint64_t(stores)<<7);
  auto instruction=fetch.insn;const uint64_t key=uint32_t(instruction.bits())|(flags<<32);
  const uint64_t mixed=(key^(key>>17))*0x9e3779b97f4a7c15ull;
  auto&e=memo[(mixed>>32)&2047];if(e.valid&&e.key==key)return e.value;
  auto value=pure_decode_uncached(fetch,compressed,counters,branches,asynchronous,loads,fadd,scalar_fadd,stores);
  e.key=key;e.valid=true;e.value=value;return value;
}
std::optional<uint64_t> private_xpr_value(processor_t* core,unsigned reg) {
  const auto v=core->get_state()->XPR.read_transport(reg);
  if(std::all_of(v.known.begin(),v.known.end(),[](uint8_t bits){return bits==0xff;}))return v.value;
  return {};
}
uint64_t future_cycle(uint64_t now, uint64_t divider, unsigned stages) {
  const auto limit = std::numeric_limits<uint64_t>::max() - 1;
  if (divider > (limit-now)/stages) throw std::overflow_error("IRIS_PIPELINE_CYCLE_OVERFLOW");
  return now + divider*stages;
}
}


void iris_timing_adapter::cpu_event(unsigned h,const char*event,uint64_t pc,uint32_t raw,size_t id,const std::string&fields)const{
 if(!cpu_trace_||h!=cpu_trace_hart_||clock_.now()<cpu_trace_first_||clock_.now()>cpu_trace_last_)return;
 if(cpu_trace_roi_stride_&&(!cpu_trace_mcycle_counts_.at(h)||cpu_trace_mcycle_counts_.at(h)%cpu_trace_roi_stride_==0))return;
 if(!cpu_trace_event_filter_.empty()&&cpu_trace_event_filter_.find(","+std::string(event)+",")==std::string::npos)return;
 auto&out=*cpu_trace_;out<<"{\"schema\":\"iris.CPU_diagnostic.v1\",\"event\":"<<std::quoted(event)<<",\"cycle\":"<<clock_.now()<<",\"hart\":"<<h<<",\"pc\":"<<pc<<",\"raw\":"<<raw<<",\"instruction\":";if(id==SIZE_MAX)out<<"null";else out<<id;if(!fields.empty())out<<','<<fields;out<<"}\n";out.flush();
}

std::optional<iris::shuttle::Uop> iris_timing_adapter::pure_decode_for_frontend(const insn_fetch_t&fetch)const{
  return pure_decode(fetch,true,true,true,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,profile_.empirical_store_front);
}

bool iris_timing_adapter::vadd_eg_scalar_allowed(const insn_fetch_t&fetch)const{
 auto u=pure_decode(fetch,true,true,true,false,false,false,false,false);return u&&(base_integer(*u)||u->cfi()||source_counter_read(*u));
}

bool iris_timing_adapter::fadd_eg_scalar_allowed(const insn_fetch_t&fetch)const{
 auto u=pure_decode(fetch,true,profile_.empirical_fadd_eg_counter_csr,true,false,false,false,false,false);return u&&(base_integer(*u)||u->cfi()||(profile_.empirical_fadd_eg_counter_csr&&source_counter_read(*u)));
}

bool iris_timing_adapter::frontend_uop_candidate(unsigned hart,const iris::shuttle::Uop&u)const{
 if(profile_.empirical_vadd_eg&&hart<2&&!vadd_eg_pending_[hart].empty()&&!((u.expanded&0xfc00707f)==0x57)&&!base_integer(u)&&!u.cfi()&&!source_counter_read(u))return false;
    if(profile_.empirical_fadd_eg&&hart<2&&!fadd_eg_pending_[hart].empty()&&u.instruction_name!="empirical-RVV-FADD-front"&&!base_integer(u)&&!u.cfi()&&!(profile_.empirical_fadd_eg_counter_csr&&source_counter_read(u)))return false;
    if(!u.control_verified||u.exception)return false;
    if(scalar_fadd_candidate(hart,u))return true;
    if(u.has(iris::shuttle::VECTOR)){
      if(profile_.empirical_scalar_fadd&&scalar_fadd_pending(hart))return false;
      if(!profile_.empirical_async)return false;
      const auto*state=cores_[hart]->get_state();
      if(cores_[hart]->VU.vill||cores_[hart]->VU.vstart->read()||!(state->mstatus->read()&MSTATUS_VS))return false;
      if(u.instruction_name=="empirical-RVV-FADD-front"&&(!profile_.empirical_async_fadd||state->prv!=PRV_M||state->v||!(state->mstatus->read()&MSTATUS_FS)||(cores_[hart]->VU.vsew!=8&&cores_[hart]->VU.vsew!=16&&cores_[hart]->VU.vsew!=32&&cores_[hart]->VU.vsew!=64)))return false;
      return true;
    }
    return base_integer(u)||source_counter_read(u)||u.cfi()||empirical_load_candidate(hart,u)||empirical_store_candidate(hart,u);
}

bool iris_timing_adapter::pure_candidate(unsigned hart, const insn_fetch_t& fetch) const {
  if(profile_.empirical_vadd_eg&&hart<2&&!vadd_eg_pending_[hart].empty()&&!vadd_eg_is_vv(&fetch)&&!vadd_eg_scalar_allowed(fetch))return false;
  if(profile_.empirical_fadd_eg&&hart<2&&!fadd_eg_pending_[hart].empty()&&!fadd_eg_is_vv(&fetch)&&!fadd_eg_scalar_allowed(fetch))return false;
  if(frontend_enabled(hart)){const auto u=frontend_decode(hart,fetch);return u&&frontend_uop_candidate(hart,*u);}
  if(hart==2 && rocket_frontend_enabled()) {const auto u=rocket_frontend_decode(fetch);return u && u->control_verified && !u->exception && (base_integer(*u)||source_counter_read(*u)||u->cfi()||rocket_memory_decode(*u));}
  if(profile_.empirical_scalar_fadd){auto instruction=fetch.insn;auto u=iris::shuttle::decode_scalar(uint32_t(instruction.bits()),uint32_t(instruction.bits()),iris::shuttle::FrontendSignals::sequential_fixture());if((u.expanded&0xfe00007f)==0x53||(u.expanded&0xfe00007f)==0x02000053||(u.expanded&0xfe00007f)==0x04000053)return scalar_fadd_candidate(hart,u);if(scalar_fadd_pending(hart)&&empirical_unit_decode(uint32_t(instruction.bits()),profile_.empirical_async_fadd))return false;}
  if(profile_.empirical_async){auto instruction=fetch.insn;if(auto unit=empirical_unit_decode(uint32_t(instruction.bits()),profile_.empirical_async_fadd)){if(cores_[hart]->VU.vill||cores_[hart]->VU.vstart->read()||!(cores_[hart]->get_state()->mstatus->read()&MSTATUS_VS))return false;if(hart==2&&unit->instruction_name=="empirical-VME-front")return false;if(unit->instruction_name=="empirical-RVV-FADD-front"&&(cores_[hart]->get_state()->v||cores_[hart]->get_state()->prv!=PRV_M||!(cores_[hart]->get_state()->mstatus->read()&MSTATUS_FS)||(cores_[hart]->VU.vsew!=8&&cores_[hart]->VU.vsew!=16&&cores_[hart]->VU.vsew!=32&&cores_[hart]->VU.vsew!=64)||(hart==2&&(cores_[hart]->VU.vsew==8||cores_[hart]->VU.altfmt))))return false;}}
  auto candidate=pure_decode(fetch,true,true,profile_.empirical,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,profile_.empirical_store_front);if(candidate&&candidate->has(iris::shuttle::MEM)&&!empirical_load_candidate(hart,*candidate)&&!empirical_store_candidate(hart,*candidate))return false;
  if (hart==2) return profile_.rocket_pure_pipeline && pure_decode(fetch,true,true,profile_.empirical,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,profile_.empirical_store_front).has_value();
  return profile_.shuttle_pure_pipeline && hart<2 && pure_decode(fetch,profile_.shuttle_rvc_pipeline,profile_.shuttle_counter_pipeline,profile_.empirical,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,profile_.empirical_store_front).has_value();
}

bool iris_timing_adapter::pure_begin(unsigned hart, reg_t pc, const insn_fetch_t& fetch) {
  if (!pure_candidate(hart,fetch) || clock_.now()%profile_.harts[hart].divider ||
      !(frontend_enabled(hart)||(hart==2&&rocket_frontend_enabled())?cores_[hart]->iris_pipeline_context_safe():cores_[hart]->iris_pipeline_can_prefetch(pc,hart==2 || profile_.shuttle_rvc_pipeline,hart==2))) return false;
  auto& p = pure_.at(hart);
  if (p.engaged || !p.packets.empty()) throw std::logic_error("IRIS_PIPELINE_ENTERED_WITH_INFLIGHT_STATE");
  if (p.next_commit != p.instructions.size()) throw std::logic_error("IRIS_PIPELINE_RETIREMENT_FRONTIER_INVALID");
  p.engaged = true; p.boundary = false; p.frontier = pc; p.deferred_fetch = {};if(profile_.empirical)p.last_attempt.reset();
  p.last_writer.fill(std::nullopt);
  if(profile_.private_forwarded_values) {
    iris::frontend::ForwardedValues::Snapshot initial;
    for(unsigned reg=0;reg<32;++reg)initial[reg]=private_xpr_value(cores_[hart],reg);
    if(!p.values||!p.values->pending_external_count())p.values.emplace(initial,hart==2?(profile_.rocket_scalar_memory?32:3):8);
  }
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
  iris::empirical::IntegerHazardFold hazards;
  // Match RTL ll,WB,COM,MEM,EX override order. A held CSR remains in EX
  // beyond its original age; readiness follows its actual COM node.
  for (unsigned stage=4;stage>=1;--stage) {
    for (size_t index=p.first_live;index<p.instructions.size();++index) {
      const auto& instruction=p.instructions[index];
      if (instruction.released || instruction.exception || now<=instruction.rrd) continue;
      unsigned current=now<=instruction.ex_release ? 1 : now==instruction.com_cycle-divider ? 2 : now==instruction.com_cycle ? 3 : now==instruction.com_cycle+divider ? 4 : 0;
      if (current!=stage) continue;
      cpu_event(hart,"model_stage",instruction.pc,instruction.uop.raw,index,"\"stage\":"+std::to_string(stage)+",\"result_completed\":"+((instruction.result&&clock_.nodes().at(*instruction.result).completed)?"true":"false"));
      // Saved Shuttle DCache exposes a warm hit in S2/COM (EX+2), not MEM.
      // Keep the private transport latch and COM-owned architectural load intact;
      // only suppress its pre-COM bypass. Late/coherence-fallback responses retain
      // their existing separate return path. Rocket uses its own MEM word bypass.
      const bool warm_load_before_COM=profile_.empirical_shuttle_load_com_forward &&
          hart<2 && instruction.empirical_load_warm_hit && now<instruction.com_cycle;
      const bool ready = instruction.result && clock_.nodes().at(*instruction.result).completed && !warm_load_before_COM && !(frontend_enabled(hart) && instruction.sfb_shadow && current==1);
      hazards.observe(instruction.uop.has(iris::shuttle::WXD),instruction.uop.rd,ready);
    }
  }
  signals.integer_hazard=hazards.values();
  for (size_t index=p.first_live;index<p.instructions.size();++index) {
    const auto& instruction=p.instructions[index];
    if (instruction.released || now<instruction.rrd) continue;
    if (now>instruction.rrd && now<=instruction.ex_release) signals.ex_busy=Signal::yes;
    if (now==instruction.com_cycle-divider) signals.mem_busy=Signal::yes;
    if (now==instruction.com_cycle) signals.com_busy=Signal::yes;
    // Source ex_fcsr_data_hazard: a CSR in EX blocks all RRD while
    // older MEM/COM registers remain valid, including their retire edge.
    if ((instruction.counter || instruction.scalar_fadd) && now>instruction.rrd && now<instruction.ex_release)
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
  if(frontend_enabled(hart) && (!frontend_[hart].prepared || frontend_[hart].inputs.redirect_flush))return;
  p.last_attempt=now;
  cpu_event(hart,"rrd_attempt",p.frontier,0,SIZE_MAX,"\"packets\":"+std::to_string(p.packets.size()));
  if (pure_signals(hart).ex_stall==Signal::yes){cpu_event(hart,"rrd_reject",p.frontier,0,SIZE_MAX,"\"reason\":\"ex_stall\"");return;}
  const bool exception_inflight=!p.instructions.empty() && p.instructions.back().exception && !p.instructions.back().released;
  if (exception_inflight) return;
  if (!cores_[hart]->iris_pipeline_context_safe())
    throw std::runtime_error("IRIS_PIPELINE_CONTEXT_CHANGED_DURING_FLIGHT hart="+std::to_string(hart));
  if(scalar_fadd_defer_irq(hart))return;
  if(profile_.empirical_async&&empirical_async_[hart]&&cores_[hart]->iris_pipeline_interrupt_exception())return;
  if (auto exception=cores_[hart]->iris_pipeline_interrupt_exception()) {
    if(frontend_enabled(hart)) {
      if(!frontend_[hart].outputs.queue[0].valid)return;
      p.frontier=frontend_[hart].outputs.queue[0].pc;frontend_consume(hart,1);
    }
    pure_exception(hart,exception); return;
  }
  if (p.boundary) {
    cpu_event(hart,"boundary_wait",p.frontier,0,SIZE_MAX,"\"packets\":"+std::to_string(p.packets.size())+",\"async_owner\":"+(empirical_async_[hart]?"true":"false"));
    if (p.packets.empty()) { p.engaged=false; p.last_writer.fill(std::nullopt); }
    return;
  }
  if (p.deferred_fetch) {if(profile_.empirical_async&&empirical_async_[hart])return;pure_exception(hart,p.deferred_fetch); p.deferred_fetch={}; return; }
  std::vector<std::pair<reg_t,insn_fetch_t>> fetched;
  std::vector<iris::shuttle::Uop> uops;
  reg_t next_pc=p.frontier;
  for (unsigned lane=0;lane<2;++lane) {
    if(frontend_enabled(hart)) {
      const auto& q=frontend_[hart].outputs.queue[lane];
      if(!q.valid)break;
      const insn_t raw(q.compressed?uint16_t(q.raw):q.raw);
      insn_fetch_t fetch{cores_[hart]->decode_for_model(raw),raw};
      auto u=frontend_decode(hart,fetch,lane);
      if(u&&empirical_load_wait_base(hart,*u,q.pc)){if(fetched.empty())return;break;}
      if(u&&empirical_store_wait_base(hart,*u)){if(fetched.empty())return;break;}
      if(!u||!frontend_uop_candidate(hart,*u)){p.boundary=true;break;}
      if(profile_.empirical_async&&u->has(iris::shuttle::VECTOR)&&!empirical_async_can_dispatch(hart,&fetch)){if(fetched.empty())return;break;}
      fetched.emplace_back(q.pc,fetch);uops.push_back(*u);continue;
    }
    const auto pc=next_pc;
    cpu_event(hart,"fetch_attempt",pc,0,SIZE_MAX,"\"lane\":"+std::to_string(lane));
    if (!cores_[hart]->iris_pipeline_can_prefetch(pc,profile_.shuttle_rvc_pipeline)) {
      cpu_event(hart,"candidate_boundary",pc,0,SIZE_MAX,"\"reason\":\"prefetch_scope\"");p.boundary=true; break;
    }
    insn_fetch_t fetch;
    try { fetch=(first && lane==0) ? *first : cores_[hart]->get_mmu()->load_insn(pc); }
    catch (trap_t&) {
      if (lane==0) { pure_exception(hart,std::current_exception()); return; }
      p.deferred_fetch=std::current_exception(); break;
    }
    if(profile_.empirical&&!empirical_fetch_ready(hart,pc,fetch.insn.length(),&fetch)){cpu_event(hart,"rrd_reject",pc,uint32_t(fetch.insn.bits()),SIZE_MAX,"\"reason\":\"icache_fetch_wait\"");if(fetched.empty())return;break;}
    if(profile_.empirical_store_front){auto store=pure_decode(fetch,true,true,true,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,true);if(store&&empirical_store_wait_base(hart,*store)){if(fetched.empty())return;break;}}
    if(profile_.empirical_pending_base_retry){auto load=pure_decode_for_frontend(fetch);if(load&&empirical_load_wait_base(hart,*load,pc)){if(fetched.empty())return;break;}}
    if (!pure_candidate(hart,fetch)) {cpu_event(hart,"candidate_boundary",pc,uint32_t(fetch.insn.bits()),SIZE_MAX,"\"reason\":\"pure_candidate_false\"");p.boundary=true; break; }
    if(profile_.empirical_async&&!empirical_async_can_dispatch(hart,&fetch)&&empirical_unit_decode(uint32_t(fetch.insn.bits()),profile_.empirical_async_fadd)){cpu_event(hart,"rrd_reject",pc,uint32_t(fetch.insn.bits()),SIZE_MAX,"\"reason\":\"whole_async_owner\"");if(fetched.empty())return;break;}
    fetched.emplace_back(pc,fetch);
    uops.push_back(*pure_decode(fetch,profile_.shuttle_rvc_pipeline,profile_.shuttle_counter_pipeline,profile_.empirical,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,profile_.empirical_store_front));
    next_pc+=fetch.insn.length();
    if(profile_.empirical&&uops.back().cfi()){next_pc=empirical_predict(hart,pc,uops.back(),fetch.insn.length());if(lane==0&&next_pc!=pc+fetch.insn.length())break;}
  }
  if (!fetched.empty()) {
    auto plan=iris::shuttle::select_rrd(uops,pure_signals(hart));
    if(profile_.empirical_load_front&&plan.ready_prefix>1&&plan.lanes[1].integer_result_stage==ResultStage::wb){cpu_event(hart,"lane1_WB_split",fetched[1].first,uint32_t(fetched[1].second.insn.bits()),SIZE_MAX,"\"planned_ready_prefix\":2");plan.ready_prefix=1;}
    if(cpu_trace_)for(unsigned i=0;i<plan.lanes.size();++i){std::ostringstream fields;fields<<"\"lane\":"<<i<<",\"accepted_prefix\":"<<plan.ready_prefix<<",\"reasons\":[";bool first=true;for(const auto&reason:plan.lanes[i].reasons){if(!first)fields<<",";first=false;fields<<std::quoted(reason);}fields<<"]";cpu_event(hart,"rrd_plan",fetched[i].first,uint32_t(fetched[i].second.insn.bits()),SIZE_MAX,fields.str());}
    for (unsigned i=0;i<plan.ready_prefix;++i)
      if (!source_counter_read(uops[i]) && !((frontend_enabled(hart)||profile_.empirical) && uops[i].cfi()) && !uops[i].has(iris::shuttle::VECTOR) && !scalar_fadd_candidate(hart,uops[i]) && !uops[i].has(iris::shuttle::MEM) && plan.lanes[i].integer_result_stage!=ResultStage::ex && plan.lanes[i].integer_result_stage!=ResultStage::mem)
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
  Cycle packet_ex=future_cycle(now,divider,1);
  if(profile_.empirical_scalar_fadd)for(unsigned lane=0;lane<fetched.size();++lane){const auto&f=fetched[lane];auto u=frontend_enabled(hart)?frontend_decode(hart,f.second,lane):pure_decode_for_frontend(f.second);if(u)packet_ex=std::max(packet_ex,scalar_fadd_release(hart,*u,packet_ex));}
  for (unsigned lane=0;lane<fetched.size();++lane) {
    auto insn=fetched[lane].second.insn;
    PureInstruction instruction;
    instruction.pc=fetched[lane].first;instruction.fetch=fetched[lane].second;
    instruction.uop=frontend_enabled(hart)?*frontend_decode(hart,fetched[lane].second,lane):*pure_decode(fetched[lane].second,profile_.shuttle_rvc_pipeline,profile_.shuttle_counter_pipeline,profile_.empirical,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,profile_.empirical_store_front);
    if(frontend_enabled(hart)){instruction.frontend=frontend_[hart].outputs.queue[lane];instruction.sfb_shadow=plan.lanes[lane].sfb_shadow;}
    instruction.counter=source_counter_read(instruction.uop);instruction.empirical_compute=profile_.empirical_async&&instruction.uop.has(iris::shuttle::VECTOR);instruction.empirical_load=profile_.empirical_load_front&&instruction.uop.has(iris::shuttle::MEM)&&(instruction.uop.expanded&127)==3;instruction.empirical_store=profile_.empirical_store_front&&instruction.uop.has(iris::shuttle::MEM)&&(instruction.uop.expanded&127)==0x23;
    instruction.result_stage=instruction.empirical_load?ResultStage::mem:instruction.empirical_store?ResultStage::ex:plan.lanes[lane].integer_result_stage;
    instruction.packet=packet;instruction.lane=lane;instruction.rrd=now;
    instruction.ex_release=packet_ex;
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
    auto& stored=p.instructions.at(id);cpu_event(hart,"rrd_accept",stored.pc,uint32_t(stored.fetch.insn.bits()),id,"\"lane\":"+std::to_string(lane)+",\"EX_planned\":"+std::to_string(stored.ex_release)+",\"MEM_planned\":"+std::to_string(stored.com_cycle-divider)+",\"COM_planned\":"+std::to_string(stored.com_cycle));if(stored.empirical_load){++empirical_load_metrics_[hart].accepted;const auto base=p.values->peek(stored.uop.rs1);if(!base)throw std::logic_error("empirical load accepted unknown base");insn_t raw(stored.uop.expanded);stored.memory_address=*base+raw.i_imm();stored.memory_size=(stored.uop.expanded>>12)&3;}
    if(stored.empirical_store){++store_metrics_[hart].accepted;const auto base=p.values->peek(stored.uop.rs1);if(!base)throw std::logic_error("store front accepted unknown base");const auto x=stored.uop.expanded;stored.memory_address=*base+iris::frontend::PureAluValue::sext(((x>>25)<<5)|((x>>7)&31),12);stored.memory_size=(x>>12)&3;}
    if(profile_.empirical&&!frontend_enabled(hart)&&stored.uop.cfi())stored.empirical_prediction=empirical_predict(hart,stored.pc,stored.uop,stored.fetch.insn.length());
    if(p.values) {
      if((frontend_enabled(hart)||profile_.empirical) && stored.uop.cfi()) {
        stored.branch_operands=p.values->latch(stored.uop.has(iris::shuttle::RXS1)?stored.uop.rs1:0,stored.uop.has(iris::shuttle::RXS2)?stored.uop.rs2:0);
        p.values->issue_external(id,stored.uop.has(iris::shuttle::WXD)?stored.uop.rd:0);
      } else if(stored.empirical_load)p.values->issue_external(id,stored.uop.rd);
      else if(stored.empirical_store||stored.empirical_compute||scalar_fadd_candidate(hart,stored.uop))p.values->issue_external(id,0);
      else if(stored.counter)p.values->issue_external(id,stored.uop.rd);
      else p.values->issue(id,stored.uop.expanded,stored.pc);
    }
    const bool mem=stored.result_stage==ResultStage::mem;
    if (stored.counter) {
      iris::Op ex{hart,stored.uop.instruction_name+".EX-counter-hold",prefix+"CSR_EX",stored.ex_release-now,divider};
      ex.retires=false;ex.pc=stored.pc;ex.issue_period=divider;ex.cancellable=frontend_enabled(hart)||profile_.empirical;
      stored.csr_ex=clock_.issue(std::move(ex));
    } else {
      iris::Op result{hart,stored.uop.instruction_name+".result-ready",prefix+(stored.empirical_load?"LOAD_RESPONSE":mem?"MEM_ALU":"EX"),stored.ex_release-now,divider};
      result.retires=false;result.pc=stored.pc;result.issue_period=divider;result.cancellable=frontend_enabled(hart)||profile_.empirical;
      if (mem) result.earliest=future_cycle(now,divider,1);
      for (auto producer:stored.raw_producers) result.deps.push_back(*p.instructions.at(producer).result);
      if(p.values)result.on_complete=[this,hart,id]{
        auto& p=pure_.at(hart);auto& row=p.instructions.at(id);
        if(row.squashed)return;
        cpu_event(hart,"result_callback",row.pc,uint32_t(row.fetch.insn.bits()),id,"\"load\":"+std::string(row.empirical_load?"true":"false"));
        if(row.empirical_load){empirical_load_response(hart,id);return;}
        if((frontend_enabled(hart)||profile_.empirical) && row.uop.cfi()) {
          const auto values=p.values->read(*row.branch_operands);
          if(!values[0] || !values[1])throw std::runtime_error("IRIS_FRONTEND_UNDEFINED_BRANCH_OPERANDS_UNMODELED");
          if(row.uop.has(iris::shuttle::BRANCH))row.branch_taken=iris::frontend::ShuttleBranch::compare(row.uop.expanded,*values[0],*values[1]);
          if(row.uop.has(iris::shuttle::JALR))row.branch_wdata=*values[0]+iris::frontend::PureAluValue::sext(row.uop.expanded>>20,12);
          else row.branch_wdata=row.pc+row.fetch.insn.length();
          row.branch_operands.reset();
          if(!row.uop.has(iris::shuttle::JALR)) {
            row.private_value=row.uop.has(iris::shuttle::WXD)?row.branch_wdata:0;
            p.values->complete_external(id,row.private_value);row.private_value_ready=true;
          }
        } else if(row.empirical_store){row.private_value=0;p.values->complete_external(id,0);row.private_value_ready=true;}
    else if(row.empirical_compute){row.private_value=0;p.values->complete_external(id,0);row.private_value_ready=true;}
        else if(row.scalar_fadd){scalar_fadd_ex(hart,id);row.private_value=0;p.values->complete_external(id,0);row.private_value_ready=true;}
    else {row.private_value=p.values->complete(id);row.private_value_ready=true;}
      };
      stored.result=clock_.issue(std::move(result));
      if((frontend_enabled(hart)||profile_.empirical) && stored.uop.has(iris::shuttle::JALR))stored.csr_ex=stored.result;
    }
    iris::Op commit{hart,stored.uop.instruction_name+".COM",prefix+"COM",divider,divider};
    commit.retires=false;commit.pc=stored.pc;commit.issue_period=divider;commit.cancellable=frontend_enabled(hart)||profile_.empirical;
    commit.earliest=stored.com_cycle-divider;commit.deps={stored.counter?*stored.csr_ex:*stored.result};
    commit.on_complete=[this,hart,id]{pure_commit(hart,id);};
    stored.com=clock_.issue(std::move(commit));
    if (stored.counter || ((frontend_enabled(hart)||profile_.empirical) && stored.uop.has(iris::shuttle::JALR)))stored.result=stored.com;
    if((frontend_enabled(hart)||profile_.empirical) && (stored.uop.cfi() || stored.uop.predicted_next_pc_valid==Signal::yes)) {
      iris::Op branch{hart,stored.uop.instruction_name+".MEM-control",prefix+"BRANCH_MEM",divider,divider};
      branch.retires=false;branch.pc=stored.pc;branch.issue_period=divider;branch.cancellable=true;
      branch.earliest=future_cycle(now,divider,1);
      branch.on_complete=[this,hart,id]{if(frontend_enabled(hart))frontend_branch_resolve(hart,id);else empirical_branch_resolve(hart,id);};stored.branch_mem=clock_.issue(std::move(branch));
    }
    iris::Op wb{hart,stored.uop.instruction_name+".WB",prefix+"WB",divider,divider};
    wb.retires=false;wb.pc=stored.pc;wb.issue_period=divider;wb.deps={*stored.com};wb.cancellable=frontend_enabled(hart)||profile_.empirical;
    wb.on_complete=[this,hart,id]{
      auto& p=pure_.at(hart);auto& row=p.instructions.at(id);
      if (p.packets.empty() || p.packets.front().id!=row.packet || !p.packets.front().remaining)
        throw std::logic_error("IRIS_PIPELINE_WB_ORDER");
      row.released=true;
      if (!--p.packets.front().remaining) p.packets.pop_front();
      while(p.first_live<p.instructions.size() && p.instructions[p.first_live].released) ++p.first_live;
    };
    stored.wb=clock_.issue(std::move(wb));previous_[hart]=stored.wb;
    if(scalar_fadd_candidate(hart,stored.uop))scalar_fadd_reserve(hart,id);
  if(stored.empirical_compute)empirical_async_begin(hart,id);
    if(profile_.empirical)empirical_fetch_consume(hart,stored.pc,stored.fetch.insn.length());
    if (stored.uop.has(iris::shuttle::WXD) && stored.uop.rd) p.last_writer[stored.uop.rd]=id;
  }
  if(frontend_enabled(hart)) {
    const auto& last=frontend_[hart].outputs.queue[fetched.size()-1];
    p.frontier=last.prediction_valid?last.predicted_pc:last.pc+(last.compressed?2:4);
    frontend_consume(hart,fetched.size());
  } else for(unsigned i=0;i<fetched.size();++i){auto instruction=fetched[i].second.insn;const auto&row=p.instructions.at(p.instructions.size()-fetched.size()+i);p.frontier=profile_.empirical&&row.uop.cfi()?row.empirical_prediction:fetched[i].first+instruction.length();}
}

void iris_timing_adapter::pure_exception(unsigned hart,std::exception_ptr exception) {
  if(profile_.empirical_async&&empirical_async_[hart]){pure_[hart].deferred_fetch=exception;return;}
  if(hart==2&&profile_.rocket_scalar_memory&&pure_[2].values&&pure_[2].values->pending_external_count())throw std::runtime_error("IRIS_ROCKET_SOURCE_PENDING_LOAD_PRECISE_INTERRUPT_UNMODELED");
  auto& p=pure_.at(hart);const auto divider=profile_.harts[hart].divider;
  PureInstruction row;row.pc=p.frontier;row.fetch={nullptr,insn_t(0)};
  row.packet=p.next_packet++;row.rrd=clock_.now();row.exception=exception;
  if(frontend_enabled(hart)){
    const auto&f=frontend_[hart];const auto&q=f.outputs.queue[0];
    if(!f.prepared||!q.valid||q.pc!=row.pc)throw std::logic_error("IRIS_SOURCE_TRAP_WITHOUT_ACCEPTED_FRONTEND_PARCEL");
    row.frontend=q;
  }

  row.ex_release=future_cycle(row.rrd,divider,1);row.com_cycle=future_cycle(row.rrd,divider,3);
  const auto id=p.instructions.size();p.instructions.push_back(row);
  p.packets.push_back({row.packet,1});p.peak_packets=std::max(p.peak_packets,p.packets.size());
  p.boundary=true;
  iris::Op op{hart,hart==2?"latched-ID-exception.WB":"latched-RRD-exception.COM",hart==2?"rocket2.WB":"shuttle"+std::to_string(hart)+".COM",divider,divider};
  op.pc=row.pc;op.retires=false;op.issue_period=divider;op.earliest=future_cycle(clock_.now(),divider,2);op.cancellable=frontend_enabled(hart)||(hart==2&&rocket_frontend_enabled())||profile_.empirical;
  op.on_complete=[this,hart,id]{pure_commit(hart,id);};
  p.instructions.at(id).com=clock_.issue(std::move(op));previous_[hart]=p.instructions.at(id).com;
}

void iris_timing_adapter::pure_commit(unsigned hart,size_t id) {
  if(hart==2&&profile_.rocket_scalar_memory&&!rocket_frontend_.prepared){rocket_frontend_.pending_wb.push_back(id);return;}
  auto& p=pure_.at(hart);auto& row=p.instructions.at(id);
  if(hart==2&&profile_.rocket_scalar_memory&&row.exception&&p.values&&p.values->pending_external_count())throw std::runtime_error("IRIS_ROCKET_SOURCE_PENDING_LOAD_PRECISE_INTERRUPT_UNMODELED");
  if (id!=p.next_commit || cores_[hart]->get_state()->pc!=row.pc)
    throw std::runtime_error("IRIS_PIPELINE_PRECISE_COM_PC_MISMATCH hart="+std::to_string(hart));
  if (!cores_[hart]->iris_pipeline_context_safe())
    throw std::runtime_error("IRIS_PIPELINE_DEBUG_OR_PRIVILEGE_CHANGED_BEFORE_COM");
  if(row.empirical_store&&!empirical_store_before_commit(hart,id))return;
  cpu_event(hart,"COM_enter",row.pc,uint32_t(row.fetch.insn.bits()),id);
  completing_=hart;completing_pure_=id;completing_node_=row.com;completion_reads_.clear();const auto before=retired_[hart];
  if(row.scalar_fadd)scalar_fadd_before(hart,id);
  if(row.empirical_compute)empirical_async_before(hart,id);
  if(row.empirical_load)empirical_load_before_commit(hart,id);
  try {
    cores_[hart]->step(1);
    if (cores_[hart]->iris_step_timing_waited())
      throw std::runtime_error("IRIS_PIPELINE_COMPLETION_RETRY_UNMODELED hart=" + std::to_string(hart));
  } catch (...) {if(profile_.empirical_fadd_eg)if(auto a=fadd_eg_find(hart,id))fadd_eg_after(hart,a,false);if(row.empirical_load)empirical_load_after_commit();completion_reads_.clear();completing_node_.reset();completing_pure_.reset();completing_.reset();throw;}
  if(row.empirical_load)empirical_load_after_commit();
  if(row.scalar_fadd)scalar_fadd_after(hart,id,retired_[hart]==before+1);
  if(row.empirical_store)empirical_store_after_commit(hart,id,retired_[hart]==before+1);
  finish_counter_reads(hart,before);
  if(row.empirical_compute)empirical_async_after(hart,id,retired_[hart]==before+1);
  cpu_event(hart,"COM_exit",row.pc,uint32_t(row.fetch.insn.bits()),id,"\"retired_delta\":"+std::to_string(retired_[hart]-before));
  completing_pure_.reset();completing_.reset();++p.next_commit;++completions_;
  while(p.next_commit<p.instructions.size() && p.instructions[p.next_commit].squashed)++p.next_commit;
  if (row.exception) {
    if (retired_[hart]!=before || p.packets.empty() || p.packets.front().id!=row.packet || p.packets.front().remaining!=1)
      throw std::logic_error("IRIS_PIPELINE_EXCEPTION_ORDER_OR_RETIREMENT");
    row.released=true;p.packets.pop_front();p.engaged=false;p.last_writer.fill(std::nullopt);
    while(p.first_live<p.instructions.size() && p.instructions[p.first_live].released) ++p.first_live;
    queue_trap(hart,row.frontend?std::optional<unsigned>(row.frontend->ras_head):std::nullopt);
  } else {
    if (retired_[hart]!=before+1)
      throw std::runtime_error("IRIS_PIPELINE_UNEXPECTED_PURE_TRAP: timing subset refused");
    if (clock_.now()!=row.com_cycle)
      throw std::runtime_error("IRIS_PIPELINE_RETIREMENT_EDGE_CHANGED");
    if(p.values) {
      const auto observed=private_xpr_value(cores_[hart],row.uop.rd);
      if(row.counter) {p.values->complete_external(id,observed);row.private_value=observed;row.private_value_ready=true;}
      else if((frontend_enabled(hart)||profile_.empirical) && row.uop.has(iris::shuttle::JALR)&&!row.private_value_ready) {
        row.private_value=row.pc+row.fetch.insn.length();row.private_value_ready=true;p.values->complete_external(id,row.private_value);
      }
      if(row.source_memory&&row.memory_pending)p.values->retire_pending_external(id);else p.values->commit(id,observed);
    }
    row.retired=true;
    if(hart==2&&rocket_frontend_enabled())rocket_frontend_.last_architectural_wb=clock_.now();
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
     <<",\"domain\":"<<std::quoted(profile_.saved_shuttle_frontend ? "experimental-source-Shuttle-frontend-RV64IC-ALU-counter-CFI" : profile_.shuttle_counter_pipeline ? "experimental-RV64IC-counter-read-sequential-frontend" : profile_.shuttle_rvc_pipeline ? "experimental-base-RV64IC-pure-sequential-frontend" : "experimental-base-RV64I-pure-32bit-sequential-frontend")
     <<",\"compressed_ALU_enabled\":"<<(profile_.shuttle_rvc_pipeline?"true":"false")
     <<",\"counter_reads_enabled\":"<<(profile_.shuttle_counter_pipeline?"true":"false")<<",\"calibrated\":false,\"peak_packets\":[";
  for(size_t h=0;h<pure_.size();++h){if(h)out<<',';out<<(h<2?pure_[h].peak_packets:0);}
  out<<"],\"instructions\":[";bool first=true;
  for(size_t h=0;h<std::min(size_t(2),pure_.size());++h) for(size_t i=0;i<pure_[h].instructions.size();++i){
    const auto& row=pure_[h].instructions[i];auto insn=row.fetch.insn;if(!first)out<<',';first=false;
    out<<"{\"hart\":"<<h<<",\"sequence\":"<<i<<",\"packet\":"<<row.packet<<",\"lane\":"<<row.lane
       <<",\"pc\":"<<row.pc<<",\"raw\":"<<(row.uop.compressed?uint16_t(insn.bits()):uint32_t(insn.bits()))
       <<",\"length\":"<<(row.exception||row.rocket_replay?0:insn.length())<<",\"expanded\":"<<row.uop.expanded<<",\"RRD\":"<<row.rrd
       <<",\"result_stage\":"<<std::quoted(row.counter || (frontend_enabled(h) && row.uop.has(iris::shuttle::JALR))?"COM":iris::shuttle::stage_name(row.result_stage))
       <<",\"counter_read\":"<<(row.counter?"true":"false")<<",\"EX_release\":"<<row.ex_release
       <<",\"CSR_EX_node\":"<<(row.csr_ex?std::to_string(*row.csr_ex):"null")
       <<",\"result_node\":"<<(row.result?std::to_string(*row.result):"null")
       <<",\"COM_node\":"<<(row.com?std::to_string(*row.com):"null")<<",\"WB_node\":"<<(row.wb?std::to_string(*row.wb):"null")
       <<",\"retired\":"<<(row.retired?"true":"false")<<",\"released\":"<<(row.released?"true":"false")
       <<",\"latched_exception\":"<<(row.exception?"true":"false");
    if(frontend_enabled(h)) {
      out<<",\"squashed\":"<<(row.squashed?"true":"false")<<",\"sfb_shadow\":"<<(row.sfb_shadow?"true":"false")<<",\"MEM_control_node\":"<<(row.branch_mem?std::to_string(*row.branch_mem):"null")
         <<",\"MEM_control_resolved\":"<<(row.branch_resolved?"true":"false")<<",\"MEM_mispredict\":"<<(row.branch_mispredict?"true":"false")<<",\"MEM_redirect\":"<<(row.branch_redirect?"true":"false")<<",\"MEM_sfb_pair\":"<<(row.branch_sfb_pair?"true":"false");
      if(row.frontend)out<<",\"source_prediction_valid\":"<<(row.frontend->prediction_valid?"true":"false")<<",\"source_predicted_pc\":"<<row.frontend->predicted_pc<<",\"source_btb_valid\":"<<(row.frontend->btb_valid?"true":"false")<<",\"source_ras_head\":"<<row.frontend->ras_head;
    }
    if(profile_.private_forwarded_values)out<<",\"private_value_ready\":"<<(row.private_value_ready?"true":"false")
       <<",\"private_value\":"<<(row.private_value?std::to_string(*row.private_value):"null");
    out<<",\"raw_producers\":[";
    for(size_t j=0;j<row.raw_producers.size();++j){if(j)out<<',';out<<row.raw_producers[j];}out<<"]}";
  }
  out<<"]}";
}

void iris_timing_adapter::rocket_dispatch(unsigned hart,const insn_fetch_t* first) {
  if (hart!=2 || !profile_.rocket_pure_pipeline) throw std::logic_error("IRIS_ROCKET_PIPELINE_HART_CONFIG");
  auto& p=pure_.at(hart);const auto now=clock_.now(),divider=profile_.harts[hart].divider;
  if (!p.engaged || now%divider || (p.last_attempt && *p.last_attempt==now) || p.packets.size()>=3) return;
  if(rocket_frontend_enabled() && (!rocket_frontend_.prepared || rocket_frontend_.inputs.redirect_valid))return;
  p.last_attempt=now;
  if (!p.instructions.empty() && p.instructions.back().exception && !p.instructions.back().released) return;
  if (!cores_[hart]->iris_pipeline_context_safe())throw std::runtime_error("IRIS_ROCKET_PIPELINE_CONTEXT_CHANGED_DURING_FLIGHT");
  if (p.boundary) {
    cpu_event(hart,"boundary_wait",p.frontier,0,SIZE_MAX,"\"packets\":"+std::to_string(p.packets.size())+",\"async_owner\":"+(empirical_async_[hart]?"true":"false"));if (p.packets.empty()) {if(profile_.rocket_scalar_memory&&p.values&&p.values->pending_external_count())throw std::runtime_error("IRIS_ROCKET_PENDING_LOAD_CONSERVATIVE_BOUNDARY_UNMODELED");p.engaged=false;p.last_writer.fill(std::nullopt);}return;}
  auto pc=p.frontier;insn_fetch_t fetch;std::optional<iris::shuttle::Uop> uop;
  if(rocket_frontend_enabled()) {
    auto& f=rocket_frontend_;if(!f.outputs.id.valid)return;
    if(f.outputs.id.replay){rocket_frontend_replay_accept();return;}
    pc=f.outputs.id.pc;
    if(auto exception=cores_[hart]->iris_pipeline_interrupt_exception()){p.frontier=pc;pure_exception(hart,exception);rocket_frontend_consume();return;}
    if(f.outputs.id.first_access_fault||f.outputs.id.second_access_fault){p.boundary=true;return;}
    const insn_t raw(f.outputs.id.compressed?uint16_t(f.outputs.id.raw):f.outputs.id.raw);fetch={cores_[hart]->decode_for_model(raw),raw};
    uop=rocket_frontend_decode(fetch);
  } else {
    if (auto exception=cores_[hart]->iris_pipeline_interrupt_exception()) {pure_exception(hart,exception);return;}
    if (!cores_[hart]->iris_pipeline_can_prefetch(pc,true,true)) {p.boundary=true;return;}
    try {fetch=first?*first:cores_[hart]->get_mmu()->load_insn(pc);}catch (trap_t&) {pure_exception(hart,std::current_exception());return;}
    uop=pure_decode(fetch,true,true,profile_.empirical,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,profile_.empirical_store_front);
  }
  if(p.deferred_fetch){if(profile_.empirical_async&&empirical_async_[hart])return;pure_exception(hart,p.deferred_fetch);p.deferred_fetch={};return;}
  if(profile_.rocket_scalar_memory&&uop){
    const bool supported=base_integer(*uop)||scalar_fadd_candidate(hart,*uop)||source_counter_read(*uop)||uop->cfi()||rocket_memory_decode(*uop);
    for(unsigned rd=1;rd<32;++rd){const bool touches=(uop->has(iris::shuttle::RXS1)&&uop->rs1==rd)||(uop->has(iris::shuttle::RXS2)&&uop->rs2==rd)||(uop->has(iris::shuttle::WXD)&&uop->rd==rd);
      if(!touches)continue;if(rocket_frontend_.pending_loads[rd])return;
      if(!supported&&p.last_writer[rd]){const auto&older=p.instructions.at(*p.last_writer[rd]);if(older.source_memory&&!older.private_value_ready)return;}
    }
  }
  if(uop&&empirical_store_wait_base(hart,*uop))return;
  if(profile_.empirical&&!empirical_fetch_ready(hart,pc,fetch.insn.length(),&fetch))return;
  if (!uop || !(base_integer(*uop)||scalar_fadd_candidate(hart,*uop)||empirical_store_candidate(hart,*uop)||source_counter_read(*uop)||(profile_.empirical_load_front&&uop->has(iris::shuttle::MEM)&&empirical_load_candidate(hart,*uop))||(profile_.empirical_async&&uop->has(iris::shuttle::VECTOR))||((rocket_frontend_enabled()||profile_.empirical)&&uop->cfi())||rocket_memory_decode(*uop))) {p.boundary=true;return;}
  if(profile_.rocket_scalar_memory){
    if(uop->has(iris::shuttle::MEM)&&rocket_frontend_.cache_blocked&&!rocket_frontend_.cache_grant)return;
    for(unsigned rd=1;rd<32;++rd)if(rocket_frontend_.pending_loads[rd]&&((uop->has(iris::shuttle::RXS1)&&uop->rs1==rd)||(uop->has(iris::shuttle::RXS2)&&uop->rs2==rd)||(uop->has(iris::shuttle::WXD)&&uop->rd==rd)))return;
  }
  // RocketCore1041–1053: CSR RAW/WAW interlocks in EX+MEM, JALR in
  // EX only. JALR's corrected link bypass is available from MEM->WB.
  for (size_t index=p.first_live;index<p.instructions.size();++index) {
    const auto& older=p.instructions[index];
    if (older.released || older.squashed || older.exception || !older.uop.rd) continue;
    const bool blocked=(older.empirical_load&&(older.memory_size<2?now<older.com_cycle:now<older.rrd+2*divider)) || older.counter&&now<older.com_cycle || (older.source_memory&&now<older.rrd+2*divider) || (older.source_memory&&older.memory_size<2&&now<older.com_cycle) || ((rocket_frontend_enabled()||profile_.empirical)&&older.uop.has(iris::shuttle::JALR)&&now<older.rrd+2*divider);
    if(!blocked)continue;const auto rd=older.uop.rd;
    if ((uop->has(iris::shuttle::RXS1) && uop->rs1==rd) || (uop->has(iris::shuttle::RXS2) && uop->rs2==rd) || (uop->has(iris::shuttle::WXD) && uop->rd==rd)) return;
  }
  if(profile_.empirical_async&&!empirical_async_can_dispatch(hart,&fetch)&&uop->has(iris::shuttle::VECTOR))return;
  if(scalar_fadd_candidate(hart,*uop)&&scalar_fadd_release(hart,*uop,now)>now)return;
  rocket_accept(hart,pc,fetch);
}

void iris_timing_adapter::rocket_accept(unsigned hart,reg_t pc,const insn_fetch_t& fetch) {
  auto& p=pure_.at(hart);const auto now=clock_.now(),divider=profile_.harts[hart].divider;
  auto decoded=rocket_frontend_enabled()?rocket_frontend_decode(fetch):pure_decode(fetch,true,true,profile_.empirical,profile_.empirical_async,profile_.empirical_load_front,profile_.empirical_async_fadd,profile_.empirical_scalar_fadd,profile_.empirical_store_front);
  if (hart!=2 || !decoded || p.packets.size()>=3) throw std::logic_error("IRIS_ROCKET_PIPELINE_ACCEPT_DOMAIN");
  PureInstruction row;row.pc=pc;row.fetch=fetch;row.uop=*decoded;row.counter=source_counter_read(row.uop);row.empirical_compute=profile_.empirical_async&&row.uop.has(iris::shuttle::VECTOR);row.empirical_load=profile_.empirical_load_front&&row.uop.has(iris::shuttle::MEM)&&(row.uop.expanded&127)==3;row.empirical_store=profile_.empirical_store_front&&row.uop.has(iris::shuttle::MEM)&&(row.uop.expanded&127)==0x23;
  row.source_memory=rocket_memory_decode(row.uop);if(row.empirical_load){++empirical_load_metrics_[hart].accepted;const auto base=p.values->peek(row.uop.rs1);if(!base)throw std::logic_error("empirical Rocket load base");insn_t raw(row.uop.expanded);row.memory_address=*base+raw.i_imm();row.memory_size=(row.uop.expanded>>12)&3;}
  if(row.empirical_store){++store_metrics_[hart].accepted;const auto base=p.values->peek(row.uop.rs1);if(!base)throw std::logic_error("Rocket store front accepted unknown base");const auto x=row.uop.expanded;row.memory_address=*base+iris::frontend::PureAluValue::sext(((x>>25)<<5)|((x>>7)&31),12);row.memory_size=(x>>12)&3;}
  if(row.source_memory){row.memory_store=(row.uop.expanded&127)==0x23;row.memory_size=(row.uop.expanded>>12)&3;
    if(!row.memory_store&&!row.uop.rd)throw std::runtime_error("IRIS_ROCKET_SOURCE_LOAD_X0_NO_RESP_POLICY_UNMODELED");
    row.memory_operands=p.values->latch(row.uop.rs1,row.memory_store?row.uop.rs2:0);
  }
  row.packet=p.next_packet++;row.rrd=now;row.ex_release=future_cycle(now,divider,1);row.com_cycle=future_cycle(now,divider,3);
  if(rocket_frontend_enabled())row.rocket_frontend=rocket_frontend_.outputs.id;
  row.result_stage=row.counter?ResultStage::wb:row.uop.has(iris::shuttle::JALR)?ResultStage::mem:ResultStage::ex;
  for (const auto& source:{std::pair{iris::shuttle::RXS1,row.uop.rs1},std::pair{iris::shuttle::RXS2,row.uop.rs2}})
    if (row.uop.has(source.first) && source.second && p.last_writer[source.second]) row.raw_producers.push_back(*p.last_writer[source.second]);
  std::sort(row.raw_producers.begin(),row.raw_producers.end());row.raw_producers.erase(std::unique(row.raw_producers.begin(),row.raw_producers.end()),row.raw_producers.end());
  if(profile_.rocket_scalar_memory)for(auto producer:row.raw_producers){const auto&older=p.instructions.at(producer);row.memory_load_use|=older.source_memory&&!older.memory_store&&now==older.rrd+2*divider;}
  if(profile_.rocket_scalar_memory&&row.uop.has(iris::shuttle::WXD)&&row.uop.rd&&p.last_writer[row.uop.rd]){const auto&older=p.instructions.at(*p.last_writer[row.uop.rd]);row.memory_load_use|=older.source_memory&&!older.memory_store&&now==older.rrd+2*divider;}
  const auto id=p.instructions.size();p.instructions.push_back(std::move(row));auto& stored=p.instructions.at(id);if(profile_.empirical&&!frontend_enabled(hart)&&stored.uop.cfi())stored.empirical_prediction=empirical_predict(hart,pc,stored.uop,stored.fetch.insn.length());
  if(p.values) {
    if((rocket_frontend_enabled()||profile_.empirical) && stored.uop.cfi()) {
      stored.branch_operands=p.values->latch(stored.uop.has(iris::shuttle::RXS1)?stored.uop.rs1:0,stored.uop.has(iris::shuttle::RXS2)?stored.uop.rs2:0);
      p.values->issue_external(id,stored.uop.has(iris::shuttle::WXD)?stored.uop.rd:0);
    } else if(stored.empirical_load)p.values->issue_external(id,stored.uop.rd);
    else if(stored.empirical_store||stored.empirical_compute||scalar_fadd_candidate(hart,stored.uop))p.values->issue_external(id,0);
    else if(stored.counter||stored.source_memory)p.values->issue_external(id,stored.memory_store?0:stored.uop.rd);
    else p.values->issue(id,stored.uop.expanded,stored.pc);
  }
  p.packets.push_back({stored.packet,1});p.peak_packets=std::max(p.peak_packets,p.packets.size());
  iris::Op ex{hart,stored.uop.instruction_name+(stored.counter?".EX-operands":".result-ready"),"rocket2.EX",divider,divider};
  ex.retires=false;ex.pc=pc;ex.issue_period=divider;ex.cancellable=rocket_frontend_enabled()||profile_.empirical;
  for (auto producer:stored.raw_producers) if(!p.instructions.at(producer).source_memory)ex.deps.push_back(*p.instructions.at(producer).result);
  if(p.values && !stored.counter)ex.on_complete=[this,hart,id]{
    if(pure_[hart].instructions.at(id).empirical_load)return;
    if(profile_.rocket_scalar_memory){rocket_frontend_.pending_ex.push_back(id);return;}
    auto& p=pure_.at(hart);auto& row=p.instructions.at(id);
    if(row.squashed)return;
    if((rocket_frontend_enabled()||profile_.empirical) && row.uop.cfi()) {
      if(!row.uop.has(iris::shuttle::JALR)){row.private_value=row.uop.has(iris::shuttle::WXD)?row.pc+row.fetch.insn.length():0;p.values->complete_external(id,row.private_value);row.private_value_ready=true;}
    } else if(row.empirical_store){row.private_value=0;p.values->complete_external(id,0);row.private_value_ready=true;}
    else if(row.empirical_compute){row.private_value=0;p.values->complete_external(id,0);row.private_value_ready=true;}
    else if(row.scalar_fadd){scalar_fadd_ex(hart,id);row.private_value=0;p.values->complete_external(id,0);row.private_value_ready=true;}
    else {row.private_value=p.values->complete(id);row.private_value_ready=true;}
  };
  stored.csr_ex=clock_.issue(std::move(ex));if (!stored.counter) stored.result=stored.csr_ex;
  iris::Op mem{hart,stored.uop.instruction_name+".MEM","rocket2.MEM",divider,divider};
  mem.retires=false;mem.pc=pc;mem.issue_period=divider;mem.deps={*stored.csr_ex};mem.cancellable=rocket_frontend_enabled()||profile_.empirical;
  if(stored.empirical_load)mem.on_complete=[this,hart,id]{empirical_load_response(hart,id);};
  else if(rocket_frontend_enabled())mem.on_complete=[this,id]{rocket_frontend_.pending_mem.push_back(id);};else if(profile_.empirical&&stored.uop.cfi())mem.on_complete=[this,id]{empirical_branch_resolve(2,id);};
  stored.mem=clock_.issue(std::move(mem));if(stored.empirical_load)stored.result=stored.mem;
  if((rocket_frontend_enabled()||profile_.empirical)&&stored.uop.has(iris::shuttle::JALR))stored.result=stored.mem;
  iris::Op wb{hart,stored.uop.instruction_name+".WB","rocket2.WB",divider,divider};
  wb.retires=false;wb.pc=pc;wb.issue_period=divider;wb.cancellable=rocket_frontend_enabled()||profile_.empirical;wb.deps={*stored.mem};wb.on_complete=[this,hart,id]{pure_commit(hart,id);};
  stored.com=clock_.issue(std::move(wb));stored.wb=stored.com;if (stored.counter) stored.result=stored.com;
  if(scalar_fadd_candidate(hart,stored.uop))scalar_fadd_reserve(hart,id);
  if(stored.empirical_compute)empirical_async_begin(hart,id);
  if(profile_.empirical)empirical_fetch_consume(hart,stored.pc,stored.fetch.insn.length());
  previous_[hart]=stored.com;if (stored.uop.has(iris::shuttle::WXD)&&stored.uop.rd) p.last_writer[stored.uop.rd]=id;
  auto instruction=fetch.insn;p.frontier=profile_.empirical&&stored.uop.cfi()?stored.empirical_prediction:pc+instruction.length();
  if(rocket_frontend_enabled())rocket_frontend_consume();
}

void iris_timing_adapter::write_rocket_json(std::ostream& out) const {
  out<<",\"rocket_pipeline\":{\"enabled\":"<<(profile_.rocket_pure_pipeline?"true":"false")
     <<",\"domain\":"<<std::quoted(rocket_frontend_enabled()?"experimental-source-Rocket-Frontend-IBuf-RV64IC-counter-CFI":"experimental-RV64IC-counter-read-sequential-frontend")<<",\"calibrated\":false,\"peak_packets\":"
     <<(pure_.size()>2?pure_[2].peak_packets:0)<<",\"instructions\":[";
  bool first=true;
  if (pure_.size()>2) for(size_t i=0;i<pure_[2].instructions.size();++i) {
    const auto& row=pure_[2].instructions[i];auto insn=row.fetch.insn;if(!first)out<<',';first=false;
    out<<"{\"hart\":2,\"sequence\":"<<i<<",\"packet\":"<<row.packet<<",\"pc\":"<<row.pc
       <<",\"raw\":"<<(row.uop.compressed?uint16_t(insn.bits()):uint32_t(insn.bits()))<<",\"length\":"<<(row.exception||row.rocket_replay?0:insn.length())
       <<",\"expanded\":"<<row.uop.expanded<<",\"ID\":"<<row.rrd<<",\"result_stage\":"<<std::quoted(rocket_frontend_enabled()&&(row.rocket_replay||row.exception)?"none":row.counter?"WB":rocket_frontend_enabled()&&row.uop.has(iris::shuttle::JALR)?"MEM":"EX")
       <<",\"counter_read\":"<<(row.counter?"true":"false")
       <<",\"EX_node\":"<<(row.csr_ex?std::to_string(*row.csr_ex):"null")<<",\"MEM_node\":"<<(row.mem?std::to_string(*row.mem):"null")
       <<",\"result_node\":"<<(row.result?std::to_string(*row.result):"null")<<",\"WB_node\":"<<(row.wb?std::to_string(*row.wb):row.com?std::to_string(*row.com):"null")
       <<",\"retired\":"<<(row.retired?"true":"false")<<",\"released\":"<<(row.released?"true":"false")
       <<",\"latched_exception\":"<<(row.exception?"true":"false");
    if(profile_.private_forwarded_values)out<<",\"private_value_ready\":"<<(row.private_value_ready?"true":"false")
       <<",\"private_value\":"<<(row.private_value?std::to_string(*row.private_value):"null");
    if(rocket_frontend_enabled())out<<",\"squashed\":"<<(row.squashed?"true":"false")<<",\"source_frontend_replay\":"<<(row.rocket_replay?"true":"false")<<",\"MEM_resolved\":"<<(row.branch_resolved?"true":"false")<<",\"MEM_wrong_npc\":"<<(row.branch_mispredict?"true":"false")<<",\"MEM_redirect\":"<<(row.branch_redirect?"true":"false");
    if(profile_.rocket_scalar_memory)out<<",\"source_scalar_memory\":"<<(row.source_memory?"true":"false")<<",\"source_memory_replay\":"<<(row.memory_replay?"true":"false")<<",\"source_load_use\":"<<(row.memory_load_use?"true":"false")<<",\"source_cache_accepted\":"<<(row.memory_accepted?"true":"false")<<",\"source_cache_killed\":"<<(row.memory_killed?"true":"false")<<",\"source_load_pending\":"<<(row.memory_pending?"true":"false")<<",\"memory_address\":"<<(row.memory_address_ready?std::to_string(row.memory_address):"null")<<",\"memory_store\":"<<(row.memory_store?"true":"false")<<",\"memory_size_log2\":"<<row.memory_size<<",\"physical_cache_actor\":"<<(row.memory_actor?std::to_string(*row.memory_actor):"null");
    out<<",\"raw_producers\":[";
    for(size_t j=0;j<row.raw_producers.size();++j){if(j)out<<',';out<<row.raw_producers[j];}out<<"]}";
  }
  out<<"]}";
}

#include "iris_scalar_fadd.inc"
