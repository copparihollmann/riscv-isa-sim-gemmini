// Experimental serialized Shuttle boundary. Real physical responses determine
// completion; source LSU overlap/throughput and fault staging remain unqualified.
#include "iris_timing_adapter.h"
#include "processor.h"
#include <iomanip>
#include <ostream>
namespace {thread_local iris_timing_adapter*shuttle_owner=nullptr;}
void iris_timing_adapter::shuttle_memory_issue(unsigned hart,reg_t pc,const insn_fetch_t&fetch,uint32_t expanded){
  auto*core=cores_.at(hart);const auto*s=core->get_state();auto&m=shuttle_memory_.at(hart);
  if(m.active||blocked_[hart]||!pure_[hart].packets.empty()||pure_[hart].engaged)throw std::logic_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_BOUNDARY_NOT_DRAINED");
  if(!core->iris_pipeline_context_safe()||s->prv!=PRV_M||s->v||s->debug_mode||(s->mstatus->read()&MSTATUS_MPRV))throw std::runtime_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_PRIVILEGE_UNQUALIFIED");
  const unsigned opcode=expanded&127,funct=(expanded>>12)&7,base=(expanded>>15)&31,rs2=(expanded>>20)&31,rd=(expanded>>7)&31;
  const bool fence=opcode==0x0f&&funct==0;
  auto raw_instruction=fetch.insn;
  if(raw_instruction.length()!=4)throw std::runtime_error("IRIS_SHUTTLE_SOURCE_COMPRESSED_DATA_UNQUALIFIED");
  if(fence&&expanded!=0x0330000f)throw std::runtime_error("IRIS_SHUTTLE_SOURCE_FENCE_FORM_UNQUALIFIED");
  if(!fence&&((opcode!=3&&opcode!=0x23)||funct!=3))throw std::runtime_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_WIDTH_UNQUALIFIED");
  if(!fence)s->XPR.require_defined(base,sizeof(reg_t),{hart,pc,"source-Shuttle-memory-address"});
  const bool store=opcode==0x23;const unsigned imm=store?((expanded>>25)<<5)|rd:expanded>>20;
  const auto address=fence?uint64_t(0):s->XPR.read_transport(base).value+iris::frontend::PureAluValue::sext(imm,12);
  if(!fence&&(address&7))throw std::runtime_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_MISALIGNED_FAULT_UNQUALIFIED");
  if(!fence&&(address<0x80000000ULL||address>=0x180000000ULL||address>0x180000000ULL-8))throw std::runtime_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_ADDRESS_SCOPE_UNQUALIFIED");
  if(!fence&&!(opcode==3&&rd==0)&&shuttle_discard_outstanding_[hart])throw std::runtime_error("IRIS_SHUTTLE_SOURCE_PENDING_DISCARD_REQUIRES_FENCE");
  if(store)s->XPR.require_defined(rs2,sizeof(reg_t),{hart,pc,"source-Shuttle-store-data"});
  auto&front=frontend_.at(hart);if(!front.prepared||!front.outputs.queue[0].valid||front.outputs.queue[0].pc!=pc)throw std::logic_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_PARCEL_OWNER");
  front.conservative=front.outputs.queue[0];frontend_consume(hart,1);
  auto actual=fetch;actual.func=&iris_timing_adapter::shuttle_memory_handler;pending_[hart]=Pending{pc,actual,{}};blocked_[hart]=true;
  m.active=true;m.fence=fence;m.discard=opcode==3&&rd==0;m.store=store;m.address=address;m.data=store?s->XPR.read_transport(rs2).value:0;m.value=0;m.tag=(rd<<1)&63;m.accepted=m.response=false;m.retries=0;m.issued_cycle=clock_.now();m.actor.reset();
  throw iris_timing_wait{};
}
void iris_timing_adapter::shuttle_memory_prepare(){
  auto&f=rocket_frontend_;
  for(unsigned h=0;h<2;++h){auto&m=shuttle_memory_[h];const auto tile="shuttle"+std::to_string(h)+"_tile";
    auto set=[&](const char*n,uint64_t value){f.fabric_inputs[f.serial->system_input_index(tile,n)].value=iris::fabric::Bits(value);};
    set("_core_io_dmem_req_valid",m.active&&!m.fence&&!m.accepted&&!m.response&&clock_.now()>=m.issued_cycle+profile_.harts[h].divider);
    set("_core_io_dmem_req_bits_addr",m.address);set("_core_io_dmem_req_bits_cmd",m.store?1:0);set("_core_io_dmem_req_bits_size",3);set("_core_io_dmem_req_bits_tag",m.tag);set("_core_io_dmem_req_bits_signed",1);
    set("_core_io_dmem_s1_paddr",m.previous_address);set("_core_io_dmem_s1_data_data",m.data);set("_core_io_dmem_s1_kill",0);set("_core_io_dmem_s2_kill",0);
  }
}
void iris_timing_adapter::shuttle_memory_observe(){
  auto&f=rocket_frontend_;
  for(unsigned h=0;h<2;++h){auto&m=shuttle_memory_[h];const auto tile="shuttle"+std::to_string(h)+"_tile";
    auto get=[&](const char*n){return f.serial_outputs.system[f.serial->system_output_index(tile,n)].limbs[0];};
    const bool response=get("_dcacheArb_io_requestor_1_resp_valid"),nack=get("_dcacheArb_io_requestor_1_s2_nack");
    const auto valid=f.fabric_inputs[f.serial->system_input_index(tile,"_core_io_dmem_req_valid")].value.limbs[0];
    auto release_discard=[&]{if(!shuttle_discard_outstanding_[h]||!shuttle_discard_actor_[h])throw std::logic_error("IRIS_SHUTTLE_SOURCE_DISCARD_COHORT_OWNER");if(!--shuttle_discard_outstanding_[h]){clock_.finish_physical(*shuttle_discard_actor_[h]);shuttle_discard_actor_[h].reset();}};
    const bool discard_response=response&&get("_dcacheArb_io_requestor_1_resp_bits_has_data")&&get("_dcacheArb_io_requestor_1_resp_bits_tag")==0;
    if(discard_response)release_discard();
    else if(response){if(!m.active||!m.accepted||m.response||m.fence||m.discard||get("_dcacheArb_io_requestor_1_resp_bits_tag")!=m.tag)throw std::runtime_error("IRIS_SHUTTLE_SOURCE_RESPONSE_OWNER_MISMATCH");
      if(bool(get("_dcacheArb_io_requestor_1_resp_bits_has_data"))==m.store)throw std::runtime_error("IRIS_SHUTTLE_SOURCE_RESPONSE_TYPE_MISMATCH");m.value=get("_dcacheArb_io_requestor_1_resp_bits_data");m.response=true;clock_.finish_physical(*m.actor);
    }
    if(nack)throw std::runtime_error("IRIS_SHUTTLE_SOURCE_REPLAY_STAGING_UNQUALIFIED");
    if(m.active&&m.discard&&m.accepted&&!m.response&&clock_.now()==m.accepted_cycle+2*profile_.harts[h].divider){m.value=0;m.response=true;clock_.finish_physical(*m.actor);}
    if(m.active&&m.fence){
      if(!m.accepted&&!shuttle_discard_outstanding_[h]&&get("_dcacheArb_io_requestor_1_ordered")){m.accepted=true;m.accepted_cycle=clock_.now();m.actor=clock_.accept_physical({h,"source-Shuttle-FENCE-after-ordered","shuttle"+std::to_string(h)+".serialized-source-cache",pending_[h]->pc,0,0,{},"source-Core-RRD-FENCE-interlock-plus-serialized-EX-MEM-COM",true});pending_[h]->completion_node=m.actor;}
      if(m.accepted&&clock_.now()==m.accepted_cycle+3*profile_.harts[h].divider){m.response=true;clock_.finish_physical(*m.actor);}
    }
    if(valid&&get("_dcacheArb_io_requestor_1_req_ready")){if(!m.active||m.accepted||m.response||m.fence)throw std::logic_error("IRIS_SHUTTLE_SOURCE_MULTIPLE_REQUEST_OWNER");m.accepted=true;m.accepted_cycle=clock_.now();m.previous_address=m.address;
      m.actor=clock_.accept_physical({h,m.discard?"source-Shuttle-load-x0-to-COM":m.store?"source-Shuttle-serialized-store":"source-Shuttle-serialized-load","shuttle"+std::to_string(h)+".serialized-source-cache",pending_[h]->pc,8,0,{},profile_.serial_system_identity,true});pending_[h]->completion_node=m.actor;
      if(m.discard){if(!shuttle_discard_outstanding_[h])shuttle_discard_actor_[h]=clock_.accept_physical({h,"source-Shuttle-tag0-load-cohort","shuttle"+std::to_string(h)+".discarded-loads-inflight",0,0,0,{},"source-cache-tag0-counted-responses;individual-response-PC-not-observable",false});++shuttle_discard_outstanding_[h];}
    }
  }
}
void iris_timing_adapter::shuttle_memory_complete(){
  for(unsigned h=0;h<2;++h){auto&m=shuttle_memory_[h];if(!m.active||!m.response)continue;
    if(!pending_[h]||!m.actor||cores_[h]->get_state()->pc!=pending_[h]->pc||!cores_[h]->iris_pipeline_context_safe())throw std::logic_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_RETIREMENT_OWNER");
    const auto pc=pending_[h]->pc;shuttle_memory_rows_.push_back({h,m.tag,m.retries,pc,m.address,8,m.issued_cycle,m.accepted_cycle,clock_.now(),m.value,m.store,m.discard,m.fence,*m.actor});
    if(shuttle_owner)throw std::logic_error("nested Shuttle source handler");shuttle_owner=this;completing_=h;completing_node_=m.actor;completion_reads_.clear();const auto before=retired_[h];
    try{cores_[h]->step(1);}catch(...){shuttle_owner=nullptr;completion_reads_.clear();completing_node_.reset();completing_.reset();throw;}
    shuttle_owner=nullptr;finish_counter_reads(h,before);if(retired_[h]!=before+1)throw std::runtime_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_UNEXPECTED_TRAP");frontend_boundary_complete(h,pc,pending_[h]->fetch);
    completing_node_.reset();completing_.reset();pending_[h].reset();blocked_[h]=false;m.active=m.accepted=m.response=false;m.actor.reset();++completions_;
  }
}
reg_t iris_timing_adapter::shuttle_memory_handler(processor_t*p,insn_t insn,reg_t pc){if(!shuttle_owner)throw std::logic_error("Shuttle source handler lacks owner");shuttle_owner->shuttle_memory_retire_effect(p,insn,pc);return pc+insn.length();}
void iris_timing_adapter::shuttle_memory_retire_effect(processor_t*core,insn_t insn,reg_t pc){
  const auto h=core->get_id();const auto&m=shuttle_memory_.at(h);if(completing_!=std::optional<unsigned>(h)||!m.active||!m.response||!pending_[h]||pending_[h]->pc!=pc||pending_[h]->fetch.insn.bits()!=insn.bits())throw std::logic_error("IRIS_SHUTTLE_SOURCE_FUNCTIONAL_PUBLICATION_OWNER");
  if(m.fence||m.discard)return;
  if(m.store)core->iris_fabric_commit_cached_store(m.address,8,m.data);
  else{const auto&parcel=*frontend_[h].conservative;const unsigned rd=(parcel.expanded>>7)&31;iris_definedness::Value<reg_t>v;v.value=m.value;v.known.fill(0xff);core->iris_write_xpr_transport(rd,v);}
}
void iris_timing_adapter::write_shuttle_memory_json(std::ostream&out)const{
  out<<",\"shuttle_source_memory\":{\"implementation\":\"experimental-serialized-LD-SD-plus-source-proven-load-x0-early-COM-and-draining-FENCE\",\"source_identity\":"<<std::quoted(profile_.serial_system_identity)<<",\"hidden_cache_warmup\":false,\"hardware_LSU_overlap_or_throughput_qualified\":false,\"architectural_fault_staging_qualified\":false,\"timing_certified\":false,\"discard_response_ownership\":\"per-hart-tag0-cohort-only-no-individual-response-PC\",\"pending_discard_loads\":["<<shuttle_discard_outstanding_[0]<<","<<shuttle_discard_outstanding_[1]<<"],\"transactions\":[";
  for(unsigned i=0;i<shuttle_memory_rows_.size();++i){const auto&r=shuttle_memory_rows_[i];if(i)out<<',';out<<"{\"hart\":"<<r.hart<<",\"tag\":"<<r.tag<<",\"retries\":"<<r.retries<<",\"pc\":"<<r.pc<<",\"address\":"<<r.address<<",\"bytes\":"<<(r.fence?0:r.bytes)<<",\"discard_x0\":"<<(r.discard?"true":"false")<<",\"fence\":"<<(r.fence?"true":"false")<<",\"store\":"<<(r.store?"true":"false")<<",\"completion_kind\":"<<std::quoted(r.discard?"source-COM-while-data-in-cohort":r.fence?"source-ordered-plus-serialized-pipeline":"owned-cache-response")<<",\"RRD\":"<<r.issue<<",\"physical_acceptance\":"<<r.accepted<<",\"response\":"<<r.response<<",\"value\":"<<((r.store||r.discard||r.fence)?"null":std::to_string(r.value))<<",\"actor\":"<<r.actor<<'}';}out<<"]}";
}
