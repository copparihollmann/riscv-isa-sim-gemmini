// Isolated experimental peer; the primary and frozen native trees are unchanged.
#include "../../../pipeline/frontend_rtl_peer_context.cpp"
#include "iris_timing_adapter.h"
#include "processor.h"
#include <algorithm>
#include <iomanip>
#include <limits>
#include <ostream>
#include <set>
#include <stdexcept>

void iris_timing_adapter::frontend_initialize() {
  rocket_frontend_initialize();
  if(!profile_.saved_shuttle_frontend)return;
  for(unsigned h=0;h<2;++h) {
    if(cores_[h]->get_cfg().iris_bootrom_file.empty() || cores_[h]->get_state()->pc!=0x10000)
      throw std::runtime_error("IRIS_FRONTEND_REQUIRES_SOURCE_PHYSICAL_RESET_PC_10000");
    frontend_[h].model=std::make_unique<FrontendPeer>(profile_.frontend_seed,profile_.frontend_reset_edges);
    clock_.configure_resource("shuttle"+std::to_string(h)+".ICACHE_D",1);
    clock_.configure_resource("shuttle"+std::to_string(h)+".BRANCH_MEM",1);
  }
}

void iris_timing_adapter::frontend_prepare() {
  rocket_frontend_prepare();
  for(unsigned h=0;h<2;++h)if(frontend_enabled(h)) {
    auto& f=frontend_[h];
    if(f.next_edge<clock_.now())throw std::logic_error("IRIS_FRONTEND_SKIPPED_SOURCE_EDGE");
    if(f.next_edge!=clock_.now())continue;
    if(f.prepared)throw std::logic_error("IRIS_FRONTEND_PREPARED_TWICE");
    f.inputs.memory_request_ready=profile_.synthetic_icache_first!=0;
    f.outputs=f.model->evaluate(f.inputs);f.prepared=true;
    if(f.outputs.memory_request_valid && !profile_.synthetic_icache_first)
      throw std::runtime_error("IRIS_FRONTEND_MISS_SERVICE_UNMODELED hart="+std::to_string(h)+" address="+std::to_string(f.outputs.memory_request_address));
    if(!f.outputs.queue[0].valid)++f.empty_edges;
  }
}

void iris_timing_adapter::frontend_consume(unsigned hart,unsigned prefix) {
  auto& f=frontend_.at(hart);
  if(!f.prepared || !prefix || prefix>2 || f.inputs.ready0 || f.inputs.redirect_flush)
    throw std::logic_error("IRIS_FRONTEND_SOURCE_DEQUEUE_PHASE");
  for(unsigned i=0;i<prefix;++i)if(!f.outputs.queue[i].valid)throw std::logic_error("IRIS_FRONTEND_DEQUEUE_INVALID_PARCEL");
  f.inputs.ready0=true;f.inputs.ready1=prefix==2;f.consumed+=prefix;
}

void iris_timing_adapter::frontend_commit_edges() {
  rocket_frontend_commit_edge();
  for(unsigned h=0;h<2;++h)if(frontend_enabled(h)) {
    auto& f=frontend_[h];if(!f.prepared)continue;
    const auto final=f.model->evaluate(f.inputs);
    const bool request=final.memory_request_valid && f.inputs.memory_request_ready;
    f.model->commit();++f.edges;
    if(f.inputs.memory_data) {
      if(!f.active_refill)throw std::logic_error("IRIS_FRONTEND_D_WITHOUT_REFILL");
      if(++f.refills.at(*f.active_refill).returned==8)f.active_refill.reset();
    }
    if(request)frontend_refill(h,final.memory_request_address);
    f.inputs={};f.prepared=false;
    const auto divider=profile_.harts[h].divider;
    if(divider>=std::numeric_limits<Cycle>::max()-clock_.now())throw std::overflow_error("IRIS_FRONTEND_CLOCK_OVERFLOW");
    f.next_edge=clock_.now()+divider;
  }
}

