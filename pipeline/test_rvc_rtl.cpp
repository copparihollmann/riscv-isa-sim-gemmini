#include "rvc.hpp"
#include "VRVCExpander.h"
#include <iostream>
#include <map>
#include <stdexcept>

int main() {
  VRVCExpander rtl;
  unsigned accepted=0;
  std::map<std::string,unsigned> counts;
  for(unsigned raw=0;raw<65536;++raw) {
    auto expanded=iris::shuttle::expand_compressed_alu(raw);
    rtl.io_in=raw;rtl.eval();
    if(!expanded) continue;
    if(!rtl.io_rvc || rtl.io_out_bits!=expanded->expanded) {
      std::cerr<<"RVC expansion mismatch raw="<<std::hex<<raw<<" model="<<expanded->expanded<<" RTL="<<rtl.io_out_bits<<"\n";
      return 1;
    }
    ++accepted;++counts[expanded->name];
    // Compressed expansion must depend only on its own 16 bits. The upper
    // half is another frontend halfword, not extra instruction control.
    for(uint32_t upper:{0u,0x12340000u,0xffff0000u}) {
      rtl.io_in=raw|upper;rtl.eval();
      if(rtl.io_out_bits!=expanded->expanded) throw std::runtime_error("upper halfword changed admitted expansion");
    }
  }
  std::cout<<"{\"status\":\"passed_exhaustive_RVC_ALU_expansion\",\"inputs\":65536,\"accepted\":"<<accepted<<",\"mnemonics\":{";
  bool first=true;for(auto [name,count]:counts){if(!first)std::cout<<',';first=false;std::cout<<'"'<<name<<"\":"<<count;}
  std::cout<<"},\"timing_certified\":false,\"firesim_image_association\":false}\n";
}
