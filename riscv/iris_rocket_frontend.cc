// Isolated Rocket source frontend; shared/frozen/primary native trees unchanged.
#include "../../../pipeline/rocket_frontend_rtl_peer.cpp"
#include "iris_timing_adapter.h"
#include "processor.h"
#include <algorithm>
#include <iomanip>
#include <limits>
#include <ostream>
#include <stdexcept>

void iris_timing_adapter::rocket_frontend_initialize() {
  if(!rocket_frontend_enabled())return;
  if(cores_.size()!=3 || cores_[2]->get_cfg().iris_bootrom_file.empty() || cores_[2]->get_state()->pc!=0x10000)
    throw std::runtime_error("IRIS_ROCKET_FRONTEND_REQUIRES_THREE_HART_PHYSICAL_RESET");
  rocket_frontend_.model=std::make_unique<RocketFrontendPeer>(profile_.frontend_seed,profile_.frontend_reset_edges);
  clock_.configure_resource("rocket2.ICACHE_D",1);
}
void iris_timing_adapter::rocket_frontend_prepare() {
  if(!rocket_frontend_enabled())return;auto& f=rocket_frontend_;
  if(f.next_edge<clock_.now())throw std::logic_error("IRIS_ROCKET_FRONTEND_SKIPPED_SOURCE_EDGE");
  if(f.next_edge!=clock_.now())return;
  if(f.prepared)throw std::logic_error("IRIS_ROCKET_FRONTEND_PREPARED_TWICE");
  f.inputs.memory_request_ready=profile_.synthetic_icache_first!=0;
  f.inputs.might_request=f.might_request;f.inputs.progress=f.next_progress;
  // Saved CSRFile_2 reg_custom_0 reset value/mask0x208. Writes are explicitly
  // refused until the native custom-CSR functional policy is implemented.
  f.inputs.custom_csr=0x208;
  const auto pmp=cores_[2]->iris_frontend_pmp();
  for(unsigned i=0;i<8;++i){const auto cfg=pmp[i].first;auto& out=f.inputs.pmp[i];out.locked=cfg&0x80;out.mode=(cfg>>3)&3;out.execute=cfg&4;out.write=cfg&2;out.read=cfg&1;out.address=pmp[i].second;
    const auto base=(out.address<<1)|(out.mode&1);out.mask=(((base&~(base+1))<<2)|3)&((uint64_t(1)<<35)-1);}
  f.outputs=f.model->evaluate(f.inputs);f.prepared=true;
  if(f.outputs.memory_request_valid && !profile_.synthetic_icache_first)
    throw std::runtime_error("IRIS_ROCKET_FRONTEND_MISS_SERVICE_UNMODELED address="+std::to_string(f.outputs.memory_request_address));
}
void iris_timing_adapter::rocket_frontend_consume() {
  auto& f=rocket_frontend_;
  if(!f.prepared || !f.outputs.id.valid || f.inputs.id_ready || f.inputs.redirect_valid)throw std::logic_error("IRIS_ROCKET_FRONTEND_ID_PHASE");
  f.inputs.id_ready=true;++f.consumed;
}
void iris_timing_adapter::rocket_frontend_commit_edge() {
  if(!rocket_frontend_enabled())return;auto& f=rocket_frontend_;if(!f.prepared)return;
  // RocketCore1122 drives IBuf.ready from decode stall, independently of
  // IBuf.valid. A32-bit instruction crossing a4-byte fetch packet needs
  // this readiness while ID.valid isfalse to accept its second parcel.
  // Driving readiness only after seeing a complete instruction deadlocks.
  const auto& admission=pure_[2];
  const bool source_stall=profile_.source_counter_clock&&source_counter_clocks_[2].blocks_rrd(clock_.now());
  const bool waiting_exception=!admission.instructions.empty()&&admission.instructions.back().exception&&!admission.instructions.back().released;
  if(!f.outputs.id.valid && !blocked_[2] && !source_stall && !waiting_exception && admission.packets.size()<3 && (!admission.engaged||!admission.boundary) && !f.inputs.redirect_valid)f.inputs.id_ready=true;
  const auto final=f.model->evaluate(f.inputs);const bool request=final.memory_request_valid && f.inputs.memory_request_ready;
  f.model->commit();++f.edges;
  if(f.inputs.memory_data){if(!f.active_refill)throw std::logic_error("IRIS_ROCKET_FRONTEND_D_WITHOUT_REFILL");if(++f.refills.at(*f.active_refill).returned==8)f.active_refill.reset();}
  if(request)rocket_frontend_refill(final.memory_request_address);
  bool ex=false,mem=false;const auto divider=profile_.harts[2].divider;
  const auto& p=pure_[2];
  for(size_t i=p.first_live;i<p.instructions.size();++i){const auto& row=p.instructions[i];if(row.squashed)continue;
    ex|=row.rrd+divider==clock_.now();mem|=row.rrd+2*divider==clock_.now();
  }
  // Conservative operations have an explicit synthetic standing-valid
  // CPU boundary; their actual EX/MEM timing is outside this subset.
  f.might_request=ex||mem||pending_[2].has_value();f.next_progress=f.last_architectural_wb && *f.last_architectural_wb==clock_.now();
  f.inputs={};f.prepared=false;
  if(divider>=std::numeric_limits<Cycle>::max()-clock_.now())throw std::overflow_error("IRIS_ROCKET_FRONTEND_CLOCK_OVERFLOW");
  f.next_edge=clock_.now()+divider;
}
void iris_timing_adapter::rocket_frontend_refill(uint64_t address) {
  auto& f=rocket_frontend_;const auto divider=profile_.harts[2].divider;
  if(f.active_refill || address&63 || !profile_.synthetic_icache_first || !profile_.synthetic_icache_gap)throw std::logic_error("IRIS_ROCKET_FRONTEND_REFILL_PROTOCOL");
  const size_t index=f.refills.size();f.refills.push_back({address,clock_.now(),{}});f.active_refill=index;
  for(unsigned beat=0;beat<8;++beat){const auto period=beat?profile_.synthetic_icache_gap:profile_.synthetic_icache_first;
    if(period>(std::numeric_limits<Cycle>::max()-1)/divider)throw std::overflow_error("IRIS_ROCKET_FRONTEND_SYNTHETIC_SERVICE_OVERFLOW");
    iris::Op op{2,"icache.synthetic-D-beat","rocket2.ICACHE_D",period*divider,divider};op.retires=false;op.bytes=8;op.issue_period=divider;
    if(beat)op.deps={f.refills[index].beats.back()};
    op.on_complete=[this,index,beat,address]{auto& f=rocket_frontend_;if(!f.active_refill || *f.active_refill!=index || f.inputs.memory_data || f.refills[index].returned!=beat)throw std::logic_error("IRIS_ROCKET_FRONTEND_SYNTHETIC_D_ORDER");
      const auto data=cores_[2]->iris_frontend_read_beat(address+beat*8);
      if(!std::all_of(data.known.begin(),data.known.end(),[](uint8_t x){return x==0xff;}))throw std::runtime_error("IRIS_ROCKET_FRONTEND_UNDEFINED_REFILL_BITS_UNMODELED");
      f.inputs.memory_data=RocketFrontendPeer::DataBeat{data.value,false};};
    f.refills[index].beats.push_back(clock_.issue(std::move(op)));
  }
}
void iris_timing_adapter::rocket_frontend_redirect(reg_t pc,bool speculative) {
  auto& f=rocket_frontend_;pc&=(uint64_t(1)<<40)-1;
  // A WB redirect has priority over same-edge MEM. Preserve that priority
  // explicitly rather than silently replacing a different pending target.
  if(f.inputs.redirect_valid && (!f.inputs.redirect_speculative || speculative)) {
    if(f.inputs.redirect_pc!=pc && !f.inputs.redirect_speculative)throw std::logic_error("IRIS_ROCKET_MULTIPLE_WB_REDIRECTS");
    return;
  }
  f.inputs.redirect_valid=true;f.inputs.redirect_speculative=speculative;f.inputs.redirect_pc=pc;++f.redirects;
}
void iris_timing_adapter::rocket_frontend_boundary_complete(reg_t pc,const insn_fetch_t& fetch) {
  auto& f=rocket_frontend_;if(!f.conservative || f.conservative->pc!=pc)throw std::logic_error("IRIS_ROCKET_BOUNDARY_WITHOUT_PARCEL");
  const auto next=cores_[2]->get_state()->pc;
  // Conservative instructions do not carry qualified source CPU stages.
  // Flush their queued younger instructions on completion and resume at the
  // architectural next PC; no empirical cycle penalty is introduced.
  rocket_frontend_redirect(next);
  auto instruction=fetch.insn;
  if((uint32_t(instruction.bits())&0x707f)==0x100f)f.inputs.invalidate_icache=true;
  f.conservative.reset();
}
std::optional<iris::shuttle::Uop> iris_timing_adapter::rocket_frontend_decode(const insn_fetch_t& fetch) const {
  const auto& f=rocket_frontend_;if(!f.prepared || !f.outputs.id.valid || f.outputs.id.replay)return {};
  const auto& q=f.outputs.id;auto insn=fetch.insn;const uint32_t raw=q.compressed?uint16_t(q.raw):q.raw;
  if(uint32_t(insn.bits())!=raw || insn.length()!=(q.compressed?2:4))return {};
  const bool exception=q.first_access_fault||q.first_page_fault||q.first_guest_page_fault||q.second_access_fault||q.second_page_fault||q.second_guest_page_fault;
  return iris::shuttle::decode_scalar(q.expanded,raw,{iris::shuttle::Signal::no,iris::shuttle::Signal::no,exception});
}
void iris_timing_adapter::rocket_frontend_resolve_mem() {
  if(!rocket_frontend_enabled())return;auto& f=rocket_frontend_;auto ids=std::move(f.pending_mem);f.pending_mem.clear();
  if(!ids.empty() && !f.prepared)throw std::logic_error("IRIS_ROCKET_MEM_CONTROL_OFF_CORE_EDGE");
  for(auto id:ids){auto& p=pure_[2];auto& row=p.instructions.at(id);if(row.squashed || row.rocket_replay)continue;
    iris::frontend::RocketBranch::Input in;in.instruction=row.uop.expanded;in.pc=row.pc;in.wdata=row.branch_wdata;
    in.valid=!row.exception;in.exception=bool(row.exception);in.compressed=row.uop.compressed;
    in.branch=row.uop.has(iris::shuttle::BRANCH);in.jal=row.uop.has(iris::shuttle::JAL);in.jalr=row.uop.has(iris::shuttle::JALR);in.taken=row.branch_taken;
    for(size_t i=id+1;i<p.instructions.size();++i){const auto& younger=p.instructions[i];if(!younger.squashed && younger.rrd+profile_.harts[2].divider==clock_.now()){
      if(in.ex_pc_valid)throw std::logic_error("IRIS_ROCKET_MULTIPLE_SOURCE_EX_PCS");in.ex_pc_valid=true;in.ex_pc=younger.pc;}}
    in.ibuf_valid=f.outputs.id.valid;in.fetch_valid=f.outputs.fetch_valid;in.ibuf_pc=f.outputs.id.pc;
    in.take_pc_wb=f.inputs.redirect_valid&&!f.inputs.redirect_speculative;
    if(!row.branch_operands && row.uop.cfi() && !row.private_value_ready)throw std::logic_error("IRIS_ROCKET_BRANCH_OPERANDS_MISSING");
    if(row.uop.cfi() && row.branch_operands){const auto operands=p.values->read(*row.branch_operands);
      if(!operands[0]||!operands[1])throw std::runtime_error("IRIS_ROCKET_FRONTEND_UNDEFINED_BRANCH_OPERANDS_UNMODELED");
      if(in.branch)in.taken=row.branch_taken=iris::frontend::ShuttleBranch::compare(row.uop.expanded,*operands[0],*operands[1]);
      if(in.jalr)in.wdata=row.branch_wdata=*operands[0]+iris::frontend::PureAluValue::sext(row.uop.expanded>>20,12);
      row.branch_operands.reset();}
    const auto out=iris::frontend::RocketBranch::resolve(in);row.branch_resolved=true;row.branch_mispredict=out.wrong_npc;row.branch_redirect=out.redirect;
    if(in.jalr){row.private_value=out.link;row.private_value_ready=true;p.values->complete_external(id,row.private_value);}
    if(out.btb_update)f.inputs.btb={true,out.btb_valid,row.rocket_frontend->btb_entry,out.cfi_type,out.fetch_pc,out.branch_pc};
    if(out.bht_update)f.inputs.bht={true,in.branch,in.taken,out.wrong_npc,row.rocket_frontend->bht_history,out.fetch_pc};
    // Even a non-redirected update uses actual MEMnpc on req.bits.pc.
    if(!in.take_pc_wb)f.inputs.redirect_pc=out.next_pc;
    if(out.redirect){frontend_squash(2,id,false);p.frontier=out.next_pc;rocket_frontend_redirect(out.next_pc,true);}
  }
}
void iris_timing_adapter::rocket_frontend_replay_accept() {
  auto& f=rocket_frontend_;auto& p=pure_[2];const auto now=clock_.now(),d=profile_.harts[2].divider;
  if(!f.prepared || !f.outputs.id.valid || !f.outputs.id.replay || p.packets.size()>=3)throw std::logic_error("IRIS_ROCKET_REPLAY_ACCEPT_PHASE");
  if(!p.engaged){p.engaged=true;p.boundary=false;p.frontier=f.outputs.id.pc;p.last_writer={};iris::frontend::ForwardedValues::Snapshot initial;
    for(unsigned reg=0;reg<32;++reg){const auto value=cores_[2]->get_state()->XPR.read_transport(reg);if(std::all_of(value.known.begin(),value.known.end(),[](uint8_t x){return x==0xff;}))initial[reg]=value.value;}
    p.values.emplace(initial,3);}
  PureInstruction row;row.pc=f.outputs.id.pc;row.fetch={nullptr,insn_t(0)};row.rocket_frontend=f.outputs.id;row.rocket_replay=true;row.packet=p.next_packet++;row.rrd=now;row.ex_release=now+d;row.com_cycle=now+3*d;
  const auto id=p.instructions.size();p.instructions.push_back(row);p.packets.push_back({row.packet,1});p.peak_packets=std::max(p.peak_packets,p.packets.size());p.values->issue_external(id,0);
  iris::Op ex{2,"frontend-replay.EX","rocket2.EX",d,d};ex.retires=false;ex.pc=row.pc;ex.issue_period=d;ex.cancellable=true;p.instructions[id].csr_ex=clock_.issue(std::move(ex));
  iris::Op mem{2,"frontend-replay.MEM","rocket2.MEM",d,d};mem.retires=false;mem.pc=row.pc;mem.issue_period=d;mem.cancellable=true;mem.deps={*p.instructions[id].csr_ex};p.instructions[id].mem=clock_.issue(std::move(mem));
  iris::Op wb{2,"frontend-replay.WB-redirect","rocket2.WB",d,d};wb.retires=false;wb.pc=row.pc;wb.issue_period=d;wb.cancellable=true;wb.deps={*p.instructions[id].mem};wb.on_complete=[this,id]{rocket_frontend_replay_complete(id);};
  p.instructions[id].wb=p.instructions[id].com=clock_.issue(std::move(wb));previous_[2]=p.instructions[id].com;
  p.last_attempt=now;rocket_frontend_consume();++f.replays;
}
void iris_timing_adapter::rocket_frontend_replay_complete(size_t id) {
  auto& p=pure_[2];auto& row=p.instructions.at(id);
  if(row.squashed || id!=p.next_commit || cores_[2]->get_state()->pc!=row.pc)throw std::logic_error("IRIS_ROCKET_REPLAY_WB_ARCHITECTURAL_FRONTIER");
  frontend_squash(2,id,false);p.values->annul_one(id);
  if(p.packets.empty() || p.packets.front().id!=row.packet)throw std::logic_error("IRIS_ROCKET_REPLAY_PACKET_ORDER");
  p.packets.pop_front();row.released=true;++p.next_commit;
  while(p.next_commit<p.instructions.size()&&p.instructions[p.next_commit].squashed)++p.next_commit;
  while(p.first_live<p.instructions.size()&&p.instructions[p.first_live].released)++p.first_live;
  p.frontier=row.pc;rocket_frontend_redirect(row.pc);++completions_;
}
void iris_timing_adapter::write_rocket_frontend_json(std::ostream& out) const {
  if(!rocket_frontend_enabled())return;const auto& f=rocket_frontend_;
  out<<",\"rocket_source_frontend\":{\"implementation\":\"saved-Iris-Frontend-IBuf-compiled-RTL\",\"clock\":\"actual-direct-core-clockGate-false\",\"source_state_injected\":false,\"reset_edges\":"<<profile_.frontend_reset_edges<<",\"unreset_state_seed\":"<<profile_.frontend_seed<<",\"edges\":"<<f.edges<<",\"consumed_uops\":"<<f.consumed<<",\"redirects\":"<<f.redirects<<",\"source_replay_tokens\":"<<f.replays<<",\"custom_CSR\":\"source-reset-0x208-only-access-unmodeled-refused\",\"external_miss_service\":"<<std::quoted(profile_.synthetic_icache_first?"explicit-synthetic":"unknown-refused")<<",\"calibrated\":false,\"ethan_image_association_verified\":false,\"refills\":[";
  for(size_t i=0;i<f.refills.size();++i){if(i)out<<',';const auto& r=f.refills[i];out<<"{\"address\":"<<r.address<<",\"accepted\":"<<r.accepted<<",\"returned_beats\":"<<r.returned<<",\"nodes\":[";for(size_t j=0;j<r.beats.size();++j){if(j)out<<',';out<<r.beats[j];}out<<"]}";}out<<"],\"final_CPU_boundary\":{\"engaged\":"<<(pure_[2].engaged?"true":"false")<<",\"boundary\":"<<(pure_[2].boundary?"true":"false")<<",\"blocked\":"<<(blocked_[2]?"true":"false")<<",\"frontier\":"<<pure_[2].frontier<<",\"architectural_PC\":"<<cores_[2]->get_state()->pc<<",\"packets\":"<<pure_[2].packets.size()<<",\"next_commit\":"<<pure_[2].next_commit<<",\"instructions\":"<<pure_[2].instructions.size()<<",\"ID_valid\":"<<(f.outputs.id.valid?"true":"false")<<",\"ID_replay\":"<<(f.outputs.id.replay?"true":"false")<<",\"ID_PC\":"<<f.outputs.id.pc<<",\"fetch_valid\":"<<(f.outputs.fetch_valid?"true":"false")<<",\"might_request\":"<<(f.might_request?"true":"false")<<"}}";
}