void iris_timing_adapter::frontend_refill(unsigned hart,uint64_t address) {
  auto& f=frontend_[hart];const auto divider=profile_.harts[hart].divider;
  if(f.active_refill || address&63 || !profile_.synthetic_icache_first || !profile_.synthetic_icache_gap)
    throw std::logic_error("IRIS_FRONTEND_REFILL_PEER_PROTOCOL");
  const size_t index=f.refills.size();f.refills.push_back({address,clock_.now(),{}});f.active_refill=index;
  // These are explicitly synthetic service actors. They are never canceled
  // by a CPU redirect and never presented as source NoC/DRAM latency.
  for(unsigned beat=0;beat<8;++beat) {
    const auto period=beat?profile_.synthetic_icache_gap:profile_.synthetic_icache_first;
    if(period>(std::numeric_limits<Cycle>::max()-1)/divider)throw std::overflow_error("IRIS_FRONTEND_SYNTHETIC_SERVICE_OVERFLOW");
    iris::Op op{hart,"icache.synthetic-D-beat","shuttle"+std::to_string(hart)+".ICACHE_D",period*divider,divider};
    op.retires=false;op.bytes=8;op.issue_period=divider;
    if(beat)op.deps={f.refills[index].beats.back()};
    op.on_complete=[this,hart,index,beat,address] {
      auto& f=frontend_[hart];
      if(!f.active_refill || *f.active_refill!=index || f.inputs.memory_data || f.refills[index].returned!=beat)
        throw std::logic_error("IRIS_FRONTEND_SYNTHETIC_D_ORDER");
      const auto data=cores_[hart]->iris_frontend_read_beat(address+beat*8);
      if(!std::all_of(data.known.begin(),data.known.end(),[](uint8_t x){return x==0xff;}))
        throw std::runtime_error("IRIS_FRONTEND_UNDEFINED_REFILL_BITS_UNMODELED hart="+std::to_string(hart)+" address="+std::to_string(address+beat*8));
      f.inputs.memory_data=FrontendPeer::DataBeat{data.value};
    };
    f.refills[index].beats.push_back(clock_.issue(std::move(op)));
  }
}

void iris_timing_adapter::frontend_redirect(unsigned hart,reg_t pc,unsigned ras_head) {
  auto& f=frontend_[hart];
  if(f.inputs.redirect_flush && (f.inputs.redirect_pc!=pc || f.inputs.redirect_ras_head!=ras_head))
    throw std::logic_error("IRIS_FRONTEND_MULTIPLE_SOURCE_REDIRECTS");
  f.inputs.redirect_flush=f.inputs.redirect_valid=true;f.inputs.redirect_pc=pc&((uint64_t(1)<<40)-1);f.inputs.redirect_ras_head=ras_head;++f.redirects;
}

void iris_timing_adapter::frontend_boundary_complete(unsigned hart,reg_t pc,const insn_fetch_t& fetch) {
  auto& f=frontend_[hart];
  if(!f.conservative || f.conservative->pc!=pc)throw std::logic_error("IRIS_FRONTEND_BOUNDARY_COMPLETION_WITHOUT_PARCEL");
  const auto next=cores_[hart]->get_state()->pc;auto insn=fetch.insn;
  // Nonpipelined operations retain the explicit conservative fixture cost.
  // Source pipeline-qualified branches use MEM control below instead.
  if(next!=pc+insn.length() || f.conservative->prediction_valid)frontend_redirect(hart,next,f.conservative->ras_head);
  if((uint32_t(insn.bits())&0x707f)==0x100f) {
    f.inputs.invalidate_icache=true;
    if(!f.inputs.redirect_flush)frontend_redirect(hart,next,f.conservative->ras_head);
  }
  f.conservative.reset();
}

std::optional<iris::shuttle::Uop> iris_timing_adapter::frontend_decode(unsigned hart,const insn_fetch_t& fetch,unsigned lane) const {
  const auto& f=frontend_.at(hart);if(!f.prepared || lane>1 || !f.outputs.queue[lane].valid)return {};
  const auto& q=f.outputs.queue[lane];
  const auto raw=q.compressed?uint16_t(q.raw):q.raw;auto insn=fetch.insn;
  if((q.compressed?uint16_t(insn.bits()):uint32_t(insn.bits()))!=raw)
    throw std::runtime_error("IRIS_FRONTEND_FETCH_DECODE_IDENTITY_MISMATCH hart="+std::to_string(hart)+" lane="+std::to_string(lane)+" pc="+std::to_string(q.pc)+" queue="+std::to_string(raw)+" fetched="+std::to_string(uint32_t(insn.bits()))+" length="+std::to_string(insn.length()));
  // Wrong-path parcels can resemble unsupported >32-bit encodings. Do not
  // turn their speculative decode into a host failure before an older MEM
  // branch can annul them; leave them at the conservative boundary.
  if(insn.length()!=(q.compressed?2:4))return {};
  const iris::shuttle::FrontendSignals signals{q.prediction_valid?iris::shuttle::Signal::yes:iris::shuttle::Signal::no,iris::shuttle::Signal::no,q.exception};
  auto u=iris::shuttle::decode_scalar(q.expanded,raw,signals);
  // FetchBuffer.scala52 uses packet-wide next_pc.valid for SFB, while54
  // masks next_pc.valid separately for each uop. The source frontend owns
  // this field; per-uop prediction alone cannot reconstruct it.
  u.sfb_branch=q.small_forward_branch?iris::shuttle::Signal::yes:iris::shuttle::Signal::no;
  return u;
}

