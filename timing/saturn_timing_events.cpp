#include "saturn_timing_events.hpp"
#include <stdexcept>
namespace iris::saturn {
std::string_view PhysicalEventLedger::name(EventKind k){switch(k){
#define N(a,b) case EventKind::a:return b;
 N(EXCandidate,"EX_candidate") N(EXFire,"EX_fire") N(MEMKill,"MEM_kill") N(COMFrontToken,"COM_front_token") N(COMRetireLate,"COM_retire_late") N(COMInternalReplay,"COM_internal_replay") N(COMException,"COM_exception") N(WBReplay,"WB_replay") N(WBFrontRetire,"WB_front_retire") N(WBException,"WB_exception") N(ScalarResponse,"scalar_response") N(FFlagsUpdate,"fflags_update") N(TLA,"TL_A_beat") N(TLD,"TL_D_beat") N(HellaRequest,"Hella_A_request") N(SharedFPURequest,"shared_FPU_request") N(SharedFPUResponse,"shared_FPU_response")
#undef N
 }throw std::invalid_argument("Unknown Saturn event");}
PhysicalEventLedger::PhysicalEventLedger(Profile p,unsigned h):profile_(p),hart_(h){
 SaturnTimingCut::source_clock_id(p,h);unsigned n=0;for(auto f:SaturnTimingCut::input_fields(p))input_.emplace(f.name,n++);n=0;for(auto f:SaturnTimingCut::output_fields(p))output_.emplace(f.name,n++);
}
std::uint64_t PhysicalEventLedger::get(const std::map<std::string,unsigned>&m,const std::vector<std::uint64_t>&v,const std::string&n)const{auto at=m.find(n);if(at==m.end())throw std::invalid_argument("Missing physical source field "+n);return v.at(at->second);}
std::vector<PhysicalEvent> PhysicalEventLedger::observe(const ReferenceInputs&i,const ReferenceOutputs&o,std::optional<std::uint64_t>epoch){
 if(i.words.size()!=input_.size()||o.words.size()!=output_.size())throw std::invalid_argument("Incomplete Saturn event frame");
 for(auto direction:{false,true}){auto fields=direction?SaturnTimingCut::output_fields(profile_):SaturnTimingCut::input_fields(profile_);const auto&words=direction?o.words:i.words;for(unsigned n=0;n<fields.size();++n)if(fields[n].word_width<64&&words[n]>=(1ULL<<fields[n].word_width))throw std::invalid_argument("Overwide physical Saturn event field");}
 auto I=[&](const std::string&n){return get(input_,i.words,n);};auto O=[&](const std::string&n){return get(output_,o.words,n);};std::vector<PhysicalEvent> result;
 auto event=[&](EventKind k)->PhysicalEvent&{result.push_back(PhysicalEvent{k,hart_,edge_});++counts_[std::string(name(k))];return result.back();};
 if(I("reset")){reset_seen_=true;s1_.reset();s2_.reset();pending_.clear();++edge_;return result;}
 if(!reset_seen_)throw std::invalid_argument("Actual-reset event projection requires reset history");
 const bool rocket=profile_==Profile::Rocket256;const std::string core=rocket?"io_core_":"io_";const unsigned bus=rocket?8:32;
 auto A=[&]{
  const auto source=unsigned(O("auto_atl_out_a_bits_source")),opcode=unsigned(O("auto_atl_out_a_bits_opcode")),size=unsigned(O("auto_atl_out_a_bits_size"));const auto address=O("auto_atl_out_a_bits_address");
  if((opcode!=0&&opcode!=1&&opcode!=4)||size>7)throw std::invalid_argument("Unqualified physical TL request");
  const unsigned beats=((1u<<size)+bus-1)/bus;auto it=pending_.find(source);
  if(it==pending_.end())it=pending_.emplace(source,Owner{opcode,size,0,0,opcode==4?1:beats,opcode==4?beats:1,address,edge_}).first;
  auto& owner=it->second;if(owner.opcode!=opcode||owner.size!=size||owner.address!=address||owner.a_seen>=owner.a_total)throw std::invalid_argument("TL source reused before completion");
  auto&e=event(EventKind::TLA);e.source=source;e.opcode=opcode;e.size=size;e.address=address;e.request_edge=owner.edge;e.beat=++owner.a_seen;e.total_beats=owner.a_total;e.byte_mask=O("auto_atl_out_a_bits_mask");
  if(opcode==0||opcode==1)for(unsigned w=0;w<bus/8;++w){e.data[w]=O("auto_atl_out_a_bits_data"+(rocket?std::string():"_"+std::to_string(w)));for(unsigned b=0;b<8;++b)if(e.byte_mask&(1ULL<<(8*w+b)))e.data_defined_mask[w]|=255ULL<<(8*b);}
 };
 auto D=[&]{
  const auto source=unsigned(I("auto_atl_out_d_bits_source")),opcode=unsigned(I("auto_atl_out_d_bits_opcode")),size=unsigned(I("auto_atl_out_d_bits_size"));auto it=pending_.find(source);
  if(it==pending_.end())throw std::invalid_argument("D beat has no accepted source owner");auto& owner=it->second;
  if(size!=owner.size||opcode!=(owner.opcode==4?1u:0u)||owner.d_seen>=owner.d_total)throw std::invalid_argument("TL D type/size/count mismatch");
  auto&e=event(EventKind::TLD);e.source=source;e.opcode=opcode;e.size=size;e.address=owner.address;e.request_edge=owner.edge;e.beat=++owner.d_seen;e.total_beats=owner.d_total;
  if(opcode==1){const unsigned bytes=1u<<owner.size;const unsigned offset=bytes<bus?owner.address&(bus-1):0;
   for(unsigned w=0;w<bus/8;++w){e.data[w]=I("auto_atl_out_d_bits_data"+(rocket?std::string():"_"+std::to_string(w)));for(unsigned b=0;b<8;++b)if(bytes>=bus||(8*w+b>=offset&&8*w+b<offset+bytes))e.data_defined_mask[w]|=255ULL<<(8*b);}}
  if(owner.d_seen==owner.d_total)pending_.erase(it);
 };
 const bool afire=O("auto_atl_out_a_valid")&&I("auto_atl_out_a_ready"),dfire=I("auto_atl_out_d_valid")&&O("auto_atl_out_d_ready");
 const bool old_d=dfire&&pending_.contains(unsigned(I("auto_atl_out_d_bits_source")));
 // Prior response completes before same-source reuse. A simultaneous new A/D
 // may establish and release an owner without inventing an extra source edge.
 if(old_d)D();if(afire)A();if(dfire&&!old_d)D();
 std::optional<CommandIdentity> cmd;const bool valid=I(core+"ex_valid"),ready=O(core+"ex_ready");
 if(valid&&ready){
  CommandIdentity c;c.hart=hart_;c.sequence=next_id_++;c.pc=I(rocket?"io_core_ex_pc":"io_ex_uop_pc");c.instruction=I(rocket?"io_core_ex_inst":"io_ex_uop_inst");c.ex_fired=rocket||I("io_ex_fire");c.caller_config_epoch=epoch;
  const std::string prefix=core+"ex_vconfig_";auto&v=c.config;v.vl=I(prefix+"vl");v.vstart=I(core+"ex_vstart");v.illegal=I(prefix+"vtype_vill");v.sew=I(prefix+"vtype_vsew");v.lmul_negative=I(prefix+"vtype_vlmul_sign");v.lmul_magnitude=I(prefix+"vtype_vlmul_mag");v.mask_agnostic=I(prefix+"vtype_vma");v.tail_agnostic=I(prefix+"vtype_vta");v.alternate_format=I(prefix+"vtype_altfmt");v.tile_widen=I(prefix+"vtype_vtwiden");if(!rocket){v.tile_rows=I(prefix+"vtype_tm");v.tile_k=I(prefix+"vtype_tk");}
  cmd=c;event(EventKind::EXCandidate).command=c;if(c.ex_fired)event(EventKind::EXFire).command=c;
 }
 const bool kill=rocket?I("io_core_killm"):(I("io_mem_kill")||(s1_&&!s1_->ex_fired));if(s1_&&kill)event(EventKind::MEMKill).command=s1_;if(s2_)event(EventKind::COMFrontToken).command=s2_;
 auto control=[&](const char*field,EventKind k,const char*pc,const char*raw){if(O(field)){auto&e=event(k);e.pc=O(pc);if(raw)e.instruction=O(raw);}};
 if(rocket){control("io_core_wb_replay",EventKind::WBReplay,"io_core_wb_pc","io_core_wb_inst");control("io_core_wb_retire",EventKind::WBFrontRetire,"io_core_wb_pc","io_core_wb_inst");control("io_core_wb_xcpt",EventKind::WBException,"io_core_wb_pc","io_core_wb_inst");
  if(O("io_dmem_req_valid")&&I("io_dmem_req_ready")){auto&e=event(EventKind::HellaRequest);e.opcode=O("io_dmem_req_bits_cmd");e.source=O("io_dmem_req_bits_tag");}
  if(O("io_fp_req_valid")&&I("io_fp_req_ready")){auto&e=event(EventKind::SharedFPURequest);e.rounding_mode=O("io_fp_req_bits_rm");e.type_in=O("io_fp_req_bits_typeTagIn");e.type_out=O("io_fp_req_bits_typeTagOut");e.third_operand=O("io_fp_req_bits_ren3");e.swap23=O("io_fp_req_bits_swap23");e.opcode=O("io_fp_req_bits_fmaCmd");for(unsigned operand=0;operand<3;++operand)for(unsigned word=0;word<2;++word)e.recoded_operands[operand][word]=O("io_fp_req_bits_in"+std::to_string(operand+1)+"_"+std::to_string(word));}
  if(I("io_fp_resp_valid")){auto&e=event(EventKind::SharedFPUResponse);e.data[0]=I("io_fp_resp_bits_data_0");e.data[1]=I("io_fp_resp_bits_data_1");e.data_defined_mask[0]=~0ULL;e.data_defined_mask[1]=1;}
 }else{control("io_com_retire_late",EventKind::COMRetireLate,"io_com_pc",nullptr);control("io_com_internal_replay",EventKind::COMInternalReplay,"io_com_pc",nullptr);control("io_com_xcpt",EventKind::COMException,"io_com_pc",nullptr);}
 if(O(core+"resp_valid")&&I(core+"resp_ready")){auto&e=event(EventKind::ScalarResponse);e.rd=O(core+"resp_bits_rd");e.floating=O(core+"resp_bits_fp");e.value=O(core+"resp_bits_data");}
 if(O(core+"set_fflags_valid"))event(EventKind::FFlagsUpdate).value=O(core+"set_fflags_bits");
 s2_=kill?std::optional<CommandIdentity>{}:s1_;s1_=cmd;++edge_;return result;
}
}
