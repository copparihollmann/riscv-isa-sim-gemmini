#include "saturn_timing_live_bridge.hpp"
#include <algorithm>
#include <limits>
#include <map>
#include <stdexcept>
namespace iris::saturn {
struct SaturnLiveBridge::Impl {
 Profile profile;unsigned hart;LiveBridgeCapability capability;
 SaturnTimingCut unit;SaturnOwnershipLedger ledger;
 std::map<std::string,unsigned>input_index,output_index;
 DefinedReferenceInputs inputs;bool evaluated=false,poisoned=false;
 bool admitted_commands_never_sample_frs1=false;
 std::optional<std::uint64_t> previous_tick;
 Impl(Profile p,unsigned h,std::uint32_t seed,LiveBridgeCapability c):profile(p),hart(h),capability(std::move(c)),unit(p,h,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness),ledger(p,h,unit.activity_fields(p),unit.ownership_fields(p)){
  if(capability.manifest_identity.empty()||capability.instructions.empty())throw std::invalid_argument("Live Saturn requires explicit instruction capability provenance");
  const auto ownership=unit.ownership_fields(p);if(std::none_of(ownership.begin(),ownership.end(),[](const Field&f){return f.name.starts_with("vu.vrf.vrf.vrf_0.write_bits_data");}))throw std::invalid_argument("Live Saturn requires source numeric write projection for staged intent validation");
  for(const auto&pattern:capability.instructions)if(!pattern.mask||(pattern.value&~pattern.mask))throw std::invalid_argument("Malformed live Saturn instruction pattern");
  admitted_commands_never_sample_frs1=std::all_of(capability.instructions.begin(),capability.instructions.end(),[](const auto&p){const auto f3=(p.value>>12)&7;return p.mask==~0u&&f3!=1&&f3!=5;});
  for(unsigned n=0;n<unit.input_fields(p).size();++n)input_index.emplace(std::string(unit.input_fields(p)[n].name),n);
  for(unsigned n=0;n<unit.output_fields(p).size();++n)output_index.emplace(std::string(unit.output_fields(p)[n].name),n);
 }
 void healthy()const{if(poisoned)throw std::runtime_error("Live Saturn bridge is poisoned after a rejected commit");}
};
SaturnLiveBridge::SaturnLiveBridge(Profile p,unsigned h,std::uint32_t seed,LiveBridgeCapability c):impl_(std::make_unique<Impl>(p,h,seed,std::move(c))){}
SaturnLiveBridge::~SaturnLiveBridge()=default;
SaturnLiveBridge::SaturnLiveBridge(SaturnLiveBridge&&)noexcept=default;
SaturnLiveBridge&SaturnLiveBridge::operator=(SaturnLiveBridge&&)noexcept=default;
void SaturnLiveBridge::evaluate(const DefinedReferenceInputs&in){
 auto&s=*impl_;s.healthy();s.evaluated=false;const auto fields=s.unit.input_fields(s.profile);
 if(in.values.words.size()!=fields.size()||in.known_bits.size()!=fields.size())throw std::invalid_argument("Live Saturn physical input/knownness shape mismatch");
 const bool qualified=s.capability.inactive_payload==InactiveInputConvention::SourceQualifiedInactivePayload;
 const auto ex_name=s.profile==Profile::Compute128?"io_ex_valid":"io_core_ex_valid";
 const auto ex_at=s.input_index.at(ex_name),reset_at=s.input_index.at("reset");
 if(!(in.known_bits.at(ex_at)&1)||!(in.known_bits.at(reset_at)&1))throw std::invalid_argument("Live Saturn reset and EX valid must be defined source controls");
 const bool ex_valid=in.values.words.at(ex_at),reset=in.values.words.at(reset_at);
 std::uint32_t instruction=0;if(ex_valid){const auto at=s.input_index.at(s.profile==Profile::Compute128?"io_ex_uop_inst":"io_core_ex_inst");if((in.known_bits.at(at)&0xffffffffULL)!=0xffffffffULL)throw std::invalid_argument("Active source instruction must be defined before operand qualification");instruction=in.values.words.at(at);}
 const auto opcode=instruction&0x7f,funct3=(instruction>>12)&7;const bool vector_arithmetic=ex_valid&&(opcode==0x77||(opcode==0x57&&funct3!=7));
 DefinedReferenceInputs effective=in;bool unknown_rounding=false;
 for(unsigned n=0;n<fields.size();++n){
  const auto width=fields[n].word_width;const auto bits=width==64?~0ULL:(1ULL<<width)-1;const std::string name(fields[n].name);
  if(in.values.words[n]&~bits)throw std::invalid_argument("Live Saturn physical input exceeds its source width: "+name);
  if((in.known_bits[n]&bits)==bits)continue;
  const bool ex_payload=name.starts_with("io_ex_uop_")||name.starts_with("io_ex_vconfig_")||name=="io_ex_vstart"||(name.starts_with("io_core_ex_")&&name!="io_core_ex_valid");
  const bool rounding=name==(s.profile==Profile::Compute128?"io_com_frm":"io_core_wb_frm")||name==(s.profile==Profile::Compute128?"io_com_vxrm":"io_core_wb_vxrm");
  // Saved EarlyVectorDecode.read_rs1/read_rs2: arithmetic uses XPR rs1 only
  // for funct3 4/6 and never XPR rs2. Do not initialize unused register bits.
  const bool unused_rs1=vector_arithmetic&&funct3!=4&&funct3!=6&&name==(s.profile==Profile::Compute128?"io_ex_uop_rs1_data":"io_core_ex_rs1");
  const bool unused_rs2=vector_arithmetic&&name==(s.profile==Profile::Compute128?"io_ex_uop_rs2_data":"io_core_ex_rs2");
  const bool unused_frs1=s.admitted_commands_never_sample_frs1&&name==(s.profile==Profile::Compute128?"io_mem_frs1":"io_core_mem_frs1");
  if(!qualified||!(ex_payload&&!ex_valid||rounding||unused_rs1||unused_rs2||unused_frs1))throw std::invalid_argument("Live Saturn physical input is undefined: "+name);
  // This is only an inactive-port concretization. The original known_bits
  // are retained and no architectural state becomes initialized by it.
  effective.values.words[n]&=in.known_bits[n];unknown_rounding|=rounding;
 }
 s.unit.evaluate(effective.values);
 if(unknown_rounding&&!reset){
  const auto activity=s.unit.sample_activity();const auto names=s.unit.activity_fields(s.profile);bool found_s2=false,found_ifc=false,consumed=false;
  for(unsigned n=0;n<names.size();++n){if(names[n].name=="vfu.pfc.io_s2_inst_valid"){found_s2=true;consumed|=bool(activity.words[n]);}if(names[n].name=="vfu.ifc.io_busy"){found_ifc=true;consumed|=bool(activity.words[n]);}}
  if(!found_s2||!found_ifc||consumed){s.poisoned=true;throw std::invalid_argument("Undefined late rounding payload with active source frontend command");}
 }
 s.inputs=std::move(effective);s.evaluated=true;
}
ReferenceOutputs SaturnLiveBridge::sample()const{auto&s=*impl_;s.healthy();if(!s.evaluated)throw std::logic_error("Live Saturn sample requires same-edge evaluation");return s.unit.sample();}
std::vector<OwnershipEvent> SaturnLiveBridge::commit(std::uint64_t tick,std::optional<CallerCommand>caller){auto&s=*impl_;s.healthy();if(!s.evaluated)throw std::logic_error("Live Saturn commit requires same-edge evaluation");try{
 if(s.previous_tick&&tick<=*s.previous_tick)throw std::invalid_argument("Live Saturn source edge must have a strictly increasing global timestamp");
 const auto o=s.unit.sample();const auto a=s.unit.sample_activity(tick),x=s.unit.sample_ownership(tick);
 const auto in=[&](const std::string&n){return s.inputs.values.words.at(s.input_index.at(n));};
 const auto out=[&](const std::string&n){const auto at=s.output_index.find(n);return at==s.output_index.end()?0ULL:o.words.at(at->second);};
 if(!in("reset")){
  for(const auto&name:{"auto_atl_out_a_valid","io_dmem_req_valid","io_fp_req_valid","io_tlb_req_valid"})if(out(name))throw std::runtime_error("Live Saturn finite capability has no physical service for "+std::string(name));
  for(const auto&name:{"auto_atl_out_d_valid","io_dmem_resp_valid","io_fp_resp_valid"})if(s.input_index.contains(name)&&in(name))throw std::runtime_error("Live Saturn finite capability rejects unsolicited external response "+std::string(name));
  unsigned accept=0;const auto fields=s.unit.activity_fields(s.profile);while(accept<fields.size()&&fields[accept].name!="vfu.pfc.io_s0_in_valid")++accept;if(accept==fields.size())throw std::runtime_error("Live Saturn source S0 metadata is unresolved");
  if(a.words.at(accept)){const auto raw=std::uint32_t(in(s.profile==Profile::Compute128?"io_ex_uop_inst":"io_core_ex_inst"));if((raw&0x7f)==7||(raw&0x7f)==39)throw std::runtime_error("Live Saturn finite capability refuses vector memory before source acceptance");bool supported=false;for(const auto&pattern:s.capability.instructions)supported|=(raw&pattern.mask)==pattern.value;if(!supported)throw std::runtime_error("Live Saturn instruction is absent from the explicit source-qualified capability manifest");if(!caller)throw std::runtime_error("Live Saturn native command requires exact accepted EX caller metadata");}
 }
 auto events=s.ledger.observe(s.inputs.values,o,a,x,caller);s.unit.commit();s.previous_tick=tick;s.evaluated=false;return events;
 }catch(...){s.poisoned=true;throw;}}
std::uint64_t SaturnLiveBridge::edges()const{return impl_->unit.edges();}
PendingOwnership SaturnLiveBridge::pending()const{return impl_->ledger.pending();}
std::vector<OwnedCommand> SaturnLiveBridge::live_commands()const{return impl_->ledger.live_commands();}
const char*SaturnLiveBridge::component_source_identity(){return SaturnTimingCut::source_identity();}
}