void iris_timing_adapter::frontend_flush_annotations() {
  for(auto id:squash_after_completion_) {
    if(!clock_.nodes().at(id).completed)throw std::logic_error("IRIS_FRONTEND_SAME_EDGE_SQUASH_DID_NOT_COMPLETE");
    clock_.mark_squashed(id,"source-MEM-control-killed-younger-work");
  }
  squash_after_completion_.clear();
}

void iris_timing_adapter::frontend_squash(unsigned hart,size_t anchor,bool shadow_only) {
  auto& p=pure_[hart];const auto reason=shadow_only?"source-SFB-taken-shadow-annul":"source-MEM-mispredict";
  if(shadow_only) {
    if(anchor+1>=p.instructions.size() || p.instructions[anchor+1].packet!=p.instructions[anchor].packet || !p.instructions[anchor+1].sfb_shadow)
      throw std::logic_error("IRIS_FRONTEND_SFB_SHADOW_NOT_SAME_PACKET");
    p.values->annul_one(anchor+1);
  } else p.values->discard_younger(anchor);
  for(size_t i=anchor+1;i<p.instructions.size();++i) {
    if(shadow_only && i!=anchor+1)break;
    auto& row=p.instructions[i];if(row.squashed)continue;
    if(row.retired)throw std::logic_error("IRIS_FRONTEND_REDIRECT_AFTER_YOUNGER_RETIREMENT");
    row.squashed=row.released=true;row.branch_operands.reset();
    std::set<iris::NodeId> ids;
    for(const auto node:{row.csr_ex,row.mem,row.result,row.branch_mem,row.com,row.wb})if(node)ids.insert(*node);
    for(auto id:ids) {
      const auto& node=clock_.nodes().at(id);
      if(node.cancelled)continue;
      if(node.completed)clock_.mark_squashed(id,reason);
      else if(node.issued && node.end==clock_.now() && ((row.result && id==*row.result) || (row.csr_ex && id==*row.csr_ex && !row.counter)) && (!row.com || id!=*row.com))
        squash_after_completion_.push_back(id);
      else clock_.cancel(id,reason);
    }
    auto packet=std::find_if(p.packets.begin(),p.packets.end(),[&](const PurePacket& x){return x.id==row.packet;});
    if(packet==p.packets.end() || !packet->remaining)throw std::logic_error("IRIS_FRONTEND_CANCEL_PACKET_ACCOUNTING");
    if(!--packet->remaining)p.packets.erase(packet);
  }
  p.last_writer={};
  for(size_t i=p.first_live;i<p.instructions.size();++i) {
    const auto& u=p.instructions[i];
    if(!u.released && !u.squashed && u.uop.has(iris::shuttle::WXD) && u.uop.rd)p.last_writer[u.uop.rd]=i;
  }
  previous_[hart]=p.instructions[anchor].wb?p.instructions[anchor].wb:p.instructions[anchor].com;
  for(size_t i=anchor+1;i<p.instructions.size();++i)if(!p.instructions[i].squashed)previous_[hart]=p.instructions[i].wb?p.instructions[i].wb:p.instructions[i].com;
  while(p.first_live<p.instructions.size() && p.instructions[p.first_live].released)++p.first_live;
  if(!shadow_only){p.boundary=false;p.deferred_fetch={};}
}

