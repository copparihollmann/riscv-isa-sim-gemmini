#include "VIrisRocketFrontendPeer.h"
#include "verilated.h"
#include <chrono>
#include <cstdint>
#include <iostream>
#include <optional>
#include <stdexcept>
struct Refill {uint64_t line;unsigned accepted,beat=0;};
static uint8_t byte(uint64_t address) {
  static constexpr uint8_t code[]={0x05,0x03,0x93,0x82,0x12,0x00};
  if(address<0x10000 || address>=0x11000)throw std::runtime_error("source Rocket synthetic ROM outside test span");
  return code[(address-0x10000)%6];
}
int main() {
  VerilatedContext context;context.randSeed(1);context.randReset(2);context.threads(1);VIrisRocketFrontendPeer dut(&context);
#include "zero_inputs.inc"
  dut.io_ptw_status_prv=3;dut.io_ptw_ptbr_mode=0;dut.io_cpu_might_request=1;dut.io_cpu_progress=1;
  auto edge=[&]{dut.clock=1;dut.eval();context.timeInc(1);dut.clock=0;dut.eval();context.timeInc(1);};
  dut.reset=1;for(unsigned i=0;i<16;++i)edge();dut.reset=0;
  std::optional<Refill> refill;uint64_t expected_pc=0x10000;unsigned consumed=0,requests=0,beats=0,carried32=0,replays=0;std::optional<uint64_t> correction;
  for(unsigned cycle=0;cycle<20000 && consumed<512;++cycle) {
    dut.auto_icache_master_out_a_ready=1;
    dut.io_cpu_req_valid=bool(correction);if(correction)dut.io_cpu_req_bits_pc=*correction;
    dut.io_cpu_req_bits_speculative=0;correction.reset();
    dut.cpu_id_ready=cycle%11<8 && !dut.io_cpu_req_valid;
    const bool returning=refill && cycle>=refill->accepted+3;
    dut.auto_icache_master_out_d_valid=returning;dut.auto_icache_master_out_d_bits_opcode=1;dut.auto_icache_master_out_d_bits_size=6;
    if(returning){uint64_t data=0;for(unsigned b=0;b<8;++b)data|=uint64_t(byte(refill->line+refill->beat*8+b))<<(b*8);dut.auto_icache_master_out_d_bits_data=data;}
    dut.eval();
    if(dut.io_ptw_req_valid)throw std::runtime_error("M-mode Rocket frontend unexpectedly requested page walk");
    if(dut.auto_icache_master_out_a_valid) {
      if(refill || (dut.auto_icache_master_out_a_bits_address&63))throw std::runtime_error("source Rocket refill request protocol differs");
      refill=Refill{dut.auto_icache_master_out_a_bits_address,cycle,0};++requests;
    }
    if(dut.ibuf_inst_0_valid && dut.cpu_id_ready) {
      if(dut.ibuf_inst_0_bits_xcpt0_pf_inst || dut.ibuf_inst_0_bits_xcpt0_gf_inst || dut.ibuf_inst_0_bits_xcpt0_ae_inst || dut.ibuf_inst_0_bits_xcpt1_pf_inst || dut.ibuf_inst_0_bits_xcpt1_gf_inst || dut.ibuf_inst_0_bits_xcpt1_ae_inst)
        throw std::runtime_error("source Rocket frontend produced unexpected fault pc="+std::to_string(dut.ibuf_pc));
      if(dut.ibuf_inst_0_bits_replay) {correction=dut.ibuf_pc;++replays;edge();if(returning){++beats;if(++refill->beat==8)refill.reset();}continue;}
      const bool compressed=(expected_pc-0x10000)%6==0;
      if(dut.ibuf_pc!=expected_pc || bool(dut.ibuf_inst_0_bits_rvc)!=compressed || (compressed?uint16_t(dut.ibuf_inst_0_bits_raw):dut.ibuf_inst_0_bits_raw)!=(compressed?0x0305u:0x00128293u) || dut.ibuf_inst_0_bits_inst_bits!=(compressed?0x00130313u:0x00128293u))
        throw std::runtime_error("source Rocket mixed/cross-fetch parcel differs pc="+std::to_string(dut.ibuf_pc)+" expected="+std::to_string(expected_pc));
      if(!compressed && (expected_pc&3)==2)++carried32;
      expected_pc+=compressed?2:4;++consumed;
    }
    edge();if(returning){++beats;if(++refill->beat==8)refill.reset();}
  }
  if(consumed!=512 || requests<20 || beats<160 || carried32<100)throw std::runtime_error("source Rocket frontend corpus incomplete");
  dut.cpu_id_ready=0;dut.auto_icache_master_out_a_ready=0;dut.auto_icache_master_out_d_valid=0;
  const auto begin=std::chrono::steady_clock::now();constexpr unsigned count=100000;for(unsigned i=0;i<count;++i)edge();const auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
  std::cout<<"{\"status\":\"passed_source_Rocket_Frontend_IBuf_mixed_parcels\",\"consumed_uops\":"<<consumed<<",\"requests\":"<<requests<<",\"data_beats\":"<<beats<<",\"carried32_across_fetch32\":"<<carried32
           <<",\"benchmark_edges\":"<<count<<",\"benchmark_seconds\":"<<seconds<<",\"local_edges_per_second\":"<<count/seconds<<",\"synthetic_replay_corrections\":"<<replays<<",\"synthetic_replay_redirect_delay\":1,\"synthetic_first_beat_delay\":3,\"native_integration\":false,\"calibrated\":false}\n";
}
