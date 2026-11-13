#include "VMaxPeriodFibonacciLFSR.h"
#include "verilated.h"
#include "empirical_cache_v8.hpp"
#include <array>
#include <iostream>
#include <stdexcept>
#include <cstdint>
static void need(bool v,const char*s){if(!v)throw std::runtime_error(s);}
static uint16_t advance(uint16_t v){return uint16_t((v<<1)|(((v>>10)^(v>>12)^(v>>13)^(v>>15))&1));}
int main(){try{
 VerilatedContext ctx;ctx.threads(1);VMaxPeriodFibonacciLFSR m(&ctx);uint64_t checks=0;
 auto edge=[&](bool reset,bool inc){m.reset=reset;m.io_increment=inc;m.clock=0;m.eval();m.clock=1;m.eval();m.clock=0;m.eval();};
 auto bits=[&](){return uint16_t(m.io_out_0|(m.io_out_1<<1)|(m.io_out_2<<2)|(m.io_out_3<<3)|(m.io_out_4<<4)|(m.io_out_5<<5)|(m.io_out_6<<6)|(m.io_out_7<<7)|(m.io_out_8<<8)|(m.io_out_9<<9)|(m.io_out_10<<10)|(m.io_out_11<<11)|(m.io_out_12<<12)|(m.io_out_13<<13)|(m.io_out_14<<14)|(m.io_out_15<<15));};
 edge(true,false);uint16_t oracle=1;need(bits()==oracle,"reset");
 for(unsigned i=0;i<10000;++i){bool rst=i%997==996,inc=i%7<4;edge(rst,inc);oracle=rst?1:inc?advance(oracle):oracle;need(bits()==oracle,"source LFSR state mismatch");++checks;}
 edge(true,false);std::array<std::array<int,2>,64> tags;for(auto&s:tags)s={-1,-1};
 iris::empirical::CacheHistoryV8 model(iris::empirical::iris_geometry_v8(),true);
 unsigned collisions=0;uint64_t tick=0;
 for(unsigned i=0;i<64;++i){const auto addr=0x84000000ull+i*128;const unsigned set=(addr/64)%64,way=m.io_out_0;
  if(tags[set][way]>=0)++collisions;tags[set][way]=int(i);edge(false,true);
  auto d=model.begin({i+1,0,addr,8,true,tick++});need(d.l1_misses==1,"V8 preparation misses");model.complete(i+1,tick++);++checks;
 }
 unsigned retained=0,model_hits=0;for(unsigned i=0;i<64;++i){unsigned set=((0x84000000ull+i*128)/64)%64;if(tags[set][0]==int(i)||tags[set][1]==int(i))++retained;if(model.data_hit(0,0x84000000ull+i*128,8))++model_hits;}
 need(collisions>0&&retained<64&&model_hits==64,"conditional source/LRU divergence absent");
 std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"conditional_sequential_misses\":64,\"stride\":128,\"source_retained_nodes\":"<<retained<<",\"source_valid_victims_despite_empty_other_way\":"<<collisions<<",\"V8_LRU_ready_nodes\":"<<model_hits<<",\"actual_workload_cache_history_reproduced\":false,\"whole_DCache_simulated\":false,\"replacement_PRNG_exact_associated_SV\":true}\n";
 return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
