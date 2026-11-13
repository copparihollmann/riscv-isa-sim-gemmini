// Isolated experimental peer; the primary and frozen native trees are unchanged.
// Plain C++ source-derived frontend; no RTL model is constructed here.
#include "iris_timing_adapter.h"
#include "processor.h"
#include <algorithm>
#include <iomanip>
#include <cmath>
#include <limits>
#include <iostream>
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
    if(!profile_.empirical)clock_.configure_resource("shuttle"+std::to_string(h)+".BRANCH_MEM",1);
  }
}

void iris_timing_adapter::frontend_prepare() {
  rocket_frontend_prepare();
  if(profile_.rocket_serial&&!rocket_frontend_.fabric_prepared)rocket_serial_prepare();
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
  if(profile_.saturn_live)saturn_commit();
  rocket_frontend_commit_edge();
  if(profile_.rocket_serial&&rocket_frontend_.fabric_prepared)rocket_serial_commit();
  for(unsigned h=0;h<2;++h)if(frontend_enabled(h)) {
    auto& f=frontend_[h];if(!f.prepared)continue;
    const auto final=f.model->evaluate(f.inputs);
    const bool request=final.memory_request_valid && f.inputs.memory_request_ready;
    f.model->commit();++f.edges;
    if(f.inputs.memory_data) {
      if(!f.active_refill)throw std::logic_error("IRIS_FRONTEND_D_WITHOUT_REFILL");
      if(++f.refills.at(*f.active_refill).returned==8){
        const auto owner=f.refills.at(*f.active_refill).cache_owner;
        if(owner){empirical_cache_->complete(*owner,clock_.now());cache_nodes_.erase(*owner);}
        f.active_refill.reset();++f.completed_refills;
        if(!profile_.keep_history)f.refills.clear();
      }
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
  const size_t index=f.refills.size();f.refills.push_back({address,clock_.now(),{}});f.active_refill=index;++f.accepted_refills;
  std::optional<iris::empirical::Delta> cache_delta;
  double first_cycles=profile_.synthetic_icache_first,outer_interval=1;
  if(profile_.empirical){
    const auto owner=next_cache_owner_++;cache_delta=empirical_cache_->begin_vector({owner,hart,address,64,false,clock_.now()});
    f.refills[index].cache_owner=owner;f.refills[index].l2_misses=cache_delta->l2_misses;
    auto&stats=memory_features_[hart]["ICACHE.SOURCE."+std::string(iris::empirical::path_name(cache_delta->path))];
    ++stats["accesses"];stats["bytes"]+=64;++stats["l1misses"];stats["l2hits"]+=cache_delta->l2_hits;stats["l2misses"]+=cache_delta->l2_misses;
    if(cache_delta->path==iris::empirical::Path::DRAM){
      for(const auto&r:profile_.empirical_cache_rules)if(r.hart==hart){first_cycles+=r.l1+r.outer*cache_delta->l2_misses;outer_interval=r.outer_interval*cache_delta->l2_misses;break;}
      for(const auto&r:profile_.empirical_instruction_rules)if(r.hart==hart){first_cycles=profile_.synthetic_icache_first+r.l1+r.outer*cache_delta->l2_misses;outer_interval=r.interval*cache_delta->l2_misses;break;}
    }
  }
  if(!std::isfinite(first_cycles)||first_cycles>profile_.max_cycles)throw std::runtime_error("IRIS_SOURCE_FRONTEND_EMPIRICAL_SERVICE_HORIZON");
  // These are explicitly synthetic service actors. They are never canceled
  // by a CPU redirect and never presented as source NoC/DRAM latency.
  for(unsigned beat=0;beat<8;++beat) {
    const uint64_t period=beat?profile_.synthetic_icache_gap:uint64_t(std::ceil(first_cycles));
    if(period>(std::numeric_limits<Cycle>::max()-1)/divider)throw std::overflow_error("IRIS_FRONTEND_SYNTHETIC_SERVICE_OVERFLOW");
    const bool outer=!beat&&cache_delta&&cache_delta->l2_misses&&(!profile_.empirical_cache_rules.empty()||!profile_.empirical_instruction_rules.empty());
    iris::Op op{hart,profile_.empirical?"icache.empirical-source-D-beat":"icache.synthetic-D-beat",outer?"empirical.outer":"shuttle"+std::to_string(hart)+".ICACHE_D",period*divider,outer?uint64_t(std::max(1.0,std::ceil(outer_interval)))*divider:divider};
    if(!beat&&cache_delta)for(const auto owner:cache_delta->wait_for){const auto found=cache_nodes_.find(owner);if(found==cache_nodes_.end())throw std::logic_error("IRIS_SOURCE_FRONTEND_CACHE_DEPENDENCY_OWNER_MISSING");op.deps.push_back(found->second);}
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
    if(beat==7&&f.refills[index].cache_owner)cache_nodes_[*f.refills[index].cache_owner]=f.refills[index].beats.back();
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
  if(profile_.empirical_async&&(raw&3)==3){
    // Decode the identical finite async whitelist in iris_shuttle_issue.cc;
    // candidate guards and staging remain owned by the shared CPU path.
    if(auto unit=pure_decode_for_frontend(fetch);unit&&unit->has(iris::shuttle::VECTOR)){u=*unit;u.predicted_next_pc_valid=signals.predicted_next_pc_valid;}
  }
  // FetchBuffer.scala52 uses packet-wide next_pc.valid for SFB, while54
  // masks next_pc.valid separately for each uop. The source frontend owns
  // this field; per-uop prediction alone cannot reconstruct it.
  u.sfb_branch=q.small_forward_branch?iris::shuttle::Signal::yes:iris::shuttle::Signal::no;
  return u;
}

void iris_timing_adapter::frontend_flush_annotations() {
  for(auto id:squash_after_completion_) {
    if(!clock_.mark_cpu_completed_this_cycle_squashed(id,"source-MEM-control-killed-younger-work"))++compacted_cpu_squash_annotations_;
  }
  squash_after_completion_.clear();
}

void iris_timing_adapter::frontend_squash(unsigned hart,size_t anchor,bool shadow_only,const char*reason_override) {
  if(profile_.empirical&&!shadow_only){++empirical_fetch_[hart].generation;empirical_fetch_[hart].response_ready=false;}
  auto& p=pure_[hart];const auto reason=reason_override?reason_override:shadow_only?"source-SFB-taken-shadow-annul":"source-MEM-mispredict";
  if(shadow_only) {
    if(anchor+1>=p.instructions.size() || p.instructions[anchor+1].packet!=p.instructions[anchor].packet || !p.instructions[anchor+1].sfb_shadow)
      throw std::logic_error("IRIS_FRONTEND_SFB_SHADOW_NOT_SAME_PACKET");
    p.values->annul_one(anchor+1);
  } else p.values->discard_younger(anchor);
  for(size_t i=anchor+1;i<p.instructions.size();++i) {
    if(shadow_only && i!=anchor+1)break;
    auto& row=p.instructions[i];if(row.squashed)continue;
    if(row.retired)throw std::logic_error("IRIS_FRONTEND_REDIRECT_AFTER_YOUNGER_RETIREMENT");
    if(row.empirical_compute)empirical_async_cancel(hart,i);
    row.squashed=row.released=true;row.branch_operands.reset();
    if(row.empirical_load_actor&&!row.empirical_load_actor->done)row.empirical_load_actor->discarded=true;
    std::set<iris::NodeId> ids;
    for(const auto node:{row.csr_ex,row.mem,row.result,row.branch_mem,row.com,row.wb})if(node)ids.insert(*node);
    for(auto id:ids) {
      if(row.empirical_load_actor&&row.empirical_load_actor->response==std::optional<iris::NodeId>(id))continue; // accepted memory survives CPU kill
      const auto& node=clock_.nodes().at(id);
      if(node.cancelled)continue;
      if(node.completed)clock_.mark_squashed(id,reason);
      else if(node.issued && node.end==clock_.now() && ((row.result && id==*row.result) || (row.csr_ex && id==*row.csr_ex && !row.counter)) && (!row.com || id!=*row.com))
        {if(!node.op.cancellable||node.physical)throw std::logic_error("IRIS_FRONTEND_DEFERRED_SQUASH_REQUIRES_OWNED_CPU");squash_after_completion_.push_back(id);}
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
  ++f.resolved_controls;if(result.mispredict)++f.mispredicts;
  if(profile_.empirical&&u.cfi()){++empirical_branches_[hart].branches;if(result.mispredict)++empirical_branches_[hart].mispredicts;}

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
  out<<",\"source_frontend\":{\"implementation\":\"source-derived-plain-C++-ShuttleFrontend\",\"scope\":\"M-mode-VM-disabled-harts0/1\",\"saved_firrtl_sha256\":\"f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4\",\"reset_edges\":"<<profile_.frontend_reset_edges
     <<",\"reference_unreset_comparison_seed\":"<<profile_.frontend_seed<<",\"required_unreset_payload_policy\":\"strict-refuse-required-RAS-or-RAM\",\"source_state_injected\":false,\"external_miss_service\":"<<std::quoted(profile_.empirical?"explicit-effective-shared-L2-service":profile_.synthetic_icache_first?"explicit-synthetic":"unknown-refused")
     <<",\"service_source\":"<<std::quoted(profile_.icache_service_source)<<",\"synthetic_first_local_edges\":"<<profile_.synthetic_icache_first<<",\"synthetic_gap_local_edges\":"<<profile_.synthetic_icache_gap
     <<",\"calibrated\":false,\"ethan_image_association_verified\":false,\"harts\":[";
  for(unsigned h=0;h<2;++h) {
    if(h)out<<',';const auto& f=frontend_[h];
    out<<"{\"hart\":"<<h<<",\"memory_replay_redirects\":"<<f.memory_replay_redirects<<",\"resolved_MEM_controls\":"<<f.resolved_controls<<",\"MEM_prediction_corrections\":"<<f.mispredicts<<",\"active_refill\":"<<(f.active_refill?"true":"false")<<",\"accepted_refills\":"<<f.accepted_refills<<",\"completed_refills\":"<<f.completed_refills<<",\"edges\":"<<f.edges<<",\"consumed_uops\":"<<f.consumed<<",\"redirects\":"<<f.redirects<<",\"empty_queue_edges\":"<<f.empty_edges<<",\"refills\":[";
    for(size_t i=0;i<f.refills.size();++i) {
      if(i)out<<',';const auto& r=f.refills[i];out<<"{\"address\":"<<r.address<<",\"accepted\":"<<r.accepted<<",\"returned_beats\":"<<r.returned<<",\"nodes\":[";
      for(size_t j=0;j<r.beats.size();++j){if(j)out<<',';out<<r.beats[j];}out<<"]}";
    }
    out<<"]}";
  }
  out<<"]}";
}

void iris_timing_adapter::frontend_diagnostic(unsigned hart,const char*reason)const{
 const auto&f=frontend_.at(hart);const auto&p=pure_.at(hart);const auto*s=cores_[hart]->get_state();
 std::cerr<<"IRIS_FRONTEND_INVARIANT {\"reason\":"<<std::quoted(reason)<<",\"hart\":"<<hart<<",\"cycle\":"<<clock_.now()<<",\"frontend_edge\":"<<f.edges<<",\"architectural_pc\":"<<s->pc<<",\"ready_prefix\":"<<(f.inputs.ready1?2:f.inputs.ready0?1:0)<<",\"redirect_flush\":"<<f.inputs.redirect_flush<<",\"redirect_valid\":"<<f.inputs.redirect_valid<<",\"redirect_pc\":"<<f.inputs.redirect_pc<<",\"mip\":"<<s->mip->read()<<",\"mip_known\":"<<s->mip->iris_known_bits()<<",\"mie\":"<<s->mie->read()<<",\"mie_known\":"<<s->mie->iris_known_bits()<<",\"queue\":[";
 for(unsigned lane=0;lane<2;++lane){if(lane)std::cerr<<',';const auto&q=f.outputs.queue[lane];std::cerr<<"{\"valid\":"<<q.valid<<",\"pc\":"<<q.pc<<",\"raw\":"<<q.raw<<",\"compressed\":"<<q.compressed<<",\"edge_instruction\":"<<q.edge_instruction<<'}';}
 std::cerr<<"],\"last_CPU_rows\":[";bool first=true;const auto begin=p.instructions.size()>16?std::max(p.instructions.base(),p.instructions.size()-16):p.instructions.base();
 for(size_t id=begin;id<p.instructions.size();++id){if(!first)std::cerr<<',';first=false;const auto&r=p.instructions.at(id);auto raw_insn=r.fetch.insn;std::cerr<<"{\"id\":"<<id<<",\"pc\":"<<r.pc<<",\"raw\":"<<raw_insn.bits()<<",\"RRD\":"<<r.rrd<<",\"retired\":"<<r.retired<<",\"squashed\":"<<r.squashed<<'}';}std::cerr<<"]}\n";
}
