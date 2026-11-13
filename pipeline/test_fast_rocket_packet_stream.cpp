#include "fast_rocket_packets.hpp"
#include "fast_source_rvc_table.hpp"
#include "VIBuf.h"
#include "verilated.h"
#include "cases.hpp"
#include <iostream>
#include <stdexcept>
using Flow=iris::frontend::FastRocketPackets;
static int64_t branch_imm(uint32_t x){uint32_t v=((x>>31)<<12)|(((x>>7)&1)<<11)|(((x>>25)&63)<<5)|(((x>>8)&15)<<1);return int64_t(int32_t(v<<19)>>19);}
int main(){unsigned checks=0;for(unsigned c=0;c<64;++c){const auto&t=packet_cases[c];Flow model(1,t.pc);VerilatedContext context;context.randReset(2);context.randSeed(17);context.threads(1);Verilated::threadContextp(&context);VIBuf rtl(&context);
 auto drive=[&](const iris::frontend::FastRocketIBuf::Inputs&i){rtl.clock=0;rtl.reset=i.reset;rtl.io_imem_valid=i.valid;rtl.io_inst_0_ready=i.ready;rtl.io_kill=i.kill;const auto&p=i.packet;rtl.io_imem_bits_pc=p.pc;rtl.io_imem_bits_data=p.data;rtl.io_imem_bits_btb_taken=p.taken;rtl.io_imem_bits_btb_bridx=p.branch_index;rtl.io_imem_bits_btb_entry=p.entry;rtl.io_imem_bits_btb_bht_history=p.history;rtl.io_imem_bits_replay=p.replay;rtl.io_imem_bits_xcpt_pf_inst=p.exception.page;rtl.io_imem_bits_xcpt_gf_inst=p.exception.guest_page;rtl.io_imem_bits_xcpt_ae_inst=p.exception.access;rtl.eval();};
 iris::frontend::FastRocketIBuf::Inputs reset;reset.reset=true;for(unsigned i=0;i<2;++i){drive(reset);rtl.clock=1;rtl.eval();rtl.clock=0;rtl.eval();}
 auto read=[&](uint64_t address){if(address<t.base||(address-t.base)/4>=t.count||address&3)throw std::runtime_error("ELF stream word route");return Flow::Word{t.words[(address-t.base)/4],0xffffffffu};};
 // The fixture is an explicitly warm, correctly predicted backward-branch
 // stream. The target comes from opcode bits, never a PC/cycle lookup.
 auto predict=[](uint64_t pc,uint32_t raw,unsigned bytes){const auto x=iris::frontend::expand_source_rvc(raw);return (x&127)==0x63&&branch_imm(x)<0?pc+branch_imm(x):pc+bytes;};
 unsigned retired=0;uint64_t tick=0;while(retired<3*128&&tick<2048){const unsigned lane=retired%3;uint64_t pc=t.pc;for(unsigned i=0;i<lane;++i)pc+=t.widths[i];const bool ready=model.prepare(tick,pc,t.raw[lane],t.widths[lane],read,predict);if(ready)model.consume(tick);drive(model.inputs());const auto out=model.outputs();
 auto check=[&](uint64_t x,uint64_t y){if(x!=y){std::cerr<<"case="<<c<<" tick="<<tick<<" RTL="<<y<<" model="<<x<<'\n';throw std::runtime_error("source stream port differential");}++checks;};
 check(out.valid,rtl.io_inst_0_valid);if(out.ready_known)check(out.imem_ready,rtl.io_imem_ready);if(out.valid){check(out.pc,rtl.io_pc);check(out.compressed,rtl.io_inst_0_bits_rvc);check(out.expanded,rtl.io_inst_0_bits_inst_bits);check(out.raw&(out.compressed?65535:0xffffffffu),rtl.io_inst_0_bits_raw&(out.compressed?65535:0xffffffffu));}
 const bool word_fire=rtl.io_imem_valid&&rtl.io_imem_ready;rtl.clock=1;rtl.eval();rtl.clock=0;rtl.eval();auto edge=model.finish(tick);if(!edge)throw std::runtime_error("missing offered source edge");check(edge->word.has_value(),word_fire);check(edge->instruction.has_value(),ready);if(edge->instruction){check(edge->instruction->pc,pc);++retired;}++tick;
 }
 if(retired!=3*128)throw std::runtime_error("stream did not progress");std::cout<<"case="<<c<<" cycles="<<tick<<" words="<<model.metrics().words<<" partial="<<model.metrics().partial_edges<<'\n';}
 std::cout<<"PASS cases=64 checks="<<checks<<'\n';}
