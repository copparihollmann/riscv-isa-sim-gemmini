#include "VShuttleFrontend.h"
#include "verilated.h"
#include <chrono>
#include <cstdint>
#include <iostream>
#include <optional>
#include <stdexcept>

struct Refill {uint64_t line;unsigned accepted_at,beat=0;};
static uint8_t program_byte(uint64_t address) {
  static constexpr uint8_t bytes[]={0x05,0x03,0x93,0x82,0x12,0x00};
  if(address<0x10000 || address>=0x11000)throw std::runtime_error("synthetic ROM lookup outside qualified source PMA");
  return bytes[(address-0x10000)%6];
}
int main() {
  VerilatedContext context;context.randSeed(1);context.randReset(2);context.threads(1);
  VShuttleFrontend dut(&context);
  // Generated from the actual module input list. Reset alone, rather than
  // internal source-state writes, initializes the frontend.
#include "zero_inputs.inc"
  dut.io_ptw_status_prv=3;dut.io_ptw_ptbr_mode=0;
  auto edge=[&] {dut.clock=1;dut.eval();context.timeInc(1);dut.clock=0;dut.eval();context.timeInc(1);};
  dut.reset=1;for(unsigned i=0;i<16;++i)edge();dut.reset=0;
  std::optional<Refill> refill;uint64_t expected_pc=0x10000;unsigned retired_from_queue=0,requests=0,beats=0;
  for(unsigned cycle=0;cycle<10000 && retired_from_queue<256;++cycle) {
    dut.auto_icache_master_out_a_ready=1;
    dut.io_cpu_resp_0_ready=(cycle%11)<8;dut.io_cpu_resp_1_ready=dut.io_cpu_resp_0_ready;
    const bool returning=refill && cycle>=refill->accepted_at+3;
    dut.auto_icache_master_out_d_valid=returning;
    dut.auto_icache_master_out_d_bits_opcode=1;dut.auto_icache_master_out_d_bits_size=6;
    if(returning) {
      uint64_t value=0;for(unsigned b=0;b<8;++b)value|=uint64_t(program_byte(refill->line+refill->beat*8+b))<<(b*8);
      dut.auto_icache_master_out_d_bits_data=value;
    }
    dut.eval();
    if(dut.io_ptw_req_valid)throw std::runtime_error("M-mode source frontend unexpectedly requested a walk");
    if(dut.auto_icache_master_out_a_valid) {
      if(refill)throw std::runtime_error("frontend overlapped a second source refill");
      if(dut.auto_icache_master_out_a_bits_address&63)throw std::runtime_error("source Get not64B aligned");
      refill=Refill{dut.auto_icache_master_out_a_bits_address,cycle,0};++requests;
    }
    auto consume=[&](bool valid,bool ready,uint64_t pc,uint32_t raw,uint32_t expanded,bool xcpt) {
      if(!valid || !ready)return;
      if(xcpt || pc!=expected_pc)throw std::runtime_error("source frontend lost/duplicated/reordered mixed parcels atpc="+std::to_string(pc));
      const bool compressed=(expected_pc-0x10000)%6==0;
      if((compressed?uint16_t(raw):raw)!=(compressed?0x0305u:0x00128293u) || expanded!=(compressed?0x00130313u:0x00128293u))throw std::runtime_error("source frontend raw/RVC-expanded value differs");
      expected_pc+=compressed?2:4;++retired_from_queue;
    };
    consume(dut.io_cpu_resp_0_valid,dut.io_cpu_resp_0_ready,dut.io_cpu_resp_0_bits_pc,dut.io_cpu_resp_0_bits_raw_inst,dut.io_cpu_resp_0_bits_inst,dut.io_cpu_resp_0_bits_xcpt);
    consume(dut.io_cpu_resp_1_valid,dut.io_cpu_resp_1_ready,dut.io_cpu_resp_1_bits_pc,dut.io_cpu_resp_1_bits_raw_inst,dut.io_cpu_resp_1_bits_inst,dut.io_cpu_resp_1_bits_xcpt);
    edge();
    if(returning) {++beats;if(++refill->beat==8)refill.reset();}
  }
  if(retired_from_queue<256 || requests<10 || beats<80)throw std::runtime_error("incomplete full-frontend mixed parcel/refill exercise");
  // No undocumented service fallback: withholding Aready produces an actual
  // outstanding source request, which the eventual live adapter must refuse
  // if its miss service is unknown. This unit supplies only a synthetic peer.
  dut.io_cpu_resp_0_ready=0;dut.io_cpu_resp_1_ready=0;dut.auto_icache_master_out_a_ready=0;dut.auto_icache_master_out_d_valid=0;
  constexpr unsigned benchmark_edges=100000;const auto begin=std::chrono::steady_clock::now();
  for(unsigned i=0;i<benchmark_edges;++i)edge();
  const auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
  std::cout<<"{\"status\":\"passed_source_full_frontend_mixed_parcels\",\"consumed_uops\":"<<retired_from_queue<<",\"requests\":"<<requests<<",\"data_beats\":"<<beats
           <<",\"synthetic_first_beat_delay\":3,\"benchmark_edges\":"<<benchmark_edges<<",\"benchmark_seconds\":"<<seconds<<",\"frontend_edges_per_second\":"<<benchmark_edges/seconds
           <<",\"native_integration\":false,\"calibrated\":false,\"ethan_image_association_verified\":false}\n";
}
