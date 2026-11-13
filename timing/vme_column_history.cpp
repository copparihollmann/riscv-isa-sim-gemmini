// Source OPU-sequencer + full array, with Backend.scala379-416,446-449 glue.
#include "VOPUSequencer.h"
#include "VOuterArray.h"
#include "VColumnBackendRegs.h"
#include <verilated.h>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <vector>
struct Command {unsigned column,tile,index,vd;};
struct Scenario {unsigned id,policy;std::vector<Command> commands;};
struct Controls {
 std::array<unsigned,4> mrf{},row{},col{},macc{},zero{},mvin{},mvin_col{},mv_en{},shift{};
 std::array<std::array<unsigned,4>,4> left{},top{},row_en{},col_en{};
 unsigned signed_l=0,signed_t=0,fp8=0,e5m2_l=0,e5m2_t=0,rm=0;
};
class Fixture {
 public:
 VOPUSequencer seq;VOuterArray array;VColumnBackendRegs glue;uint64_t backend_register_checks=0;
#include "vme_column_history_bindings.inc"
 Controls control{};std::array<uint32_t,4> readout{};uint64_t edge=0,init_writes=0,scans=0,known_readout_checks=0,unqualified_capture_checks=0;bool initialized=false,readout_known=false;
 static uint32_t pattern(unsigned slot,unsigned pr,unsigned pc){
  const unsigned tile=slot/4,subr=(slot/2)%2,subc=slot%2;
  const unsigned row=subr*16+(pr%4)*4+pr/4,col=subc*16+(pc%4)*4+pc/4;
  return tile*0x10000+row*64+col;
 }
 void defaults(){seq.io_dis_valid=0;seq.io_dis_bits_bits=0;seq.io_dis_bits_vconfig_vl=32;seq.io_dis_bits_vconfig_vtype_tm=32;seq.io_dis_bits_vconfig_vtype_tk=1;seq.io_dis_bits_vconfig_vtype_altfmt=0;seq.io_dis_bits_vconfig_vtype_vsew=2;seq.io_dis_bits_rs1_data=0;seq.io_dis_bits_vat=0;seq.io_dis_bits_rm=0;seq.io_dis_bits_emul=2;seq.io_older_writes=0;seq.io_older_reads=0;seq.io_vat_head=0;seq.io_rvs1_ready=1;seq.io_rvs2_ready=1;seq.io_pipe_write_req_available=1;}
 void settle(const Controls& c){seq.clock=0;array.clock=0;glue.clock=0;drive(c);seq.eval();array.eval();glue_inputs();glue.eval();}
 void commit(const Controls& next,const std::optional<Controls>& direct={}){
  const bool capture=seq.io_write_reg_enable;std::array<uint32_t,4> captured{};for(unsigned j=0;j<4;++j)captured[j]=*out[j];
  seq.clock=1;array.clock=1;glue.clock=1;seq.eval();array.eval();glue.eval();++edge;
  if(capture){readout=captured;readout_known=initialized;for(unsigned j=0;j<4;++j){if(readout[j]!=glue.vrf_io_pipe_writes_2_bits_data_r[j])throw std::runtime_error("source Backend RegEnable phase mismatch");++backend_register_checks;if(initialized)++known_readout_checks;else ++unqualified_capture_checks;}}control=next;if(!direct)glue_compare(control);seq.clock=0;array.clock=0;glue.clock=0;drive(direct?*direct:control);seq.eval();array.eval();glue_inputs();glue.eval();
 }
 void physical_tick(const Controls& c){settle(c);commit(c,c);}
 Fixture(){defaults();seq.reset=1;array.reset=1;physical_tick({});physical_tick({});seq.reset=0;array.reset=0;initialize();}
 void initialize(){
  for(unsigned slot=0;slot<16;++slot)for(unsigned pr=0;pr<16;++pr)for(unsigned lc=0;lc<4;++lc){Controls c;for(unsigned cr=0;cr<4;++cr){c.mrf[cr]=slot;c.row[cr]=pr%4;c.col[cr]=lc;c.mvin[cr]=cr==pr/4;c.mv_en[cr]=1;for(unsigned j=0;j<4;++j)c.row_en[cr][j]=c.col_en[cr][j]=1;}
   for(unsigned cc=0;cc<4;++cc){uint32_t v=pattern(slot,pr,cc*4+lc);for(unsigned b=0;b<4;++b)c.top[cc][b]=(v>>(8*b))&255;}physical_tick(c);init_writes+=4;
  }
  // Full known physical-word scan through real vertical registers, no state peeks.
  for(unsigned slot=0;slot<16;++slot)for(unsigned lr=0;lr<4;++lr)for(unsigned lc=0;lc<4;++lc){Controls c;for(unsigned cr=0;cr<4;++cr){c.mrf[cr]=slot;c.row[cr]=lr;c.col[cr]=lc;}physical_tick(c);
   for(unsigned n=0;n<4;++n){for(unsigned cc=0;cc<4;++cc){auto actual=*out[cc],expected=pattern(slot,(3-n)*4+lr,cc*4+lc);if(actual!=expected)throw std::runtime_error("physical initialization scan mismatch");++scans;}for(unsigned cr=1;cr<4;++cr)c.shift[cr]=1;if(n<3)physical_tick(c);}
  }
  physical_tick({});control={};initialized=true;
 }
 void run(const Scenario&s){
  defaults();seq.reset=1;for(unsigned n=0;n<3;++n){settle(control);commit(snapshot());}seq.reset=0;
  unsigned dispatched=0,issued=0,writes=0;std::optional<unsigned> current;uint64_t local=0;
  std::cout<<"CASE "<<s.id<<' '<<s.policy<<' '<<edge<<' '<<s.commands.size()<<'\n';
  while(local<200){
   defaults();seq.io_pipe_write_req_available=s.policy==0?1:s.policy==1?(local%2==0):s.policy==2?(local%5<2):(local%7!=1&&local%7!=2&&local%7!=3);
   if(dispatched<s.commands.size()){const auto&c=s.commands[dispatched];seq.io_dis_valid=1;seq.io_dis_bits_bits=0x41f06057u|(c.vd<<7)|(1u<<15);seq.io_dis_bits_rs1_data=(uint64_t(c.tile)<<29)|(uint64_t(c.column)<<24)|c.index;seq.io_dis_bits_vat=dispatched;}
   settle(control);
   if(seq.io_iss_valid){if(!current||issued>=8)throw std::runtime_error("missing source issue owner");const auto&c=s.commands[*current];std::cout<<"ISSUE "<<s.id<<' '<<edge<<' '<<*current<<' '<<issued<<' '<<c.column<<' '<<c.tile<<' '<<c.index<<' '<<c.vd<<'\n';++issued;}
   if(seq.io_write_valid){if(!initialized||!readout_known)throw std::runtime_error("undefined readout payload cannot be consumed");std::cout<<"WRITE "<<s.id<<' '<<edge<<' '<<unsigned(seq.io_write_bits);for(auto v:readout)std::cout<<' '<<v;std::cout<<'\n';++writes;}
   const bool dis=seq.io_dis_valid&&seq.io_dis_ready;if(dis){std::cout<<"DISPATCH "<<s.id<<' '<<edge<<' '<<dispatched<<'\n';current=dispatched++;issued=0;}
   auto next=snapshot();commit(next);++local;
   if(dispatched==s.commands.size()&&writes==s.commands.size()*8&&!seq.io_busy&&!seq.io_write_valid){for(unsigned n=0;n<8;++n){defaults();settle(control);commit(snapshot());}std::cout<<"END "<<s.id<<' '<<edge<<' '<<writes<<'\n';return;}
  }
  throw std::runtime_error("bounded source sequencer did not drain");
 }
};
int main(int argc,char**argv){try{if(argc!=2)throw std::runtime_error("explicit scenario file required");Verilated::commandArgs(argc,argv);Verilated::threadContextp()->threads(1);Verilated::randSeed(1);Verilated::randReset(2);Fixture f;std::ifstream in(argv[1]);unsigned id,policy,n;unsigned cases=0;while(in>>id>>policy>>n){Scenario s{id,policy,{}};if(policy>3||n<1||n>2)throw std::runtime_error("invalid case shape");for(unsigned j=0;j<n;++j){Command c;if(!(in>>c.column>>c.tile>>c.index>>c.vd)||c.column>1||c.tile>3||c.index>31||c.vd>28)throw std::runtime_error("invalid command");s.commands.push_back(c);}f.run(s);++cases;}std::cerr<<"VME_COLUMN_HISTORY_DONE cases="<<cases<<" edges="<<f.edge<<" physical_words_initialized="<<f.init_writes<<" physical_words_scanned="<<f.scans<<" backend_SV_register_checks="<<f.backend_register_checks<<" backend_known_readout_checks="<<f.known_readout_checks<<" backend_unqualified_capture_checks="<<f.unqualified_capture_checks<<'\n';return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
