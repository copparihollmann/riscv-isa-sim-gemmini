#include "rvv_integer_eg_source_v1.hpp"
#include <saturn_timing.hpp>
#include <algorithm>
#include <iostream>
#include <map>
#include <string>
#include <vector>
using namespace iris::saturn;
using namespace iris::rvv_integer_source;
static void need(bool b,const std::string&s){if(!b)throw std::runtime_error(s);}
int main(int argc,char**argv){try{
  need(argc==6,"SEW LMUL mode seed count");
  unsigned sew=std::stoul(argv[1]),lm=std::stoul(argv[2]),mode=std::stoul(argv[3]),seed=std::stoul(argv[4]),count=std::stoul(argv[5]);
  need(mode<=3&&count>0&&count<=256,"finite command stream");
  SaturnTimingCut unit(Profile::Compute128,0,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);
  std::map<std::string,unsigned>ii,oi,ai,xi;
  auto inf=unit.input_fields(Profile::Compute128),ouf=unit.output_fields(Profile::Compute128),af=unit.activity_fields(Profile::Compute128),xf=unit.ownership_fields(Profile::Compute128);
  for(unsigned i=0;i<inf.size();++i)ii.emplace(inf[i].name,i);
  for(unsigned i=0;i<ouf.size();++i)oi.emplace(ouf[i].name,i);
  for(unsigned i=0;i<af.size();++i)ai.emplace(af[i].name,i);
  for(unsigned i=0;i<xf.size();++i)xi.emplace(xf[i].name,i);
  ReferenceInputs in;in.words.resize(inf.size());Scheduler model;
  unsigned retired=0,attempts=0,replays=0,accepted=0,issues=0,writes=0,idle=0,vdq_peak=0,iq_peak=0,raw_edges=0,waw_edges=0;
  bool waiting=false;uint64_t checks=0;std::vector<unsigned>write_edges;
  std::map<unsigned,uint64_t> vat_owner;
  unsigned gap=seed%3;
  for(unsigned edge=0;edge<40000;++edge){
    std::fill(in.words.begin(),in.words.end(),0);
    auto set=[&](const char*n,uint64_t v){in.words.at(ii.at(n))=v;};
    set("reset",edge<2);set("io_status_prv",3);set("io_resp_ready",1);set("auto_atl_out_a_ready",1);
    unsigned vd=(mode==1||mode==2)&&retired%2?24:8;
    unsigned vs2=mode==2&&retired%2?8:(mode==3?24:vd);
    unsigned vsew=sew==8?0:sew==16?1:sew==32?2:3,mag=lm==1?0:lm==2?1:lm==4?2:3;
    Command geometry{1,0,vd,16,vs2,sew,lm};Scheduler::validate(geometry);
    set("io_ex_vconfig_vl",256/sew*lm);set("io_ex_vconfig_vtype_vsew",vsew);set("io_ex_vconfig_vtype_vlmul_mag",mag);
    set("io_ex_vconfig_vtype_vta",1);set("io_ex_vconfig_vtype_vma",1);
    bool valid=edge>=130&&!waiting&&retired<count&&(gap==0);
    if(gap&&!waiting&&edge>=130)--gap;
    set("io_ex_valid",valid);set("io_ex_uop_inst",0x02000057|(vs2<<20)|(16<<15)|(vd<<7));set("io_ex_uop_pc",0x80001000+4*retired);
    unit.evaluate(in);auto out=unit.sample();auto ov=[&](const char*n){return out.words.at(oi.at(n));};
    bool fire=valid&&ov("io_ex_ready");set("io_ex_fire",fire);unit.evaluate(in);out=unit.sample();
    auto a=unit.sample_activity(edge),x=unit.sample_ownership(edge);
    auto sv=[&](const std::string&n){auto it=ai.find(n);return it!=ai.end()?a.words.at(it->second):x.words.at(xi.at(n));};
    if(edge>=130){
      auto equal=[&](uint64_t got,uint64_t expected,const std::string&n){++checks;need(got==expected,"edge="+std::to_string(edge)+" "+n+" model="+std::to_string(got)+" source="+std::to_string(expected));};
      need(!ov("auto_atl_out_a_valid")&&!ov("io_com_xcpt"),"unexpected memory/exception");
      if(fire){++attempts;waiting=true;}
      bool permission=(sv("vfu.pfc.io_s2_inst_valid")&&sv("vfu.pfc.io_s2_retire"))||(sv("vfu.ifc.io_busy")&&sv("vfu.ifc.io_retire"));
      bool replay=sv("vfu.pfc.io_s2_inst_valid")&&!sv("vfu.ifc.io_busy")&&ov("io_com_block_all")&&!ov("io_com_internal_replay");
      if(permission){need(waiting,"CPU permission owner missing");waiting=false;++retired;gap=(retired*17+seed)%5==0?2:0;}
      else if(replay){need(waiting,"CPU replay owner missing");waiting=false;++replays;}
      unsigned vdq=0,iq=0;
      for(unsigned i=0;i<4;++i)vdq+=sv("vu.vdq.valids_"+std::to_string(i));
      for(unsigned i=0;i<3;++i)iq+=sv("vu.vxissq_int.q.valids_"+std::to_string(i));
      std::optional<Command> command;
      if(sv("vu.io_dis_valid")){
        uint64_t raw=sv("vu.io_dis_bits_bits");
        command=Command{uint64_t(accepted)+1,unsigned(sv("vu.io_dis_bits_vat")),unsigned(raw>>7&31),unsigned(raw>>15&31),unsigned(raw>>20&31),sew,lm};
      }
      auto e=model.step(edge,command);
      equal(e.vdq_before,vdq,"VDQ occupancy");equal(e.iq_before,iq,"IQ occupancy");equal(e.seq_before,sv("vu.vxsint.valid"),"sequencer valid");
      equal(e.input_ready,sv("vu.io_dis_ready"),"backend input ready");
      equal(e.vdq_dequeue,sv("vu.vdq.io_deq_valid")&&sv("vu.vdq.io_deq_ready"),"VDQ dequeue");
      equal(e.iq_dequeue,sv("vu.vxissq_int.io_deq_valid")&&sv("vu.vxissq_int.io_deq_ready"),"IQ dequeue");
      equal(e.seq_ready,sv("vu.vxsint.io_dis_ready"),"sequencer handoff ready");
      equal(bool(e.issue),sv("vu.vxsint.io_iss_valid")&&sv("vu.vxsint.io_iss_ready"),"microissue");
      equal(bool(e.write),sv("vu.vxuint.io_pipe_write_valid"),"physical VRF write");
      equal(0,ov("io_set_fflags_valid"),"integer VADD never sets FFLAGS");
      equal(0,sv("vu.vxuint.io_pipe_hazards_1_valid"),"second physical int pipe slot inactive for VADD");
      if(e.input_fire){++accepted;vat_owner[command->vat]=command->id;std::cout<<"ACCEPT "<<edge<<' '<<command->id<<' '<<command->vat<<'\n';}
      if(e.candidate){equal(e.candidate->command.vat,sv("vu.vxsint.io_vat"),"sequencer VAT");equal(e.candidate->eidx,sv("vu.vxsint.eidx"),"sequencer eidx");equal(e.candidate->source1,sv("vu.vxsint.io_rvs1_bits_eg"),"source1 EG");equal(e.candidate->source2,sv("vu.vxsint.io_rvs2_bits_eg"),"source2 EG");need(sv("vu.vxsint.io_rvs1_ready")&&sv("vu.vxsint.io_rvs2_ready"),"unmodeled VRF port contention");}
      if(e.issue){equal(0,sv("vu.vxuint.io_iss_bits_pipe_depth"),"actual integer pipeline depthminusone");++issues;equal(e.issue->tail,sv("vu.vxsint.io_iss_bits_tail"),"tail");equal(e.issue->eidx,sv("vu.vxsint.io_iss_bits_eidx"),"microissue eidx");equal(e.issue->command.vat,sv("vu.vxsint.io_iss_bits_vat"),"microissue VAT");std::cout<<"ISSUE "<<edge<<' '<<e.issue->command.id<<' '<<e.issue->index<<' '<<e.issue->destination<<' '<<e.issue->source1<<' '<<e.issue->source2<<'\n';}
      if(e.write){++writes;write_edges.push_back(edge);equal(e.write->destination,sv("vu.vxuint.io_pipe_write_bits_eg"),"physical write EG");equal(edge-e.write->issue_edge,1,"source issue/write depth");std::cout<<"WRITE "<<edge<<' '<<e.write->command.id<<' '<<e.write->index<<' '<<e.write->destination<<'\n';}
      for(unsigned stage=0;stage<1;++stage){std::string prefix="vu.vxuint.io_pipe_hazards_"+std::to_string(stage);equal(bool(e.pipe[stage]),sv(prefix+"_valid"),"pipeline valid");if(e.pipe[stage]){equal(e.pipe[stage]->destination,sv(prefix+"_bits_eg"),"pipeline EG");equal(e.pipe[stage]->command.vat,sv(prefix+"_bits_vat"),"pipeline VAT");}}
      vdq_peak=std::max(vdq_peak,vdq);iq_peak=std::max(iq_peak,iq);raw_edges+=e.raw;waw_edges+=e.waw;
      if(retired==count&&!ov("io_backend_busy"))++idle;else idle=0;
    }
    unit.commit();
    if(idle==8){need(accepted==count&&issues==count*2*lm&&writes==issues&&model.empty(),"full source/model drain");std::cerr<<"{\"pass\":true,\"SEW\":"<<sew<<",\"LMUL\":"<<lm<<",\"mode\":"<<mode<<",\"seed\":"<<seed<<",\"commands\":"<<count<<",\"CPU_attempts\":"<<attempts<<",\"CPU_replays\":"<<replays<<",\"microissues\":"<<issues<<",\"physical_write_beats\":"<<writes<<",\"edge_checks\":"<<checks<<",\"RAW_blocked_edges\":"<<raw_edges<<",\"WAW_blocked_edges\":"<<waw_edges<<",\"VDQ_peak\":"<<vdq_peak<<",\"IQ_peak\":"<<iq_peak<<",\"end_edge\":"<<edge<<"}\n";return 0;}
  }
  throw std::runtime_error("source/model did not drain");
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
