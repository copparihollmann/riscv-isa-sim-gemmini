// Saved full Saturn unit. Only source physical input ports are driven.
#include "rvv_integer_eg_source_v1.hpp"
#include <saturn_timing.hpp>
#include <algorithm>
#include <array>
#include <deque>
#include <iostream>
#include <map>
#include <set>
#include <string>
using namespace iris::saturn;
using namespace iris::rvv_integer_source;
static void need(bool b,const std::string&s){if(!b)throw std::runtime_error(s);}
struct Ack{uint64_t due;unsigned source,size;};
int main(int argc,char**argv){try{
 need(argc==6,"SEW LMUL mode seed count");unsigned sew=std::stoul(argv[1]),lm=std::stoul(argv[2]),mode=std::stoul(argv[3]),seed=std::stoul(argv[4]),count=std::stoul(argv[5]);need(mode<4&&count&&count<=128,"finite stream");Scheduler::validate({1,0,8,16,24,sew,lm});
 SaturnTimingCut unit(Profile::Compute128,0,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);
 std::map<std::string,unsigned>ii,oi,ai,xi;auto inf=unit.input_fields(Profile::Compute128),ouf=unit.output_fields(Profile::Compute128),af=unit.activity_fields(Profile::Compute128),xf=unit.ownership_fields(Profile::Compute128);
 for(unsigned i=0;i<inf.size();++i)ii.emplace(inf[i].name,i);for(unsigned i=0;i<ouf.size();++i)oi.emplace(ouf[i].name,i);for(unsigned i=0;i<af.size();++i)ai.emplace(af[i].name,i);for(unsigned i=0;i<xf.size();++i)xi.emplace(xf[i].name,i);
 ReferenceInputs in;in.words.resize(inf.size());Scheduler model;std::array<unsigned char,1024>logical{};std::set<uint64_t>stored;std::map<unsigned,Ack>owners;std::deque<Ack>acks;
 enum Phase{Init,Run,Store};Phase phase=Init;unsigned init=0,stores=0,retired=0,accepted=0,issues=0,writes=0,attempts=0,replays=0,idle=0,bytes=0,reqs=0,resps=0,vdqpeak=0,iqpeak=0,rawedges=0,wawedges=0;uint64_t checks=0,tlb=0;bool waiting=false;unsigned gap=seed%3;
 auto initvalue=[&](unsigned i){return (i==0?0xfefdfcfbfaf9f8f7ULL:i==1?0x030201fffefdfcfbULL:0x807f0100fffe0201ULL)^(uint64_t(seed)*0x0101010101010101ULL);};
 auto logical_init=[&](unsigned reg,uint64_t value){for(unsigned n=0;n<32*lm;n+=sew/8)for(unsigned b=0;b<sew/8;++b)logical[32*reg+n+b]=value>>(8*b);};
 auto logical_add=[&](const Command&c){auto before=logical;for(unsigned n=0;n<32*lm;n+=sew/8){uint64_t a=0,b=0;for(unsigned j=0;j<sew/8;++j){a|=uint64_t(before[32*c.vs1+n+j])<<(8*j);b|=uint64_t(before[32*c.vs2+n+j])<<(8*j);}const auto sum=a+b;for(unsigned j=0;j<sew/8;++j)logical[32*c.vd+n+j]=sum>>(8*j);}};
 for(unsigned edge=0;edge<60000;++edge){
  std::fill(in.words.begin(),in.words.end(),0);auto set=[&](const char*n,uint64_t v){in.words.at(ii.at(n))=v;};auto setn=[&](const std::string&n,uint64_t v){in.words.at(ii.at(n))=v;};
  set("reset",edge<2);set("io_status_prv",3);set("io_resp_ready",1);set("auto_atl_out_a_ready",edge%7!=3);set("io_mem_tlb_req_ready",1);set("io_mem_tlb_resp_paddr",tlb);
  unsigned reg=phase==Init?8+8*init:8+8*stores,vd=((mode==1||mode==2)&&retired%2)?24:8,vs2=(mode==2&&retired%2)?8:mode==3?24:vd;
  unsigned mag=lm==1?0:lm==2?1:lm==4?2:3,vsew=phase==Store?0:sew==8?0:sew==16?1:sew==32?2:3;
  set("io_ex_vconfig_vl",phase==Store?32*lm:256/sew*lm);set("io_ex_vconfig_vtype_vsew",vsew);set("io_ex_vconfig_vtype_vlmul_mag",mag);set("io_ex_vconfig_vtype_vta",1);set("io_ex_vconfig_vtype_vma",1);
  bool remaining=phase==Init?init<3:phase==Run?retired<count:stores<3;
  bool valid=edge>=130&&!waiting&&remaining&&!gap;
  if(gap&&!waiting&&edge>=130)--gap;
  set("io_ex_valid",valid);set("io_ex_uop_inst",phase==Init?0x5e004057|(10<<15)|(reg<<7):phase==Run?0x02000057|(vs2<<20)|(16<<15)|(vd<<7):0x02000027|(10<<15)|(reg<<7));set("io_ex_uop_pc",0x80001000+4*(phase==Init?init:phase==Run?3+retired:3+count+stores));
  set("io_ex_uop_rs1_data",phase==Init?initvalue(init):phase==Store?0x80010000ULL+512*stores:0);
  bool dvalid=!acks.empty()&&acks.front().due<=edge;set("auto_atl_out_d_valid",dvalid);set("auto_atl_out_d_bits_opcode",0);if(dvalid){set("auto_atl_out_d_bits_size",acks.front().size);set("auto_atl_out_d_bits_source",acks.front().source);}
  unit.evaluate(in);auto out=unit.sample();auto ov=[&](const std::string&n){return out.words.at(oi.at(n));};if(edge>=130&&ov("io_mem_tlb_req_valid")){need(ov("io_mem_tlb_req_bits_vaddr")<(1ULL<<35),"fixture identityTLB outside physicaldomain");set("io_mem_tlb_resp_paddr",ov("io_mem_tlb_req_bits_vaddr"));}unit.evaluate(in);out=unit.sample();bool fire=valid&&ov("io_ex_ready");set("io_ex_fire",fire);unit.evaluate(in);out=unit.sample();const auto nexttlb=edge>=130&&ov("io_mem_tlb_req_valid")?ov("io_mem_tlb_req_bits_vaddr"):tlb;
  auto a=unit.sample_activity(edge),x=unit.sample_ownership(edge);auto sv=[&](const std::string&n){auto i=ai.find(n);return i!=ai.end()?a.words.at(i->second):x.words.at(xi.at(n));};
  auto equal=[&](uint64_t got,uint64_t expected,const char*n){++checks;need(got==expected,"edge="+std::to_string(edge)+" "+n+" model="+std::to_string(got)+" source="+std::to_string(expected));};
  if(edge>=130){
   need(!ov("io_com_xcpt"),"unexpected source exception");need(!ov("io_set_fflags_valid")&&!ov("io_set_vxsat"),"VADD must not raise floating flags or saturation");
   if(fire){++attempts;waiting=true;}
   bool permission=(sv("vfu.pfc.io_s2_inst_valid")&&sv("vfu.pfc.io_s2_retire"))||(sv("vfu.ifc.io_busy")&&sv("vfu.ifc.io_retire"));bool replay=sv("vfu.pfc.io_s2_inst_valid")&&!sv("vfu.ifc.io_busy")&&ov("io_com_block_all")&&!ov("io_com_internal_replay");
   if(permission){need(waiting,"missing actualCPU permission owner");waiting=false;if(phase==Init){logical_init(8+8*init,initvalue(init));++init;}else if(phase==Run){++retired;gap=(retired*17+seed)%5==0?2:0;}else ++stores;}
   else if(replay){need(waiting,"missing actualCPU replay owner");waiting=false;++replays;}
   if(phase==Run){
    std::optional<Command>c;if(sv("vu.io_dis_valid")){auto raw=sv("vu.io_dis_bits_bits");need((raw&0xfc00707f)==0x57,"only VADD enters finite model");c=Command{accepted+1,unsigned(sv("vu.io_dis_bits_vat")),unsigned(raw>>7&31),unsigned(raw>>15&31),unsigned(raw>>20&31),sew,lm};}
    auto e=model.step(edge,c);unsigned vdq=0,iq=0;for(unsigned i=0;i<4;++i)vdq+=sv("vu.vdq.valids_"+std::to_string(i));for(unsigned i=0;i<3;++i)iq+=sv("vu.vxissq_int.q.valids_"+std::to_string(i));
    equal(e.vdq_before,vdq,"VDQ occupancy");equal(e.iq_before,iq,"IQ occupancy");equal(e.seq_before,sv("vu.vxsint.valid"),"sequencer valid");equal(e.input_ready,sv("vu.io_dis_ready"),"backendready");equal(e.vdq_dequeue,sv("vu.vdq.io_deq_valid")&&sv("vu.vdq.io_deq_ready"),"VDQ dequeue");equal(e.iq_dequeue,sv("vu.vxissq_int.io_deq_valid")&&sv("vu.vxissq_int.io_deq_ready"),"IQ dequeue");equal(e.seq_ready,sv("vu.vxsint.io_dis_ready"),"sequencer handoff");equal(bool(e.issue),sv("vu.vxsint.io_iss_valid")&&sv("vu.vxsint.io_iss_ready"),"microissue");equal(bool(e.write),sv("vu.vxuint.io_pipe_write_valid"),"physical write");equal(0,sv("vu.vxuint.io_pipe_hazards_1_valid"),"unused integer pipe slot1");
    if(e.input_fire){++accepted;logical_add(*c);}
    if(e.candidate){equal(e.candidate->command.vat,sv("vu.vxsint.io_vat"),"VAT");equal(e.candidate->eidx,sv("vu.vxsint.eidx"),"eidx");equal(e.candidate->source1,sv("vu.vxsint.io_rvs1_bits_eg"),"source1 EG");equal(e.candidate->source2,sv("vu.vxsint.io_rvs2_bits_eg"),"source2 EG");need(sv("vu.vxsint.io_rvs1_ready")&&sv("vu.vxsint.io_rvs2_ready"),"unmodeled VRF port contention");}
    if(e.issue){++issues;equal(0,sv("vu.vxuint.io_iss_bits_pipe_depth"),"VADD depthminusone");equal(e.issue->tail,sv("vu.vxsint.io_iss_bits_tail"),"tail");equal(e.issue->eidx,sv("vu.vxsint.io_iss_bits_eidx"),"issued eidx");}
    if(e.write){++writes;equal(e.write->destination,sv("vu.vxuint.io_pipe_write_bits_eg"),"write EG");equal(edge-e.write->issue_edge,1,"VADD issue to write");}
    equal(bool(e.pipe[0]),sv("vu.vxuint.io_pipe_hazards_0_valid"),"pipe valid");if(e.pipe[0]){equal(e.pipe[0]->destination,sv("vu.vxuint.io_pipe_hazards_0_bits_eg"),"pipe EG");equal(e.pipe[0]->command.vat,sv("vu.vxuint.io_pipe_hazards_0_bits_vat"),"pipe VAT");}
    vdqpeak=std::max(vdqpeak,vdq);iqpeak=std::max(iqpeak,iq);rawedges+=e.raw;wawedges+=e.waw;
   }
   if(ov("auto_atl_out_a_valid")&&edge%7!=3){
    need(phase==Store,"memory appeared during pure initialized VADD");auto address=ov("auto_atl_out_a_bits_address");unsigned mask=ov("auto_atl_out_a_bits_mask"),size=ov("auto_atl_out_a_bits_size"),source=ov("auto_atl_out_a_bits_source"),opcode=ov("auto_atl_out_a_bits_opcode");need((opcode==0||opcode==1)&&size==4,"physical output must be16BPut");need(!owners.count(source),"source reused before acknowledgment");Ack ack{edge+2+seed%5,source,size};owners.emplace(source,ack);acks.push_back(ack);++reqs;
    for(unsigned b=0;b<32;++b)if(mask&(1u<<b)){uint64_t addr=(address&~31ULL)+b;need(addr>=0x80010000&&addr<0x80010600,"numeric output address range");unsigned group=(addr-0x80010000)/512,offset=(addr-0x80010000)%512;need(group<3&&offset<32*lm,"requested output span");uint64_t data=ov("auto_atl_out_a_bits_data_"+std::to_string(b/8));unsigned byte=(data>>(8*(b%8)))&255;need(byte==logical[32*(8+8*group)+offset],"actual output byte disagrees independent modular VADD golden");need(stored.insert(addr).second,"duplicate output byte");++bytes;}
   }
   if(dvalid&&ov("auto_atl_out_d_ready")){need(owners.erase(acks.front().source)==1,"D without owned A");acks.pop_front();++resps;}
   bool complete=phase==Init?init==3:phase==Run?retired==count:stores==3;
   if(complete&&!waiting&&!ov("io_backend_busy")&&!ov("io_trap_check_busy")&&owners.empty())++idle;else idle=0;
  }
  unit.commit();tlb=nexttlb;
  if(idle==8){
   if(phase==Init){phase=Run;idle=0;}
   else if(phase==Run){need(accepted==count&&issues==count*2*lm&&writes==issues&&model.empty(),"full numerical VADD source/model drain");phase=Store;idle=0;}
   else{need(bytes==3*32*lm&&reqs==resps&&reqs==3*2*lm,"all independently checked output bytes/requests complete");std::cerr<<"{\"pass\":true,\"SEW\":"<<sew<<",\"LMUL\":"<<lm<<",\"mode\":"<<mode<<",\"seed\":"<<seed<<",\"commands\":"<<count<<",\"CPU_attempts\":"<<attempts<<",\"CPU_replays\":"<<replays<<",\"microissues\":"<<issues<<",\"physical_write_beats\":"<<writes<<",\"edge_checks\":"<<checks<<",\"RAW_blocked_edges\":"<<rawedges<<",\"WAW_blocked_edges\":"<<wawedges<<",\"VDQ_peak\":"<<vdqpeak<<",\"IQ_peak\":"<<iqpeak<<",\"output_bytes\":"<<bytes<<",\"output_Put_requests\":"<<reqs<<",\"synthetic_ack_delay\":"<<2+seed%5<<",\"source_reset_and_VMV_initialization_only\":true,\"end_edge\":"<<edge<<"}\n";return 0;}
  }
 }
 throw std::runtime_error("finite numeric source/model did not drain");
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
