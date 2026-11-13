#include "VRVCExpander.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
int main(int argc,char**argv){
 if(argc!=2)throw std::invalid_argument("new header output required");
 VRVCExpander d;std::ofstream out(argv[1]);uint64_t checks=0;
 out<<"// Functional encoding fields from exact saved RVCExpander, not timing data.\n#pragma once\n#include <array>\n#include <cstdint>\nnamespace iris::frontend {\ninline constexpr std::array<uint16_t,49152> rocket_rvc_registers={\n";
 for(unsigned q=0;q<3;++q)for(unsigned n=0;n<16384;++n){
  const uint32_t raw=(n<<2)|q;d.io_in=raw;d.eval();const unsigned expected=d.io_out_rd|(d.io_out_rs1<<5)|(d.io_out_rs2<<10);
  for(uint32_t high:{0u,0x12340000u,0xa5a50000u,0xffff0000u}){d.io_in=raw|high;d.eval();if((d.io_out_rd|(d.io_out_rs1<<5)|(d.io_out_rs2<<10))!=expected||d.io_out_rs3!=((raw|high)>>27))throw std::runtime_error("source compressed field dependence");++checks;}
  out<<"0x"<<std::hex<<expected<<"u,";if((n&15)==15)out<<'\n';
 }
 for(unsigned n=0;n<16384;++n)for(uint32_t high:{0u,0x12340000u,0xa5a50000u,0xffff0000u}){
  const uint32_t raw=(n<<2)|3|high;d.io_in=raw;d.eval();if(d.io_out_rd!=((raw>>7)&31)||d.io_out_rs1!=((raw>>15)&31)||d.io_out_rs2!=((raw>>20)&31)||d.io_out_rs3!=(raw>>27))throw std::runtime_error("source RVI register fields");++checks;
 }
 out<<"};\ninline uint16_t source_rocket_registers(uint32_t raw){return(raw&3)==3?uint16_t(((raw>>7)&31)|(((raw>>15)&31)<<5)|(((raw>>20)&31)<<10)):rocket_rvc_registers[(raw&3)*16384+(uint16_t(raw)>>2)];}\n}\n";
 if(!out)throw std::runtime_error("field output failed");std::cout<<"PASS "<<std::dec<<checks<<" source register-field checks\n";
}
