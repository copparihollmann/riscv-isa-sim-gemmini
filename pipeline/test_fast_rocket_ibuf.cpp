#include "fast_rocket_ibuf.hpp"
#include "VIBuf.h"
#include "verilated.h"
#include <iostream>
#include <random>
#include <stdexcept>
using Model=iris::frontend::FastRocketIBuf;
int main(int argc,char**argv){
 const unsigned seed=argc>1?std::stoul(argv[1]):1,edges=argc>2?std::stoul(argv[2]):100000;
 VerilatedContext context;context.randSeed(seed);context.randReset(2);context.threads(1);Verilated::threadContextp(&context);VIBuf rtl(&context);Model model;std::mt19937_64 random(seed);uint64_t checks=0,partial=0,replays=0,kills=0,accepted=0;
 auto drive=[&](const Model::Inputs&i){rtl.clock=0;rtl.reset=i.reset;rtl.io_imem_valid=i.valid;rtl.io_inst_0_ready=i.ready;rtl.io_kill=i.kill;const auto&p=i.packet;rtl.io_imem_bits_pc=p.pc;rtl.io_imem_bits_data=p.data;rtl.io_imem_bits_btb_taken=p.taken;rtl.io_imem_bits_btb_bridx=p.branch_index;rtl.io_imem_bits_btb_entry=p.entry;rtl.io_imem_bits_btb_bht_history=p.history;rtl.io_imem_bits_replay=p.replay;rtl.io_imem_bits_xcpt_pf_inst=p.exception.page;rtl.io_imem_bits_xcpt_gf_inst=p.exception.guest_page;rtl.io_imem_bits_xcpt_ae_inst=p.exception.access;rtl.eval();};
 auto edge=[&]{rtl.clock=1;rtl.eval();rtl.clock=0;rtl.eval();model.commit();};
 Model::Inputs input;input.reset=true;input.packet.known=0xffffffffu;
 for(unsigned n=0;n<2;++n){drive(input);model.evaluate(input);edge();}
 input.reset=false;bool held=false;
 for(unsigned tick=0;tick<edges;++tick){
  if(!held){input.valid=(random()%5)!=0;auto&p=input.packet;p.pc=0x80000000ull+(random()%2048)*2;p.data=uint32_t(random());p.known=0xffffffffu;p.taken=random()&1;p.branch_index=((p.pc>>1)&1)||(random()&1);p.entry=random()%32;p.history=random()%256;p.replay=random()%11==0;p.exception={random()%31==0,random()%43==0,random()%37==0};}
  input.ready=random()%4!=0;input.kill=random()%97==0;input.reset=tick%997==996;drive(input);auto out=model.evaluate(input);
  auto check=[&](uint64_t a,uint64_t b,const char*field){if(a!=b){std::cerr<<"MISMATCH seed="<<seed<<" edge="<<tick<<" field="<<field<<" model="<<a<<" RTL="<<b<<" pc="<<std::hex<<input.packet.pc<<" raw="<<input.packet.data<<std::dec<<" valid="<<input.valid<<" ready="<<input.ready<<'\n';throw std::runtime_error("source IBuf differential");}++checks;};
  check(out.imem_ready,rtl.io_imem_ready,"ready");check(out.valid,rtl.io_inst_0_valid,"valid");check(out.pc,rtl.io_pc,"pc");check(out.raw,rtl.io_inst_0_bits_raw,"raw");check(out.expanded,rtl.io_inst_0_bits_inst_bits,"expanded");check(out.compressed,rtl.io_inst_0_bits_rvc,"rvc");check(out.replay,rtl.io_inst_0_bits_replay,"replay");check(out.entry,rtl.io_btb_resp_entry,"BTBentry");check(out.history,rtl.io_btb_resp_bht_history,"BHThistory");
  check(out.first.page,rtl.io_inst_0_bits_xcpt0_pf_inst,"firstPF");check(out.first.guest_page,rtl.io_inst_0_bits_xcpt0_gf_inst,"firstGF");check(out.first.access,rtl.io_inst_0_bits_xcpt0_ae_inst,"firstAE");check(out.second.page,rtl.io_inst_0_bits_xcpt1_pf_inst,"secondPF");check(out.second.guest_page,rtl.io_inst_0_bits_xcpt1_gf_inst,"secondGF");check(out.second.access,rtl.io_inst_0_bits_xcpt1_ae_inst,"secondAE");
  check(out.rd,rtl.io_inst_0_bits_inst_rd,"rd");check(out.rs1,rtl.io_inst_0_bits_inst_rs1,"rs1");check(out.rs2,rtl.io_inst_0_bits_inst_rs2,"rs2");check(out.rs3,rtl.io_inst_0_bits_inst_rs3,"rs3");
  // Re-evaluation of a held edge is side-effect free, even if ready changes.
  const auto again=model.evaluate(input);check(again.raw,out.raw,"re-evaluate raw");check(again.valid,out.valid,"re-evaluate valid");
  if(input.valid&&!out.valid)++partial;if(out.valid&&out.replay)++replays;if(input.kill)++kills;if(out.valid&&input.ready)++accepted;
  held=input.valid&&!out.imem_ready&&!input.kill&&!input.reset;edge();
 }
 std::cout<<"PASS seed="<<seed<<" edges="<<edges<<" checks="<<checks<<" partial="<<partial<<" replays="<<replays<<" kills="<<kills<<" accepted="<<accepted<<'\n';
}
