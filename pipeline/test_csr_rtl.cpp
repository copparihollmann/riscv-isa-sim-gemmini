#include "VCsrPair.h"
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

struct Op {const char* name;unsigned funct3,rsfield,rd;uint64_t value;};
struct Probe {
  VCsrPair rtl;
  unsigned cycle=0;
  void tick(){rtl.clock=0;rtl.eval();rtl.clock=1;rtl.eval();++cycle;}
  void reset(){rtl.reset=1;rtl.shuttle_cmd=rtl.rocket_cmd=0;rtl.shuttle_retire=rtl.rocket_retire=0;tick();tick();rtl.reset=0;rtl.clock=0;rtl.eval();cycle=0;}
  uint64_t read(unsigned address,bool rocket){rtl.address=address;rtl.shuttle_cmd=rtl.rocket_cmd=2;rtl.eval();return rocket?rtl.rocket_data:rtl.shuttle_data;}
  void transaction(std::string tag,unsigned address,const Op& op,unsigned sretire=1,unsigned rretire=1,bool core_routing=true){
    uint64_t smc=read(0xb00,false),sir=read(0xb02,false),sinhibit=read(0x320,false);
    uint64_t rmc=read(0xb00,true),rir=read(0xb02,true),rinhibit=read(0x320,true);
    const unsigned base=op.funct3==0?0:op.funct3==1||op.funct3==5?5:op.funct3==2||op.funct3==6?6:7;
    const bool readonly=(base==6||base==7)&&op.rsfield==0;
    const uint32_t instruction=(address<<20)|(op.rsfield<<15)|(op.funct3<<12)|(op.rd<<7)|0x73;
    rtl.instruction=instruction;rtl.address=address;rtl.write_data=op.value;
    rtl.shuttle_cmd=base;rtl.rocket_cmd=core_routing&&readonly?2:base;rtl.eval();
    const bool sillegal=rtl.shuttle_read_illegal||(!readonly&&base>=4&&rtl.shuttle_write_illegal);
    const bool rillegal=rtl.rocket_read_illegal||(!readonly&&base>=4&&rtl.rocket_write_illegal);
    if(core_routing&&sillegal){rtl.shuttle_cmd&=3;sretire=0;}
    if(core_routing&&rillegal){rtl.rocket_cmd&=3;rretire=0;}
    rtl.shuttle_retire=sretire;rtl.rocket_retire=rretire;rtl.eval();
    const auto scmd=rtl.shuttle_cmd,rcmd=rtl.rocket_cmd;
    const uint64_t sread=rtl.shuttle_data,rread=rtl.rocket_data;
    tick();
    uint64_t samc=read(0xb00,false),sair=read(0xb02,false),sainhibit=read(0x320,false);
    uint64_t ramc=read(0xb00,true),rair=read(0xb02,true),rainhibit=read(0x320,true);
    std::cout<<"{\"tag\":\""<<tag<<"\",\"op\":\""<<op.name<<"\",\"cycle\":"<<cycle<<",\"address\":"<<address<<",\"instruction\":"<<instruction
      <<",\"write_data\":"<<op.value<<",\"shuttle_cmd\":"<<unsigned(scmd)<<",\"rocket_cmd\":"<<unsigned(rcmd)
      <<",\"shuttle_retire\":"<<sretire<<",\"rocket_retire\":"<<rretire<<",\"shuttle_illegal\":"<<sillegal<<",\"rocket_illegal\":"<<rillegal
      <<",\"shuttle_read\":"<<sread<<",\"rocket_read\":"<<rread
      <<",\"shuttle_before\":["<<smc<<','<<sir<<','<<sinhibit<<"],\"shuttle_after\":["<<samc<<','<<sair<<','<<sainhibit
      <<"],\"rocket_before\":["<<rmc<<','<<rir<<','<<rinhibit<<"],\"rocket_after\":["<<ramc<<','<<rair<<','<<rainhibit<<"]}\n";
  }
};

int main(){
  const Op nop={"noCSR",0,0,0,0},write={"CSRRW_rd0",1,5,0,100};
  const std::vector<Op> ops={{"CSRRS_x0",2,0,6,0},{"CSRRC_x0",3,0,6,0},{"CSRRSI_0",6,0,6,0},{"CSRRCI_0",7,0,6,0},
    {"CSRRW_rd0",1,5,0,100},{"CSRRWI_rd0_0",5,0,0,0},{"CSRRS_t0_value0",2,5,6,0},{"CSRRC_t0_value0",3,5,6,0},
    {"CSRRSI_1",6,1,6,1},{"CSRRCI_1",7,1,6,1}};
  for(unsigned address:{0xb00u,0xb02u,0xc00u,0xc02u})for(const auto& op:ops){
    Probe p;p.reset();
    p.transaction("setup_mcycle",0xb00,{"CSRRW_rd0",1,5,0,1000},0,0);
    p.transaction("setup_minstret",0xb02,write,0,0);
    p.transaction("instruction_matrix",address,op);
    p.transaction("following_instruction",0xb00,nop);
  }
  for(unsigned address:{0xb00u,0xb02u,0xc00u,0xc02u})for(unsigned index=0;index<4;++index){
    Probe p;p.reset();
    p.transaction("bracket_open",address,ops[index]);
    for(unsigned i=0;i<256;++i)p.transaction("body256",0xb00,nop);
    p.transaction("bracket_close",address,ops[index]);
  }
  {Probe p;p.reset();p.transaction("macro_cycle_open",0xb00,ops[0]);p.transaction("macro_instret_open",0xb02,ops[0]);
   for(unsigned i=0;i<256;++i)p.transaction("macro_body256",0xb00,nop);
   p.transaction("macro_instret_close",0xb02,ops[0]);p.transaction("macro_cycle_close",0xb00,ops[0]);}
  for(unsigned bits:{1u,4u,5u,7u}){
    Probe p;p.reset();p.transaction("inhibit_set",0x320,{"CSRRW_rd0",1,5,0,bits});
    for(unsigned i=0;i<3;++i)p.transaction("inhibited_body",0xb00,nop);
    p.transaction("inhibited_write_cycle",0xb00,{"CSRRW_rd0",1,5,0,900});
    p.transaction("inhibited_write_instret",0xb02,{"CSRRW_rd0",1,5,0,700});
    p.transaction("inhibit_clear",0x320,{"CSRRW_rd0",1,5,0,0});
    p.transaction("resumed_body",0xb00,nop);
  }
  {Probe p;p.reset();p.transaction("wrap_setup",0xb02,{"CSRRW_rd0",1,5,0,UINT64_MAX},0,0);
   p.transaction("dual_retire_wrap",0xb00,nop,2,1);}
}
