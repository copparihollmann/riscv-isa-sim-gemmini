#include "saturn_timing_ownership.hpp"
#include <array>
#include <cstdint>
#include <iostream>
#include <deque>
#include <set>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
using namespace iris::saturn;
void require(bool b,const char*m){if(!b)throw std::runtime_error(m);}
uint8_t pattern(unsigned i){return uint8_t(0x59+13*i);}
int main(int argc,char**argv){try{
 require(argc==3,"VL seed");const unsigned vl=std::stoul(argv[1]),seed=std::stoul(argv[2]);require(vl&&vl<=32,"finite VL1..32");
 const auto profile=Profile::Compute128;SaturnTimingCut unit(profile,0,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);SaturnOwnershipLedger ledger(profile,0,SaturnTimingCut::activity_fields(profile),SaturnTimingCut::ownership_fields(profile));
 ReferenceInputs in;in.words.resize(SaturnTimingCut::input_fields(profile).size());std::map<std::string,unsigned> ii,oo;
 for(unsigned i=0;i<in.words.size();++i)ii.emplace(SaturnTimingCut::input_fields(profile)[i].name,i);
 for(unsigned i=0;i<SaturnTimingCut::output_fields(profile).size();++i)oo.emplace(SaturnTimingCut::output_fields(profile)[i].name,i);
 auto set=[&](const std::string&n,uint64_t v){in.words.at(ii.at(n))=v;};
 set("io_status_prv",3);set("io_resp_ready",1);set("io_mem_tlb_req_ready",1);set("auto_atl_out_a_ready",1);
 set("io_ex_vconfig_vl",vl);set("io_ex_vconfig_vtype_vma",1);set("io_ex_vconfig_vtype_vta",1);set("io_ex_vconfig_vtype_vtwiden",3);set("io_ex_vconfig_vtype_tm",32);set("io_ex_vconfig_vtype_tk",4);
 constexpr uint64_t address=0x80010000,pc=0x80001000;constexpr uint32_t raw=0x02050407; // vle8.v v8,(a0), vm=1,nf=1
 set("io_ex_uop_inst",raw);set("io_ex_uop_pc",pc);set("io_ex_uop_rs1_data",address);
 std::array<uint8_t,1024> vrf{},known{};bool accepted=false,retired=false,request=false,replied=false;unsigned ex=0,front=0,aedge=0,dedge=0,lastwrite=0,writes=0,hold=0;struct Reply{unsigned source,size;uint64_t address;};std::deque<Reply> replies;std::set<unsigned> owned;unsigned requests=0,responses=0;bool done=false;
 for(unsigned edge=0;edge<512;++edge){
  set("reset",edge<2);set("io_ex_valid",edge>=80&&!accepted);set("io_ex_fire",0);
  set("io_mem_tlb_resp_paddr",address);set("auto_atl_out_d_valid",!replies.empty()&&edge>=aedge+64);
  if(!replies.empty()){set("auto_atl_out_d_bits_opcode",1);set("auto_atl_out_d_bits_size",replies.front().size);set("auto_atl_out_d_bits_source",replies.front().source);for(unsigned w=0;w<4;++w){uint64_t value=0;for(unsigned b=0;b<8;++b)value|=uint64_t(pattern(w*8+b))<<(8*b);set("auto_atl_out_d_bits_data_"+std::to_string(w),value);}}
  unit.evaluate(in);auto out=unit.sample();auto value=[&](const char*n){return out.words.at(oo.at(n));};
  const bool firing=in.words.at(ii.at("io_ex_valid"))&&value("io_ex_ready");set("io_ex_fire",firing);unit.evaluate(in);out=unit.sample();
  const bool afire=edge>=2&&value("auto_atl_out_a_valid")&&in.words.at(ii.at("auto_atl_out_a_ready"));const bool dfire=edge>=2&&in.words.at(ii.at("auto_atl_out_d_valid"))&&value("auto_atl_out_d_ready");
  if(edge>=2)require(!value("io_com_xcpt")&&!value("io_com_internal_replay")&&!value("io_com_retire_late")&&!value("io_com_block_all"),"unexpected PFC exception/replay/block");
  std::optional<CallerCommand> caller;if(firing){require(!accepted,"duplicate EX");accepted=true;ex=edge;caller=CallerCommand{1,pc,raw};}
  auto events=ledger.observe(in,out,unit.sample_activity(edge),unit.sample_ownership(edge),caller);
  std::cout<<"INPUT "<<edge;for(auto v:in.words)std::cout<<' '<<v;std::cout<<'\n';std::cout<<"OUTPUT "<<edge;for(auto v:out.words)std::cout<<' '<<v;std::cout<<'\n';
  for(const auto&e:events){
   std::cout<<"EVENT {\"edge\":"<<edge<<",\"kind\":\""<<e.kind<<"\",\"amount\":"<<e.amount;if(e.command)std::cout<<",\"pc\":"<<e.command->pc<<",\"raw\":"<<e.command->instruction;if(e.transport_source)std::cout<<",\"source\":"<<*e.transport_source;if(e.address)std::cout<<",\"address\":"<<*e.address;if(e.element_group)std::cout<<",\"eg\":"<<*e.element_group;std::cout<<",\"masks\":[";for(unsigned w=0;w<e.bit_mask.size();++w)std::cout<<(w?",":"")<<e.bit_mask[w];std::cout<<"],\"data\":[";for(unsigned w=0;w<e.data_words.size();++w)std::cout<<(w?",":"")<<e.data_words[w];std::cout<<"]}\n";
   if(e.kind=="PFC_front_permission"){require(!retired&&!replied,"late/repeated front permission");retired=true;front=edge;}
   if(e.kind=="VRF_bank_commit"||e.kind=="VRF_scrub_commit"){
    require(e.element_group&&e.data_words.size()==e.bit_mask.size(),"VRF payload missing");
    if(e.kind=="VRF_bank_commit"){require(replied||dfire,"early numeric VRF write before response");++writes;lastwrite=edge;}
    for(unsigned w=0;w<e.bit_mask.size();++w)for(unsigned b=0;b<8;++b){unsigned off=*e.element_group*16+w*8+b;require(off<vrf.size(),"VRF range");uint8_t mask=e.bit_mask[w]>>(8*b);vrf[off]=(vrf[off]&~mask)|(uint8_t(e.data_words[w]>>(8*b))&mask);known[off]|=mask;}
   }
  }
  if(edge==79)for(unsigned i=0;i<1024;++i)require(known[i]==255&&vrf[i]==0,"reset scrub must be observed, not inferred");
  if(afire){require(requests<(vl+15)/16&&value("auto_atl_out_a_bits_opcode")==4&&value("auto_atl_out_a_bits_size")==4&&value("auto_atl_out_a_bits_address")==address+requests*16,"unexpected source request");if(!request)aedge=edge;request=true;unsigned source=value("auto_atl_out_a_bits_source");require(owned.insert(source).second,"source reused before D");replies.push_back({source,unsigned(value("auto_atl_out_a_bits_size")),value("auto_atl_out_a_bits_address")});++requests;}
  if(request&&!replied&&!dfire){require(value("io_backend_busy"),"backend idle with owned unreturned request");require(!writes,"VRF changed under withheld data");++hold;}
  if(dfire){require(request&&retired&&!replies.empty(),"unowned D or retirement waits for D");replied=true;dedge=edge;owned.erase(replies.front().source);replies.pop_front();++responses;}
  const bool drained=replied&&replies.empty()&&responses==(vl+15)/16&&!value("io_backend_busy")&&!value("io_trap_check_busy")&&ledger.pending().empty();unit.commit();
  if(drained){done=true;break;}
 }
 require(done&&accepted&&retired&&request&&replied&&writes&&requests==(vl+15)/16&&responses==requests&&front==ex+2&&front<dedge&&hold>=64,"load lifecycle did not prove bounded early retirement");
 for(unsigned b=0;b<1024;++b){const auto expected=b>=8*32&&b<8*32+vl?pattern(b-8*32):0;require(known[b]==255&&vrf[b]==expected,"VRF output/tail/non-destination mismatch");}
 std::cout<<"RESULT {\"pass\":true,\"VL\":"<<vl<<",\"seed\":"<<seed<<",\"EX_edge\":"<<ex<<",\"front_permission_edge\":"<<front<<",\"A_edge\":"<<aedge<<",\"D_edge\":"<<dedge<<",\"last_VRF_write_edge\":"<<lastwrite<<",\"Get_requests\":"<<requests<<",\"D_responses\":"<<responses<<",\"VRF_write_events\":"<<writes<<",\"withheld_owned_edges\":"<<hold<<",\"VRF_checked_bytes\":1024,\"all_pending_released\":true}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
