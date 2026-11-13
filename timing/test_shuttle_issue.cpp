#include "shuttle_issue.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>

using namespace iris::shuttle;
namespace {
unsigned checks=0;
void check(bool value,const char* reason) {
  ++checks;
  if(!value) throw std::runtime_error(reason);
}
uint32_t ri(unsigned rd,unsigned rs1,int immediate=1,unsigned opcode=0x13,unsigned f3=0) {
  return (uint32_t(immediate)&0xfff)<<20 | (rs1<<15) | (f3<<12) | (rd<<7) | opcode;
}
uint32_t rr(unsigned rd,unsigned rs1,unsigned rs2,unsigned f7=0,unsigned f3=0,unsigned opcode=0x33) {
  return f7<<25|rs2<<20|rs1<<15|f3<<12|rd<<7|opcode;
}
Uop scalar(uint32_t word) { return decode_scalar(word,word,FrontendSignals::sequential_fixture()); }
bool reason(const LanePlan& lane,const char* why) {
  return std::find(lane.reasons.begin(),lane.reasons.end(),why)!=lane.reasons.end();
}
PacketPlan pair(Uop first,Uop second,IssueSignals s=IssueSignals::empty_pipeline_fixture()) {
  return select_rrd({first,second},s);
}
}

int main() {
  auto idle=IssueSignals::empty_pipeline_fixture();
  auto a=scalar(ri(5,6)), independent=scalar(ri(7,8)), dependent=scalar(ri(7,5));
  auto load=scalar(ri(5,8,0,0x03,3)),store=scalar(0x00543023);
  check(scalar_decode_rows()==242,"source decoder coverage changed without test review");
  auto p=pair(a,independent);
  check(p.ready_prefix==2 && p.lanes[0].integer_result_stage==ResultStage::ex && p.lanes[1].integer_result_stage==ResultStage::ex,"independent EX pair");
  check(pure_integer_bundle({a,independent},p),"pure independent bundle");
  p=pair(a,dependent);
  check(p.ready_prefix==2 && p.lanes[1].integer_result_stage==ResultStage::mem,"same-packet RAW must use MEM ALU");
  check(pure_integer_bundle({a,dependent},p),"pure RAW pair requires retimed integration, not blanket rejection");
  auto busy=idle;busy.mem_lane1_will_be_latealu=Signal::yes;
  p=pair(a,dependent,busy);
  check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.integer.rs1_hazard"),"older late ALU occupies MEM port");
  busy.mem_lane1_will_be_latealu=Signal::unknown;
  p=pair(a,dependent,busy);
  check(p.lanes[1].availability==Availability::needs_input,"unknown MEM ALU occupation cannot become ready");
  p=pair(load,dependent);
  check(p.ready_prefix==2 && p.lanes[1].integer_result_stage==ResultStage::wb,"load-dependent ALU uses late WB path");
  check(!pure_integer_bundle({load,dependent},p),"load hit/replay is not pure bundle integration");
  p=pair(load,scalar(ri(5,9)));
  check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.integer.waw_hazard"),"load WAW without late dependency blocks");
  p=pair(load,scalar(ri(5,5)));
  check(p.ready_prefix==2 && p.lanes[1].uses_latealu==Signal::yes,"load WAW with late result dependency permitted");
  p=pair(a,scalar(ri(5,9)));
  check(p.ready_prefix==2,"ALU WAW is source permitted");
  p=pair(a,scalar(ri(7,5,0,0x03,3)));
  check(p.ready_prefix==1,"ALU to load-base RAW has no same-packet bypass");
  p=pair(store,independent);
  check(p.ready_prefix==2,"store and independent ALU can share packet");
  p=pair(store,load);
  check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.one_memory_per_packet"),"only one memory operation");

  // Actual compressed loop words from the smoke ELF's dependent kernel:
  // 050d(addi a0,a0,3),2785(addiw a5,a5,1),fef59ee3(bne a1,a5,-4).
  auto actual_a=decode_scalar(0x00350513,0x050d,FrontendSignals::sequential_fixture());
  auto actual_counter=decode_scalar(0x0017879b,0x2785,FrontendSignals::sequential_fixture());
  auto actual_branch=scalar(0xfef59ee3);
  p=pair(actual_a,actual_counter);
  check(p.ready_prefix==2 && actual_a.compressed && actual_counter.compressed,"actual smoke scalar loop has two ALUs in one issue packet");
  check(pure_integer_bundle({actual_a,actual_counter},p),"actual smoke pair integration subset");
  p=pair(actual_counter,actual_branch);
  check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.integer.rs2_hazard"),"branch cannot consume same-packet counter result");

  auto branch=scalar(0x00629a63); // bne x5,x6,+20; not small-forward.
  p=pair(a,branch);check(p.ready_prefix==1,"branch dependency cannot use MEM forwarding");
  branch=scalar(0x00941a63); // bne x8,x9,+20
  p=pair(a,branch);check(p.ready_prefix==2,"independent branch uses lane1");
  p=pair(branch,scalar(0x00941a63));
  check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.one_branch_port_per_packet"),"two control transfers cannot pair");
  auto wrong_btb=a;wrong_btb.predicted_next_pc_valid=Signal::yes;
  p=pair(wrong_btb,branch);check(p.ready_prefix==1,"prediction tag reserves branch port on non-CFI too");
  p=pair(branch,independent);check(p.ready_prefix==2 && !pure_integer_bundle({branch,independent},p),"branch shadow needs actual prediction/squash model");

  auto csr=scalar(0xb0002573),fence=scalar(0x0330000f),wfi=scalar(0x10500073);
  p=pair(csr,independent);check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.older_blocked_or_youngest"),"CSR must be youngest");
  p=pair(a,csr);check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.pipe0_only"),"CSR pipe0 only");
  p=pair(fence,independent);check(p.ready_prefix==2,"drained fence is not automatically youngest");
  busy=idle;busy.mem_busy=Signal::yes;
  p=pair(fence,independent,busy);check(p.ready_prefix==0 && reason(p.lanes[0],"rrd.drain_required"),"fence drains previous memory");
  p=pair(csr,independent,busy);check(p.lanes[0].availability==Availability::ready,"ordinary CSR drain can occur later in EX; do not invent RRD condition");
  p=pair(wfi,independent);check(p.ready_prefix==1,"system instruction youngest");
  auto amo=scalar(0x005432afu);
  p=pair(amo,independent);check(p.ready_prefix==2,"unfenced AMO and independent ALU structurally allowed");
  busy=idle;busy.ex_busy=Signal::yes;
  p=pair(amo,independent,busy);check(p.ready_prefix==2,"AMO without aqrl is not forced to drain by this rule");
  auto amo_fenced=scalar(0x065432afu);
  p=pair(amo_fenced,independent,busy);check(p.ready_prefix==0,"aqrl AMO requires drain");

  auto mul=scalar(rr(5,8,9,1));
  p=pair(mul,independent);check(p.ready_prefix==2,"multiplier is lane0 but need not be youngest");
  p=pair(a,mul);check(p.ready_prefix==1,"multiply pipe0 only");
  p=pair(mul,dependent);check(p.ready_prefix==1,"multiply result is not same-packet ALU forward");
  auto fadd=scalar(0x00940553),flw=scalar(ri(5,8,0,0x07,2));
  p=pair(fadd,independent);check(p.ready_prefix==2 && fadd.has(USES_FP),"FP execution pipe0 plus integer ALU");
  p=pair(a,fadd);check(p.ready_prefix==1,"FP execute pipe0");
  p=pair(a,flw);check(p.ready_prefix==2 && !flw.has(USES_FP),"FP load is not classified as FP execution pipe0");
  p=pair(a,scalar(0x00542027));check(p.ready_prefix==1,"FP store uses FP execution path and pipe0");

  auto cfg=scalar(0xc004f5d7); // vsetivli a1,9,e8,m1
  check(cfg.control_verified && cfg.has(SETS_VCFG),"VSET control template");
  p=pair(a,cfg);check(p.ready_prefix==2,"issueVConfig false permits lane1 configuration");
  p=pair(cfg,scalar(0xc004f657));check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.one_vconfig_per_packet"),"one config per packet");
  busy=idle;busy.vconfig_inflight=Signal::yes;
  p=pair(a,cfg,busy);check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.vconfig_inflight"),"in-flight config stalls consumer");

  auto sfb=scalar(0x00029363); // bne x5,x0,+6, unpredicted
  auto compressed=decode_scalar(0x00140413,0x0405,FrontendSignals::sequential_fixture());
  check(sfb.sfb_branch==Signal::yes,"small-forward-branch metadata");
  p=pair(sfb,compressed);check(p.ready_prefix==2 && p.lanes[1].sfb_shadow,"compressed ALU SFB shadow allowed");
  p=pair(sfb,independent);check(p.ready_prefix==1 && reason(p.lanes[1],"rrd.pipe0_only"),"uncompressed SFB shadow requires lane0");
  auto compressed_load=decode_scalar(ri(9,8,0,0x03,3),0x6004,FrontendSignals::sequential_fixture());
  p=pair(sfb,compressed_load);check(p.ready_prefix==1,"memory instruction cannot shadow small-forward branch");

  // Hardware forwarding uses raw rs bitfields even when ISA operation ignores
  // them. A LUI whose immediate happens to encode rs1=5 is retimed to MEM.
  auto lui=scalar((5u<<15)|(7u<<7)|0x37);
  check(!lui.has(RXS1),"LUI has no architectural rs1");
  p=pair(a,lui);check(p.ready_prefix==2 && p.lanes[1].uses_memalu==Signal::yes,"unused encoded field still changes source retiming");
  busy=idle;busy.mem_lane1_will_be_latealu=Signal::unknown;
  p=pair(a,lui,busy);
  check(p.ready_prefix==2 && p.lanes[1].integer_result_stage==ResultStage::unresolved &&
        !pure_integer_bundle({a,lui},p),"RRD readiness does not resolve unknown result-stage occupancy");
  auto immediate_hits=scalar(ri(7,8,5));
  p=pair(a,immediate_hits);check(!immediate_hits.has(RXS2) && p.lanes[1].uses_memalu==Signal::yes,"immediate bits in unused rs2 field can also select MEM ALU");

  check(integer_hazard(5,false,{{true,5,true},{true,5,false}}),"youngest matching producer overrides older ready bypass");
  check(!integer_hazard(5,false,{{true,5,false},{true,5,true}}),"EX ready bypass wins last");
  check(!integer_hazard(5,true,{{false,5,false}}),"invalid bypass cannot override scoreboard");
  busy=idle;busy.integer_hazard[6]=Signal::yes;
  p=pair(a,independent,busy);check(p.ready_prefix==0,"older unready source blocks prefix");
  busy=idle;busy.single_step=Signal::yes;
  p=pair(a,independent,busy);check(p.ready_prefix==1,"single-step must not dual issue");
  busy=IssueSignals{};busy.ex_stall=Signal::yes;
  p=pair(a,independent,busy);check(p.lanes[0].availability==Availability::blocked,"known stall dominates missing inputs");
  p=pair(a,independent,IssueSignals{});check(p.lanes[0].availability==Availability::needs_input,"missing readiness must not silently assume idle");
  auto unknown=decode_scalar(0x02000057,0x02000057,FrontendSignals::sequential_fixture());
  p=pair(unknown,independent);check(p.ready_prefix==0 && p.lanes[0].availability==Availability::needs_input,"unknown vector decode is not an ISA illegal conclusion");
  auto unconfirmed=decode_scalar(a.expanded,a.raw,FrontendSignals{});
  check(!unconfirmed.control_verified,"missing vector override confirmation fails closed");
  check(!decode_scalar(0x050d,0x050d,FrontendSignals::sequential_fixture()).control_verified,"raw compressed words require expansion");

  // Register-index boundary matrix: x0 never creates RAW/WAW hazards, while
  // every nonzero matching ALU source uses the same MEM retiming path.
  for(unsigned rd=0;rd<32;++rd)for(unsigned rs=0;rs<32;++rs) {
    auto first=scalar(ri(rd,0)),second=scalar(ri(31,rs,0));
    auto decision=pair(first,second);
    check(decision.ready_prefix==2,"ALU register matrix should structurally pair");
    check((decision.lanes[1].uses_memalu==Signal::yes)==(rd!=0 && rd==rs),"all integer register identities and x0 forwarding");
  }
  check(maximum_issue_width(0)==2 && maximum_issue_width(1)==2 && maximum_issue_width(2)==1,"heterogeneous issue widths");
  bool rejected=false;try {select_rrd({a,a,a},idle);}catch(const std::invalid_argument&){rejected=true;}
  check(rejected,"must reject a third issue lane");
  std::cout << "shuttle_issue_checks=" << checks << " scalar_templates=" << scalar_decode_rows()
            << " rtl_certified=false timing_calibrated=false\n";
}
