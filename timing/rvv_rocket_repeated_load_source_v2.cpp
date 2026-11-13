// Frozen complete SaturnRocketUnit, driven only at its physical source ports.
// External memory below is an explicitly synthetic, owned TL responder.
#include <saturn_timing.hpp>
#include <algorithm>
#include <array>
#include <deque>
#include <iostream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
using namespace iris::saturn;
static void need(bool v,const std::string&s){if(!v)throw std::runtime_error(s);}
struct Pending {unsigned source,size,opcode,beat=0,due;uint64_t address;};
int main(int argc,char**argv){try{
 need(argc==9,"lmul count delay gap A-stall-period reverse seed initialize");
 unsigned lm=std::stoul(argv[1]),count=std::stoul(argv[2]),delay=std::stoul(argv[3]),gap=std::stoul(argv[4]),astall=std::stoul(argv[5]),reverse=std::stoul(argv[6]),seed=std::stoul(argv[7]),init=std::stoul(argv[8]);
 need((lm==4||lm==8)&&(count==16||count==64)&&gap>0,"finite control domain");
 const unsigned vl=lm*8,bytes=vl*4,mag=lm==8?3:2;constexpr uint64_t base=0x80042900,outbase=0x80041d00;
 SaturnTimingCut unit(Profile::Rocket256,2,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);
 auto inf=unit.input_fields(Profile::Rocket256),ouf=unit.output_fields(Profile::Rocket256),af=unit.activity_fields(Profile::Rocket256),xf=unit.ownership_fields(Profile::Rocket256);
 auto name=[](std::string_view n){return std::string(n.substr(0,n.find('@')));};
 std::map<std::string,std::vector<unsigned>>ii,oi,ai,xi;for(unsigned k=0;k<inf.size();++k)ii[name(inf[k].name)].push_back(k);for(unsigned k=0;k<ouf.size();++k)oi[name(ouf[k].name)].push_back(k);for(unsigned k=0;k<af.size();++k)ai[name(af[k].name)].push_back(k);for(unsigned k=0;k<xf.size();++k)xi[name(xf[k].name)].push_back(k);
 ReferenceInputs in;in.words.resize(inf.size());std::deque<Pending> replies;std::set<unsigned>owned;std::optional<Pending>put;std::array<std::array<uint64_t,4>,32>shadow{},known{};
 bool waiting=false;unsigned phase=init?0:1,ordinal=0,accepted=0,retired=0,replays=0,gets=0,dbeats=0,puts=0,acks=0,storebytes=0,writebeats=0,loadwrites=0,peak=0,peakliq=0,peaklob=0,peakreader=0,full=0,stall=0,first=~0u,last=0,done=~0u,lastD=0;uint64_t tlb=0;int active=-1;unsigned idle=0;
 auto expectedbyte=[&](uint64_t adr){need(adr>=base&&adr<base+bytes,"load outside explicit initialized backing");unsigned off=adr-base;return uint8_t(((off/4+3)>>(8*(off%4)))&255);};
 auto responseword=[&](uint64_t adr){uint64_t v=0;for(unsigned b=0;b<8;++b)v|=uint64_t(expectedbyte(adr+b))<<(8*b);return v;};
 for(unsigned edge=0;edge<100000;++edge){
  std::fill(in.words.begin(),in.words.end(),0);auto set=[&](const char*n,uint64_t v){need(ii.count(n),std::string("missing input ")+n);in.words.at(ii.at(n).front())=v;};
  set("reset",edge<2);set("io_core_status_prv",3);set("io_core_resp_ready",1);set("io_dmem_req_ready",1);set("auto_atl_out_a_ready",edge>=2&&(!astall||edge%astall!=0));
  set("io_core_ex_vconfig_vl",vl);set("io_core_ex_vconfig_vtype_vsew",2);set("io_core_ex_vconfig_vtype_vlmul_mag",mag);set("io_core_ex_vconfig_vtype_vma",1);set("io_core_ex_vconfig_vtype_vta",1);set("io_tlb_s1_resp_paddr",tlb);
  bool valid=edge>=130&&phase<3&&!waiting&&ordinal<(phase==0?3:phase==1?count:1);unsigned inst=phase==0?(0x5e004057U|(10U<<15)|((8+8*ordinal)<<7)):phase==1?0x02056407U:0x02056427U;unsigned pc=0x80001000+phase*0x100+(phase==1?0:4*ordinal);
  set("io_core_ex_valid",valid);set("io_core_ex_inst",inst);set("io_core_ex_pc",pc);set("io_core_ex_rs1",phase==0?(ordinal==1?1:0):phase==1?base:outbase);
  if(active<0&&!replies.empty()&&edge>=lastD+gap){if(reverse){for(int i=int(replies.size())-1;i>=0;--i)if(replies[i].due<=edge){active=i;break;}}else if(replies.front().due<=edge)active=0;}
  bool dv=active>=0&&edge>=lastD+gap;set("auto_atl_out_d_valid",dv);
  if(active>=0){auto&r=replies.at(active);set("auto_atl_out_d_bits_opcode",r.opcode);set("auto_atl_out_d_bits_source",r.source);set("auto_atl_out_d_bits_size",r.size);if(r.opcode==1)set("auto_atl_out_d_bits_data",responseword(r.address+8*r.beat));}
  unit.evaluate(in);auto out=unit.sample();auto ov=[&](const char*n){need(oi.count(n),std::string("missing output ")+n);return out.words.at(oi.at(n).front());};auto a=unit.sample_activity(edge),x=unit.sample_ownership(edge);
  auto v=[&](const std::string&n)->uint64_t{if(auto k=ai.find(n);k!=ai.end())return a.words.at(k->second.front());need(xi.count(n),"missing activity/ownership "+n);return x.words.at(xi.at(n).front());};
  auto wide=[&](const std::string&n){std::array<uint64_t,4>r{};if(auto k=ai.find(n);k!=ai.end()){for(unsigned idx:k->second)r.at(af[idx].word_offset/64)=a.words.at(idx);}else{need(xi.count(n),"missing wide activity/ownership "+n);for(unsigned idx:xi.at(n))r.at(xf[idx].word_offset/64)=x.words.at(idx);}return r;};
  const bool ex=valid&&ov("io_core_ex_ready"),ap=ov("auto_atl_out_a_valid")&&in.words.at(ii.at("auto_atl_out_a_ready").front()),dp=dv&&ov("auto_atl_out_d_ready");
  uint64_t nexttlb=ov("io_tlb_req_valid")?ov("io_tlb_req_bits_vaddr"):tlb;
  if(edge>=130){
   need(!ov("io_core_wb_xcpt")&&!ov("io_dmem_req_valid"),"unexpected exception/dormant Hella request");
   if(ex){need(!waiting,"duplicate CPU front acceptance");waiting=true;++accepted;std::cout<<"EX "<<edge<<' '<<phase<<' '<<ordinal<<' '<<pc<<' '<<inst<<'\n';}
   bool wb=ov("io_core_wb_retire"),rp=ov("io_core_wb_replay");need(!(wb&&rp),"simultaneous retire and CPU replay");
   if(wb||rp){need(waiting,"WB outcome without a live CPU front");need(ov("io_core_wb_pc")==pc,"WB PC ownership mismatch");waiting=false;if(wb){++retired;++ordinal;}else ++replays;std::cout<<(wb?"WB ":"REPLAY ")<<edge<<' '<<phase<<' '<<ordinal<<'\n';}
   unsigned liq=0;for(unsigned n=0;n<4;++n)liq+=v("vmu.liq_valids_"+std::to_string(n));peakliq=std::max(peakliq,liq);const unsigned qp=(v("vmu.lifq.enq_ptr_value")-v("vmu.lifq.deq_ptr_value"))&31;const unsigned qocc=qp?qp:(v("vmu.lifq.maybe_full")?32:0);peaklob=std::max(peaklob,qocc);peakreader=std::max(peakreader,unsigned(v("tl_if.reader.inflights")));full+=v("vmu.lifq.maybe_full");stall+=v("vu.vrf.io_load_write_valid")&&!v("vu.vrf.io_load_write_ready");
   bool w=v("vu.vrf.vrf.vrf_0.write_valid");if(w){unsigned eg=v("vu.vrf.vrf.vrf_0.write_bits_eg");need(eg<32,"physical VRF EG bounds");auto data=wide("vu.vrf.vrf.vrf_0.write_bits_data"),mask=wide("vu.vrf.vrf.vrf_0.write_bits_mask");for(unsigned n=0;n<4;++n){shadow[eg][n]=(shadow[eg][n]&~mask[n])|(data[n]&mask[n]);known[eg][n]|=mask[n];}++writebeats;}
   if(v("vu.vrf.io_load_write_valid")&&v("vu.vrf.io_load_write_ready"))++loadwrites;
   if(v("tl_if.io_vec_load_req_valid")&&v("tl_if.io_vec_load_req_ready"))std::cout<<"LREQ "<<edge<<' '<<v("tl_if.io_vec_load_req_bits_tag")<<' '<<v("tl_if.io_vec_load_req_bits_addr")<<'\n';if(v("tl_if.io_vec_load_resp_valid"))std::cout<<"LRESP "<<edge<<' '<<v("tl_if.io_vec_load_resp_bits_tag")<<'\n';
   std::cout<<"STATE "<<edge<<' '<<phase<<' '<<ordinal<<' '<<waiting<<' '<<ov("io_core_backend_busy")<<' '<<liq<<' '<<qocc<<' '<<v("tl_if.reader.inflights")<<' '<<owned.size()<<' '<<v("vmu.lss.io_valid")<<' '<<v("vmu.lss.io_compactor_valid")<<' '<<v("vu.vrf.io_load_write_valid")<<' '<<v("vu.vrf.io_load_write_ready")<<'\n';
  }
  std::optional<Pending>fresh;
  if(ap){unsigned op=ov("auto_atl_out_a_bits_opcode"),src=ov("auto_atl_out_a_bits_source"),size=ov("auto_atl_out_a_bits_size");uint64_t addr=ov("auto_atl_out_a_bits_address");need(size==5,"configured Rocket vector32B transaction expected edge="+std::to_string(edge)+" size="+std::to_string(size)+" opcode="+std::to_string(op));if(first==~0u)first=edge;last=edge;
   std::cout<<"A "<<edge<<' '<<op<<' '<<src<<' '<<size<<' '<<addr<<'\n';
   if(op==4){need(addr>=base&&addr+32<=base+bytes&&!(addr&31),"Get backing ownership/address");need(owned.insert(src).second,"Get source reused before response completed");fresh=Pending{src,size,1,0,edge+delay,addr};++gets;}
   else{need(op==0||op==1,"unsupported TL opcode");if(!put){need(addr>=outbase&&addr+32<=outbase+bytes,"Put output bounds");need(owned.insert(src).second,"Put source reused before ack");put=Pending{src,size,0,0,edge+delay,addr};}need(src==put->source&&addr==put->address&&size==put->size,"Put message interleaving");uint64_t data=ov("auto_atl_out_a_bits_data"),mask=ov("auto_atl_out_a_bits_mask");for(unsigned b=0;b<8;++b)if(mask&(1U<<b)){uint64_t sourceadr=base+(addr-outbase)+put->beat*8+b;need(uint8_t(data>>(8*b))==expectedbyte(sourceadr),"actual VSE readback payload mismatch");++storebytes;}if(++put->beat==4){fresh=put;fresh->beat=0;fresh->due=edge+delay;put.reset();++puts;}}
  }
  if(dp){need(active>=0&&owned.count(replies.at(active).source),"D without accepted A owner");std::cout<<"D "<<edge<<' '<<replies[active].source<<' '<<replies[active].beat<<'\n';}
  unit.commit();tlb=nexttlb;
  if(dp){lastD=edge;auto&r=replies.at(active);if(r.opcode==1){++dbeats;++r.beat;}else{++acks;r.beat=4;}if(r.beat==4){owned.erase(r.source);replies.erase(replies.begin()+active);active=-1;}}
  if(fresh)replies.push_back(*fresh);peak=std::max(peak,unsigned(owned.size()));
  bool drained=!ov("io_core_backend_busy")&&!ov("io_core_trap_check_busy")&&owned.empty()&&replies.empty()&&!put&&!waiting;
  if(edge>=130&&phase==0&&ordinal==3&&drained){phase=1;ordinal=0;}
  if(edge>=130&&phase==1&&ordinal==count&&drained){
   for(unsigned b=0;b<bytes;++b){unsigned eg=8+b/32,w=(b%32)/8,shift=(b%8)*8;need((known[eg][w]>>shift&255)==255,"final load destination not fully known by actual writes");need(uint8_t(shadow[eg][w]>>shift)==expectedbyte(base+b),"final physical VRF-write ledger disagrees with backing");}
   phase=2;ordinal=0;
  }
  if(phase==2&&ordinal==1&&drained)++idle;else idle=0;
  if(idle==4){done=edge;break;}
 }
 need(done!=~0u,"bounded source fixture did not drain");need(gets==count*bytes/32&&dbeats==gets*4&&puts==bytes/32&&acks==puts&&storebytes==bytes,"source physical message/count mismatch");need(loadwrites==count*bytes/32,"one accepted256-bit VRF load write per source32B block");
 std::cerr<<"{\"pass\":true,\"lmul\":"<<lm<<",\"VL\":"<<vl<<",\"bytes\":"<<bytes<<",\"count\":"<<count<<",\"delay\":"<<delay<<",\"D_gap\":"<<gap<<",\"A_stall_period\":"<<astall<<",\"reverse_response_transactions\":"<<reverse<<",\"seed\":"<<seed<<",\"initialized_by_actual_VMV\":"<<init<<",\"front_attempts\":"<<accepted<<",\"retired\":"<<retired<<",\"CPU_replays\":"<<replays<<",\"Gets\":"<<gets<<",\"D_data_beats\":"<<dbeats<<",\"Put_messages\":"<<puts<<",\"D_acks\":"<<acks<<",\"checked_store_bytes\":"<<storebytes<<",\"accepted_load_VRF_writes\":"<<loadwrites<<",\"all_physical_VRF_writes\":"<<writebeats<<",\"peak_external_owned\":"<<peak<<",\"peak_LIQ\":"<<peakliq<<",\"peak_LOB\":"<<peaklob<<",\"peak_reader_inflights_raw5\":"<<peakreader<<",\"LOB_maybe_full_edges\":"<<full<<",\"VRF_load_write_blocked_edges\":"<<stall<<",\"first_A\":"<<first<<",\"last_A\":"<<last<<",\"done_edge\":"<<done<<"}\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
