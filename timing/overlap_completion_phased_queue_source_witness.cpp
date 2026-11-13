// Conditional MM-only backend queue differential against the frozen complete
// Saturn source unit. Internal bits are READ ONLY comparison observations.
#include <saturn_timing.hpp>
#include "overlap_completion_command_queues_v2.hpp"
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
using namespace iris::saturn;
int main(int argc,char**argv){try{
 if(argc!=6)throw std::invalid_argument("kind shape count rotate seed");
 const bool fp8=std::string(argv[1])=="fp8",rotate=std::stoul(argv[4]);const unsigned shape=std::stoul(argv[2]),count=std::stoul(argv[3]),seed=std::stoul(argv[5]);
 if((shape!=8&&shape!=16&&shape!=32)||(count!=64&&count!=256))throw std::invalid_argument("finite power2 source witness");
 SaturnTimingCut unit(Profile::Compute128,0,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);
 auto infields=unit.input_fields(Profile::Compute128),outfields=unit.output_fields(Profile::Compute128),afields=unit.activity_fields(Profile::Compute128),xfields=unit.ownership_fields(Profile::Compute128);
 std::map<std::string,unsigned>ix,ox,ax,xx;
 const unsigned words=infields.size();
 for(unsigned k=0;k<infields.size();++k)ix.emplace(std::string(infields[k].name),k);
 for(unsigned k=0;k<outfields.size();++k)ox.emplace(std::string(outfields[k].name),k);
 for(unsigned k=0;k<afields.size();++k)ax.emplace(std::string(afields[k].name),k);
 for(unsigned k=0;k<xfields.size();++k)xx.emplace(std::string(xfields[k].name),k);
 ReferenceInputs in;in.words.resize(words);iris::opu_entry::CommandQueuesPhased model;
 unsigned accepted=0,retired=0,issues=0,full=0,stalls=0,checks=0,replays=0;bool waiting=false;unsigned idle=0;
 for(unsigned edge=0;edge<20000;++edge){
  std::fill(in.words.begin(),in.words.end(),0);auto set=[&](const char*n,uint64_t v){in.words.at(ix.at(n))=v;};
  set("reset",edge<2);set("io_status_prv",3);set("io_resp_ready",1);set("auto_atl_out_a_ready",1);
  set("io_ex_vconfig_vl",shape);set("io_ex_vconfig_vtype_tm",shape);set("io_ex_vconfig_vtype_tk",1);set("io_ex_vconfig_vtype_vtwiden",3);set("io_ex_vconfig_vtype_vsew",0);set("io_ex_vconfig_vtype_vlmul_mag",2);set("io_ex_vconfig_vtype_vta",1);set("io_ex_vconfig_vtype_vma",1);
  bool valid=edge>=130&&!waiting&&retired<count;unsigned tile=rotate?retired%4:0;
  set("io_ex_valid",valid);set("io_ex_uop_inst",(fp8?0xf2001077U:0xf2000077U)|(8U<<20)|(16U<<15)|(tile<<10));set("io_ex_uop_pc",0x80001000+4*retired);
  unit.evaluate(in);auto out=unit.sample();auto ov=[&](const char*n){return out.words.at(ox.at(n));};
  bool fire=valid&&ov("io_ex_ready");set("io_ex_fire",fire);unit.evaluate(in);out=unit.sample();
  auto a=unit.sample_activity(edge),x=unit.sample_ownership(edge);
  auto sv=[&](const std::string&n){auto i=ax.find(n);if(i!=ax.end())return a.words.at(i->second);auto j=xx.find(n);if(j!=xx.end())return x.words.at(j->second);throw std::runtime_error("source observation missing "+n);};
  if(edge>=2){
   if(ov("auto_atl_out_a_valid")||ov("io_com_xcpt"))throw std::runtime_error("unexpected memory/exception outside MM control scope");
   const bool input_valid=sv("vu.vdq.io_enq_valid");const auto raw=input_valid?sv("vu.vdq.io_enq_bits_bits"):0;
   std::optional<iris::opu_entry::Command>command;
   if(input_valid)command=iris::opu_entry::Command{sv("vu.vdq.io_enq_bits_vat"),unsigned((raw>>10)&3),shape,shape,bool((raw>>12)&1)};
   auto prediction=model.advance(edge);if(command)prediction=model.commit_input(edge,*command);
   auto eq=[&](bool b,const char*name){if(!b)throw std::runtime_error("queue differential edge"+std::to_string(edge)+" "+name);++checks;};
   eq(prediction.input_ready==bool(sv("vu.vdq.io_enq_ready")),"VDQready");
   eq(prediction.input_fire==bool(input_valid&&sv("vu.vdq.io_enq_ready")),"VDQfire");
   eq(prediction.vdq_dequeue==bool(sv("vu.vdq.io_deq_valid")&&sv("vu.vdq.io_deq_ready")),"VDQdeq");
   eq(prediction.iq_enqueue==bool(sv("vu.vxissq_int.io_enq_valid")&&sv("vu.vxissq_int.io_enq_ready")),"IQenq");
   eq(prediction.iq_dequeue==bool(sv("vu.vxissq_int.io_deq_valid")&&sv("vu.vxissq_int.io_deq_ready")),"IQdeq");
   eq(prediction.seq_ready==bool(sv("vu.vos.io_dis_ready")),"seqReady");
   eq(bool(prediction.issue)==bool(sv("vu.vos.io_iss_valid")),"microValid");
   unsigned vdq=0,iq=0;for(unsigned k=0;k<4;++k)vdq+=sv("vu.vdq.valids_"+std::to_string(k));for(unsigned k=0;k<3;++k)iq+=sv("vu.vxissq_int.q.valids_"+std::to_string(k));
   eq(prediction.vdq_before==vdq,"VDQoccupancy");eq(prediction.iq_before==iq,"IQoccupancy");
   if(prediction.issue){eq(prediction.issue->entry==sv("vu.vos.io_iss_bits_mrf_idx_0"),"MRFentry");eq(prediction.issue->command.id==sv("vu.vos.io_vat"),"VATowner");++issues;}
   if(!prediction.input_ready)++full;if(input_valid&&!prediction.input_ready)++stalls;
   std::cout<<"{\"edge\":"<<edge<<",\"input_valid\":"<<input_valid<<",\"input_ready\":"<<sv("vu.vdq.io_enq_ready")<<",\"vdq\":"<<vdq<<",\"iq\":"<<iq<<",\"seq\":"<<prediction.seq_before<<",\"microissue\":"<<bool(prediction.issue)<<"}\n";
   const bool pfc=sv("vfu.pfc.io_s2_inst_valid")&&sv("vfu.pfc.io_s2_retire");const bool ifc=sv("vfu.ifc.io_busy")&&sv("vfu.ifc.io_retire");
   if(fire){++accepted;waiting=true;}
   if(pfc||ifc){if(!waiting)throw std::runtime_error("source front permission without pending producer");waiting=false;++retired;}
   // Full VDQ asks the CPU to replay its unretired S2 instruction; it is not
   // a stored command and must not be counted as retired or advanced.
   if(sv("vfu.pfc.io_s2_inst_valid")&&!sv("vfu.ifc.io_busy")&&ov("io_com_block_all")&&!ov("io_com_internal_replay")){if(!waiting)throw std::runtime_error("replay without front owner");waiting=false;++replays;}
   if(retired==count&&model.empty()&&!ov("io_backend_busy"))++idle;else idle=0;
  }
  unit.commit();
  if(idle>=8){std::cerr<<"{\"pass\":true,\"accepted_front_attempts\":"<<accepted<<",\"retired\":"<<retired<<",\"front_replays\":"<<replays<<",\"microissues\":"<<issues<<",\"queue_full_edges\":"<<full<<",\"blocked_input_edges\":"<<stalls<<",\"checks\":"<<checks<<",\"edges\":"<<edge+1<<"}\n";return 0;}
 }
 throw std::runtime_error("bounded source producer did not drain");
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