void iris_timing_adapter::frontend_branch_resolve(unsigned hart,size_t id) {
  auto& p=pure_[hart];auto& selected=p.instructions.at(id);auto& f=frontend_[hart];
  if(selected.squashed)throw std::logic_error("IRIS_FRONTEND_CANCELED_MEM_CONTROL_CALLBACK");
  std::array<iris::frontend::ShuttleBranch::Uop,2> packet{};
  for(size_t i=p.first_live;i<p.instructions.size();++i) {
    const auto& r=p.instructions[i];if(r.packet!=selected.packet || r.squashed)continue;
    if(!r.frontend || r.lane>1)throw std::logic_error("IRIS_FRONTEND_MEM_WITHOUT_SOURCE_PARCEL");
    const auto& q=*r.frontend;auto& u=packet[r.lane];
    u.valid=true;u.expanded=r.uop.expanded;u.pc=r.pc;u.compressed=q.compressed;
    u.branch=r.uop.has(iris::shuttle::BRANCH);u.jal=r.uop.has(iris::shuttle::JAL);u.jalr=r.uop.has(iris::shuttle::JALR);
    u.taken=r.branch_taken;u.wdata=r.branch_wdata;u.predicted_valid=q.prediction_valid;u.predicted_pc=q.predicted_pc;u.sfb_branch=q.small_forward_branch;u.ras_head=q.ras_head;
  }
  const auto result=iris::frontend::ShuttleBranch::resolve(packet);
  selected.branch_resolved=true;selected.branch_mispredict=result.mispredict;selected.branch_redirect=result.redirect;selected.branch_sfb_pair=result.short_forward_pair;
  if(!result.selected || result.lane!=selected.lane)throw std::logic_error("IRIS_FRONTEND_MEM_BRANCH_SELECTION");
  const auto& q=*selected.frontend;const auto& u=selected.uop;
  if(result.predictor_update) {
    const auto rd=(u.expanded>>7)&31,rs1=(u.expanded>>15)&31;
    const unsigned type=(u.has(iris::shuttle::JAL)||u.has(iris::shuttle::JALR)) && (rd&1)?2:
      u.has(iris::shuttle::JALR) && (rs1==1 || rs1==5)?3:u.cfi() && !u.has(iris::shuttle::BRANCH)?1:0;
    f.inputs.btb={true,true,result.mispredict,q.btb_valid?q.btb_entry:32,type,result.fetch_pc,result.next_pc&((uint64_t(1)<<39)-1),result.branch_pc};
    f.inputs.bht={true,u.has(iris::shuttle::BRANCH),result.taken,result.mispredict,q.bht_history,q.bht_value,result.fetch_pc};
  }
  if(result.ras_update)f.inputs.ras={true,result.ras_update_head,result.ras_address};
  if(result.short_forward_pair && result.taken)frontend_squash(hart,id,true);
  if(result.redirect) {
    frontend_squash(hart,id,false);p.frontier=result.next_pc;
    frontend_redirect(hart,result.next_pc,result.redirect_ras_head);
  }
}

void iris_timing_adapter::write_frontend_json(std::ostream& out) const {
  if(!profile_.saved_shuttle_frontend)return;
  out<<",\"source_frontend\":{\"implementation\":\"saved-Iris-ShuttleFrontend-compiled-RTL\",\"scope\":\"M-mode-VM-disabled-harts0/1\",\"saved_firrtl_sha256\":\"f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4\",\"reset_edges\":"<<profile_.frontend_reset_edges
     <<",\"unreset_state_seed\":"<<profile_.frontend_seed<<",\"source_state_injected\":false,\"external_miss_service\":"<<std::quoted(profile_.synthetic_icache_first?"explicit-synthetic":"unknown-refused")
     <<",\"service_source\":"<<std::quoted(profile_.icache_service_source)<<",\"synthetic_first_local_edges\":"<<profile_.synthetic_icache_first<<",\"synthetic_gap_local_edges\":"<<profile_.synthetic_icache_gap
     <<",\"calibrated\":false,\"ethan_image_association_verified\":false,\"harts\":[";
  for(unsigned h=0;h<2;++h) {
    if(h)out<<',';const auto& f=frontend_[h];
    out<<"{\"hart\":"<<h<<",\"edges\":"<<f.edges<<",\"consumed_uops\":"<<f.consumed<<",\"redirects\":"<<f.redirects<<",\"empty_queue_edges\":"<<f.empty_edges<<",\"refills\":[";
    for(size_t i=0;i<f.refills.size();++i) {
      if(i)out<<',';const auto& r=f.refills[i];out<<"{\"address\":"<<r.address<<",\"accepted\":"<<r.accepted<<",\"returned_beats\":"<<r.returned<<",\"nodes\":[";
      for(size_t j=0;j<r.beats.size();++j){if(j)out<<',';out<<r.beats[j];}out<<"]}";
    }
    out<<"]}";
  }
  out<<"]}";
}
