// Complete saved Saturn source unit; source control observations are read only.
#include <saturn_timing.hpp>
#include <deque>
#include <iostream>
#include <map>
#include <stdexcept>
using namespace iris::saturn;
static void need(bool ok,const std::string&s){if(!ok)throw std::runtime_error(s);}
int main(int argc,char**argv){try{
 need(argc==5,"integer|fadd LMUL1|8 mode0|1 seed");bool fp=std::string(argv[1])=="fadd";unsigned lm=std::stoul(argv[2]),mode=std::stoul(argv[3]),seed=std::stoul(argv[4]);need((lm==1||lm==8)&&mode<=1,"finite probe");unsigned count=32,vl=(fp?8:32)*lm,beats=2*lm;
 SaturnTimingCut unit(Profile::Compute128,0,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);auto inf=unit.input_fields(Profile::Compute128),ouf=unit.output_fields(Profile::Compute128),af=unit.activity_fields(Profile::Compute128),xf=unit.ownership_fields(Profile::Compute128);std::map<std::string,unsigned>ii,oi,ai,xi;
 for(unsigned n=0;n<inf.size();++n)ii.emplace(std::string(inf[n].name),n);for(unsigned n=0;n<ouf.size();++n)oi.emplace(std::string(ouf[n].name),n);for(unsigned n=0;n<af.size();++n)ai.emplace(std::string(af[n].name),n);for(unsigned n=0;n<xf.size();++n)xi.emplace(std::string(xf[n].name),n);ReferenceInputs in;in.words.resize(inf.size());unsigned attempts=0,retired=0,replays=0,issues=0,writes=0,firstwrite=~0u,firsttail=~0u,fronts_before_first_fullwrite=0,peakvdq=0,peakiq=0,idle=0;bool waiting=false;std::deque<unsigned>microowners;std::map<unsigned,unsigned>pervat;std::string seq=fp?"vu.vxsfp":"vu.vxsint",exu=fp?"vu.vxufp":"vu.vxuint",iq=fp?"vu.vxissq_fp":"vu.vxissq_int";
 for(unsigned edge=0;edge<30000;++edge){std::fill(in.words.begin(),in.words.end(),0);auto set=[&](const char*n,uint64_t v){in.words.at(ii.at(n))=v;};set("reset",edge<2);set("io_status_prv",3);set("io_resp_ready",1);set("auto_atl_out_a_ready",1);set("io_ex_vconfig_vl",vl);set("io_ex_vconfig_vtype_vsew",fp?2:0);set("io_ex_vconfig_vtype_vlmul_mag",lm==8?3:0);set("io_ex_vconfig_vtype_vta",1);set("io_ex_vconfig_vtype_vma",1);bool valid=edge>=130&&!waiting&&retired<count;unsigned vd=mode&&retired%2?24:8,vs2=vd;set("io_ex_valid",valid);set("io_ex_uop_inst",(fp?0x02001057:0x02000057)|(vs2<<20)|(16<<15)|(vd<<7));set("io_ex_uop_pc",0x80001000+4*retired);
 unit.evaluate(in);auto out=unit.sample();auto ov=[&](const char*n){return out.words.at(oi.at(n));};bool fire=valid&&ov("io_ex_ready");set("io_ex_fire",fire);unit.evaluate(in);out=unit.sample();auto a=unit.sample_activity(edge),x=unit.sample_ownership(edge);auto sv=[&](const std::string&n){if(auto i=ai.find(n);i!=ai.end())return a.words.at(i->second);return x.words.at(xi.at(n));};
 if(edge>=130){need(!ov("auto_atl_out_a_valid")&&!ov("io_com_xcpt"),"unexpected memory/exception");if(fire){++attempts;waiting=true;std::cout<<"EX "<<edge<<' '<<retired<<'\n';}
 bool permission=(sv("vfu.pfc.io_s2_inst_valid")&&sv("vfu.pfc.io_s2_retire"))||(sv("vfu.ifc.io_busy")&&sv("vfu.ifc.io_retire"));bool replay=sv("vfu.pfc.io_s2_inst_valid")&&!sv("vfu.ifc.io_busy")&&ov("io_com_block_all")&&!ov("io_com_internal_replay");
 if(permission){need(waiting,"permission owner missing");waiting=false;++retired;std::cout<<"RETIRE "<<edge<<' '<<retired<<'\n';}else if(replay){need(waiting,"replay owner missing");waiting=false;++replays;}
 unsigned vdq=0,q=0;for(unsigned k=0;k<4;++k)vdq+=sv("vu.vdq.valids_"+std::to_string(k));for(unsigned k=0;k<3;++k)q+=sv(iq+".q.valids_"+std::to_string(k));peakvdq=std::max(peakvdq,vdq);peakiq=std::max(peakiq,q);
 if(sv(seq+".io_iss_valid")&&sv(seq+".io_iss_ready")){unsigned vat=sv(seq+".io_vat"),eidx=sv(seq+".eidx");microowners.push_back(vat);++pervat[vat];++issues;std::cout<<"ISSUE "<<edge<<' '<<vat<<' '<<eidx<<'\n';if(pervat[vat]==beats&&firsttail==~0u)firsttail=edge;}
 if(sv(exu+".io_pipe_write_valid")){need(!microowners.empty(),"physical write without earlier source issue");auto vat=microowners.front();microowners.pop_front();++writes;std::cout<<"WRITE "<<edge<<' '<<vat<<'\n';if(writes==1)firstwrite=edge;if(writes==beats)fronts_before_first_fullwrite=retired;}
 std::cout<<"Q "<<edge<<' '<<vdq<<' '<<q<<' '<<retired<<' '<<issues<<' '<<writes<<'\n';if(retired==count&&!ov("io_backend_busy"))++idle;else idle=0;
 }
 unit.commit();if(idle==8){need(issues==count*beats&&writes==issues&&microowners.empty(),"full source issue/write count");std::cerr<<"{\"pass\":true,\"kind\":\""<<(fp?"fadd":"integer")<<"\",\"LMUL\":"<<lm<<",\"mode\":"<<mode<<",\"seed\":"<<seed<<",\"commands\":"<<count<<",\"attempts\":"<<attempts<<",\"CPU_replays\":"<<replays<<",\"microissues\":"<<issues<<",\"physical_VRF_write_beats\":"<<writes<<",\"first_write\":"<<firstwrite<<",\"first_sequence_tail\":"<<firsttail<<",\"front_retirements_by_first_full_destination_write\":"<<fronts_before_first_fullwrite<<",\"VDQ_peak\":"<<peakvdq<<",\"IQ_peak\":"<<peakiq<<",\"end_edge\":"<<edge<<"}\n";return 0;}
 }
 throw std::runtime_error("source probe did not drain");
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
