// Source scalar Rocket/cache staging, isolated experimental scope.
#include "iris_timing_adapter.h"
#include "processor.h"
#include <algorithm>
#include <cstring>
namespace {thread_local iris_timing_adapter* memory_handler_adapter=nullptr;}
bool iris_timing_adapter::rocket_memory_decode(const iris::shuttle::Uop&u)const{
  if(!profile_.rocket_scalar_memory||!u.control_verified||u.exception||!u.has(iris::shuttle::MEM))return false;
  const auto op=u.expanded&127,f=(u.expanded>>12)&7;return (op==3&&f<=6)||(op==0x23&&f<=3);
}
void iris_timing_adapter::rocket_memory_prepare(){
  if(!profile_.rocket_scalar_memory)return;auto&f=rocket_frontend_;auto&p=pure_[2];const auto now=clock_.now(),d=profile_.harts[2].divider;
  const auto*architectural=cores_[2]->get_state();
  if(architectural->prv!=PRV_M||architectural->v||architectural->debug_mode||(architectural->mstatus->read()&MSTATUS_MPRV))throw std::runtime_error("IRIS_ROCKET_SOURCE_TRANSLATED_DATA_PRIVILEGE_UNMODELED");
  f.physical_ex.reset();f.physical_mem.reset();
  auto set=[&](std::string_view name,uint64_t value){auto fields=f.fabric->arbiter_input_fields();for(unsigned i=0;i<fields.size();++i)if(fields[i].name==name){f.arbiter_inputs[i].value=iris::fabric::Bits(value);return;}throw std::logic_error("source scalar arbiter pin missing");};
  set("io_requestor_1_req_valid",0);set("io_requestor_1_s1_kill",1);
  // At most one new Rocket ID token exists per core edge and there are
  // exactly EX/MEM/WB source stages; older graph history is never scanned.
  for(size_t id=p.instructions.size()>3?p.instructions.size()-3:0;id<p.instructions.size();++id){auto&row=p.instructions[id];
    if(row.source_memory&&row.rrd+d==now&&!row.squashed){
      if(f.physical_ex)throw std::logic_error("multiple source scalar EX candidates");f.physical_ex=id;
      if(!row.memory_address_ready){if(!p.values->operands_ready(*row.memory_operands))continue;const auto values=p.values->read(*row.memory_operands);if(!values[0]||(row.memory_store&&!values[1]))throw std::runtime_error("IRIS_ROCKET_SOURCE_MEMORY_UNKNOWN_OPERANDS");
        const auto x=row.uop.expanded;const auto imm=row.memory_store?((x>>25)<<5)|((x>>7)&31):x>>20;
        row.memory_address=*values[0]+iris::frontend::PureAluValue::sext(imm,12);row.memory_data=values[1].value_or(0);row.memory_address_ready=true;row.memory_operands.reset();
        if(row.memory_address>>35)throw std::runtime_error("IRIS_ROCKET_SOURCE_MEMORY_ADDRESS_WIDTH");
        if((row.memory_address>=0x70000000&&row.memory_address<0x70040000)||(row.memory_address>=0x580000000ULL&&row.memory_address<0x580020000ULL))throw std::runtime_error("IRIS_ROCKET_SOURCE_EXTERNAL_TCM_OR_SCRATCH_SERVICE_UNMODELED");
        if(!iris_board::region_for(row.memory_address,1u<<row.memory_size))throw std::runtime_error("IRIS_ROCKET_SOURCE_UNMAPPED_MEMORY_TRAP_NOT_INTEGRATED");
      }
      set("io_requestor_1_req_valid",1);set("io_requestor_1_req_bits_addr",row.memory_address);set("io_requestor_1_req_bits_tag",(row.memory_store?0:row.uop.rd)<<1);set("io_requestor_1_req_bits_cmd",row.memory_store?1:0);set("io_requestor_1_req_bits_size",row.memory_size);set("io_requestor_1_req_bits_signed",!(row.uop.expanded&(1<<14)));set("io_requestor_1_req_bits_dprv",3);
    }
    if(row.source_memory&&row.rrd+2*d==now){
      if(f.physical_mem)throw std::logic_error("multiple source scalar MEM candidates");f.physical_mem=id;
      uint64_t data=row.memory_data;const unsigned bits=8u<<row.memory_size;if(bits<64){data&=(uint64_t(1)<<bits)-1;for(unsigned n=bits;n<64;n+=bits)data|=data<<bits;}
      iris::fabric::Bits wide;wide.limbs.fill(data);auto fields=f.fabric->arbiter_input_fields();for(unsigned i=0;i<fields.size();++i)if(fields[i].name=="io_requestor_1_s1_data_data")f.arbiter_inputs[i].value=wide;
      set("io_requestor_1_s1_kill",row.squashed||row.memory_replay);
    }
  }
}
void iris_timing_adapter::rocket_memory_revise_kills(){
  if(!profile_.rocket_scalar_memory)return;auto&f=rocket_frontend_;if(!f.physical_mem)return;const auto&row=pure_[2].instructions.at(*f.physical_mem);
  auto fields=f.fabric->arbiter_input_fields();for(unsigned i=0;i<fields.size();++i)if(fields[i].name=="io_requestor_1_s1_kill")f.arbiter_inputs[i].value=iris::fabric::Bits(row.squashed||row.memory_replay);
}
void iris_timing_adapter::rocket_memory_complete_ex(size_t id){
  auto&p=pure_[2];auto&row=p.instructions.at(id);if(row.squashed||row.source_memory||row.memory_replay)return;
  if(row.uop.cfi()){
    if(!row.uop.has(iris::shuttle::JALR)){row.private_value=row.uop.has(iris::shuttle::WXD)?row.pc+row.fetch.insn.length():0;p.values->complete_external(id,row.private_value);row.private_value_ready=true;}
  }else{row.private_value=p.values->complete(id);row.private_value_ready=true;}
}
void iris_timing_adapter::rocket_memory_replay_wb(size_t id){
  auto&p=pure_[2];auto&row=p.instructions.at(id);auto&f=rocket_frontend_;
  if(id!=p.next_commit||row.retired)throw std::logic_error("source memory replay WB ordering");
  frontend_squash(2,id,false);p.values->annul_replayed(id);row.memory_replay=true;row.released=true;
  if(p.packets.empty()||p.packets.front().id!=row.packet)throw std::logic_error("source memory replay packet ordering");p.packets.pop_front();++p.next_commit;++completions_;++f.memory_replays;
  while(p.next_commit<p.instructions.size()&&p.instructions[p.next_commit].squashed)++p.next_commit;
  while(p.first_live<p.instructions.size()&&p.instructions[p.first_live].released)++p.first_live;
  p.frontier=row.pc;rocket_frontend_redirect(row.pc);
}
void iris_timing_adapter::rocket_memory_after_prepare(){
  auto&f=rocket_frontend_;if(!f.prepared)return;auto&p=pure_[2];const auto now=clock_.now(),d=profile_.harts[2].divider;
  auto get=[&](std::string_view name){auto fields=f.fabric->arbiter_output_fields();for(unsigned i=0;i<fields.size();++i)if(fields[i].name==name)return f.fabric_outputs.arbiter[i].limbs[0];throw std::logic_error("source scalar arbiter response missing");};
  f.cache_grant=get("io_requestor_1_perf_grant");
  const bool resp=get("io_requestor_1_resp_valid"),data=resp&&get("io_requestor_1_resp_bits_has_data"),late=data&&get("io_requestor_1_resp_bits_replay");const auto tag=get("io_requestor_1_resp_bits_tag");
  // Source MEM-load bypass is a same-edge combinational data dependency:
  // resolve old WB response into the private value before finalizing a
  // dependent EX address/store value. No architectural step occurs here.
  if(data&&!late)for(auto id:f.pending_wb){auto&row=p.instructions.at(id);if(!row.squashed&&row.source_memory&&!row.memory_store&&!row.memory_replay&&tag==(row.uop.rd<<1)&&!row.private_value_ready){row.private_value=get("io_requestor_1_resp_bits_data");row.private_value_ready=true;p.values->complete_external(id,row.private_value);}}
  if(f.physical_ex&&!p.instructions.at(*f.physical_ex).memory_address_ready){
    const auto before=f.fabric_outputs.arbiter;rocket_memory_prepare();
    if(f.physical_ex&&!p.instructions.at(*f.physical_ex).memory_address_ready)throw std::runtime_error("IRIS_ROCKET_SOURCE_DEPENDENT_MEMORY_MISS_ADDRESS_KNOWNNESS_UNMODELED");
    rocket_fabric_evaluate();
    for(const auto name:{"io_requestor_1_resp_valid","io_requestor_1_resp_bits_data","io_requestor_1_resp_bits_tag","io_requestor_1_resp_bits_has_data","io_requestor_1_resp_bits_replay","io_requestor_1_s2_nack"}){auto fields=f.fabric->arbiter_output_fields();for(unsigned i=0;i<fields.size();++i)if(fields[i].name==name&&before[i]!=f.fabric_outputs.arbiter[i])throw std::runtime_error("IRIS_ROCKET_SOURCE_MEMORY_COMBINATIONAL_RESPONSE_UNSTABLE");}
  }
  if(late&&!(tag&1)){
    const auto rd=(tag>>1)&31;if(!rd||!f.pending_loads[rd])throw std::runtime_error("IRIS_ROCKET_SOURCE_LATE_RF_OWNER_MISSING");
    const auto id=*f.pending_loads[rd];auto&row=p.instructions.at(id);const uint64_t value=get("io_requestor_1_resp_bits_data");
    p.values->complete_retired_external(rd,id,value);iris_definedness::Value<reg_t>v;v.value=value;v.known.fill(0xff);cores_[2]->iris_write_xpr_transport(rd,v);row.private_value=value;row.private_value_ready=true;row.memory_pending=false;
    if(!row.memory_actor)throw std::logic_error("late response without accepted cache request");clock_.finish_physical(*row.memory_actor);f.pending_loads[rd].reset();++f.late_rf_writes;
  }
  // Source replay_next reserves the next RF write port by replaying a
  // current MEM integer writer. This is not a guessed cache penalty.
  if(get("io_requestor_1_replay_next"))for(size_t id=p.first_live;id<p.instructions.size();++id){auto&row=p.instructions[id];if(!row.squashed&&row.rrd+2*d==now&&row.uop.has(iris::shuttle::WXD))row.memory_replay=true;}
  auto wb=std::move(f.pending_wb);f.pending_wb.clear();
  for(auto id:wb){auto&row=p.instructions.at(id);if(row.squashed)continue;
    if(row.source_memory){
      for(const auto suffix:{"ma_ld","ma_st","pf_ld","pf_st","ae_ld","ae_st"})if(get(std::string("io_requestor_1_s2_xcpt_")+suffix))throw std::runtime_error("IRIS_ROCKET_SOURCE_CACHE_FAULT_ARCHITECTURAL_TRAP_NOT_INTEGRATED");
      row.memory_replay|=get("io_requestor_1_s2_nack");
      if(row.memory_replay){if(row.memory_actor&&!clock_.nodes().at(*row.memory_actor).completed)clock_.finish_physical(*row.memory_actor);rocket_memory_replay_wb(id);continue;}
      if(!row.memory_accepted)throw std::logic_error("source load/store reaches valid WB without cache acceptance");
      if(row.memory_store){p.values->complete_external(id,0);row.private_value=0;row.private_value_ready=true;clock_.finish_physical(*row.memory_actor);}
      else if(data&&!late){if(tag!=(row.uop.rd<<1))throw std::runtime_error("IRIS_ROCKET_SOURCE_FAST_LOAD_RESPONSE_OWNER");if(!row.private_value_ready){row.private_value=get("io_requestor_1_resp_bits_data");row.private_value_ready=true;p.values->complete_external(id,row.private_value);}clock_.finish_physical(*row.memory_actor);}
      else{if(resp)throw std::runtime_error("IRIS_ROCKET_SOURCE_WB_LOAD_RESPONSE_COLLISION");row.memory_pending=true;f.pending_loads[row.uop.rd]=id;++f.early_load_retirements;
        for(size_t younger=id+1;younger<p.instructions.size();++younger){auto&next=p.instructions[younger];if(!next.squashed&&next.rrd+d==now&&next.memory_load_use)next.memory_replay=true;}
      }
      row.fetch.func=&iris_timing_adapter::rocket_memory_handler;
    }else if(row.memory_replay){rocket_memory_replay_wb(id);continue;}
    if(memory_handler_adapter)throw std::logic_error("nested source scalar memory handler");memory_handler_adapter=this;
    try{pure_commit(2,id);}catch(...){memory_handler_adapter=nullptr;throw;}memory_handler_adapter=nullptr;
  }
  auto ex=std::move(f.pending_ex);f.pending_ex.clear();for(auto id:ex)rocket_memory_complete_ex(id);
}
void iris_timing_adapter::rocket_memory_commit_physical(){
  if(!profile_.rocket_scalar_memory)return;auto&f=rocket_frontend_;auto&p=pure_[2];
  auto get=[&](std::string_view name){auto fields=f.fabric->arbiter_output_fields();for(unsigned i=0;i<fields.size();++i)if(fields[i].name==name)return f.fabric_outputs.arbiter[i].limbs[0];throw std::logic_error("source scalar arbiter output missing");};
  if(f.physical_ex){auto&row=p.instructions.at(*f.physical_ex);if(get("io_requestor_1_req_ready")){row.memory_accepted=true;row.memory_actor=clock_.accept_physical({2,row.memory_store?"source-scalar-cache-store":"source-scalar-cache-load","rocket2.source-scalar-cache",row.pc,uint64_t(1)<<row.memory_size,0,{},"saved-RocketCore-HellaArbiter-Dcache6227466f",true});}else row.memory_replay=true;}
  if(f.physical_mem){auto&row=p.instructions.at(*f.physical_mem);if((row.squashed||row.memory_replay)&&row.memory_actor&&!clock_.nodes().at(*row.memory_actor).completed){clock_.finish_physical(*row.memory_actor);row.memory_killed=true;}}
  f.cache_blocked=!get("io_requestor_1_req_ready")&&!get("io_requestor_1_perf_grant")&&(f.cache_blocked||f.physical_ex.has_value()||get("io_requestor_1_s2_nack"));
}
reg_t iris_timing_adapter::rocket_memory_handler(processor_t*p,insn_t insn,reg_t pc){
  if(!memory_handler_adapter)throw std::logic_error("source scalar memory handler without owning WB");memory_handler_adapter->rocket_memory_retire_effect(p,pc,insn);return pc+insn.length();
}
void iris_timing_adapter::rocket_memory_retire_effect(processor_t*core,reg_t pc,insn_t insn){
  if(!completing_pure_||completing_!=std::optional<unsigned>(2))throw std::logic_error("source scalar memory architectural owner missing");const auto&row=pure_[2].instructions.at(*completing_pure_);
  auto original=row.fetch.insn;if(!row.source_memory||row.pc!=pc||original.bits()!=insn.bits())throw std::logic_error("source scalar memory handler identity mismatch");
  if(row.memory_store){if(row.memory_address>=0x80000000&&row.memory_address<0x180000000ULL)core->iris_fabric_commit_cached_store(row.memory_address,1u<<row.memory_size,row.memory_data);}
  else{iris_definedness::Value<reg_t> v;v.value=row.private_value.value_or(0);if(row.private_value_ready)v.known.fill(0xff);core->iris_write_xpr_transport(row.uop.rd,v);}
}
