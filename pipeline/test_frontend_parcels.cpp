#include "frontend_parcels.hpp"
#include "VRVCExpander.h"
#include <iostream>
#include <stdexcept>

using iris::frontend::FetchControl;
static FetchControl decoded_control(uint32_t expanded) {
  FetchControl c;const auto opcode=expanded&127;
  c.jump=opcode==0x6f;c.jalr=opcode==0x67;c.branch=opcode==0x63;
  c.call=(c.jump||c.jalr) && (expanded&128);
  c.ret=c.jalr && !(expanded&128) && (((expanded>>15)&27)==1);
  return c;
}
int main() {
  VRVCExpander rtl;uint64_t checks=0,cfi=0;
  for(unsigned low=0;low<65536;++low)for(uint32_t upper:{0u,0x12340000u,0xffff0000u,0xa5a50000u}) {
    const auto raw=low|upper;rtl.io_in=raw;rtl.eval();
    const auto expanded=(raw&3)==3?raw:uint32_t(rtl.io_out_bits);
    const auto got=iris::frontend::fetch_control(raw),want=decoded_control(expanded);
    if(got!=want)throw std::runtime_error("source predecode differs raw="+std::to_string(raw));
    ++checks;cfi+=got.jump||got.jalr||got.branch;
  }
  // Actual packet predecode is orthogonal to core admission: compressed
  // branches/jumps are retained, and instructions after a redirect masked.
  const uint64_t nops=0x0001000100010001ull;
  for(unsigned offset=0;offset<4;++offset) {
    const auto p=iris::frontend::decode_parcels(true,0x80000000+2*offset,nops,false,0);
    if(p.mask!=(15u & (15u<<offset)) || p.end_half_valid || p.edge_instruction)throw std::runtime_error("RVC parcel positions");
  }
  const auto wide=iris::frontend::decode_parcels(true,0x80000000,0x0012829300128293ull,false,0);
  if(wide.mask!=5 || wide.end_half_valid)throw std::runtime_error("two 32-bit parcels");
  const auto carry=iris::frontend::decode_parcels(true,0x80000008,0x0001000100010012ull,true,0x8293);
  if(carry.mask!=15 || carry.raw[0]!=0x00128293 || carry.pc[0]!=0x80000006 || (carry.npc_plus4_mask&1))throw std::runtime_error("32-bit carry across packet");
  const auto jump=iris::frontend::decode_parcels(true,0x80000000,(nops&~uint64_t(65535))|0xa001,false,0);
  if(jump.mask!=1 || !jump.redirect || jump.redirect_index!=0)throw std::runtime_error("C.J packet cutoff");
  const auto branch=uint64_t(0xc001)|(nops&~uint64_t(65535));
  if(iris::frontend::decode_parcels(true,0x80000000,branch,false,0,{true,true,false,0}).redirect)throw std::runtime_error("branch ignores BHT");
  if(!iris::frontend::decode_parcels(true,0x80000000,branch,false,0,{true,true,true,0}).redirect)throw std::runtime_error("taken branch ignored");
  std::cout<<"PASS exhaustive source CFI predecode checks="<<checks<<" CFI="<<cfi<<" plus packet/carry/redirect controls\n";
}
