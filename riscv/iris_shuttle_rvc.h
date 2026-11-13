#pragma once
#include <cstdint>
#include <optional>

namespace iris::shuttle {
struct CompressedAlu {
  uint32_t expanded;
  const char* name;
};

// RV64 scalar ALU subset of pinned Rocket RVCDecoder, default
// useAddiForMv=false, as called by Shuttle RISCVConstants.ExpandRVC.
// Memory/CFI/system/reserved encodings and uncommon rd=x0 HINT groups
// remain explicit boundaries, not newly invented illegal instructions.
inline std::optional<CompressedAlu> expand_compressed_alu(uint16_t raw) {
  const unsigned quadrant=raw&3, funct=raw>>13, rd=(raw>>7)&31;
  const unsigned rs2=(raw>>2)&31, prime1=8+((raw>>7)&7), prime2=8+((raw>>2)&7);
  const unsigned immediate6=((raw>>2)&31)|((raw>>7)&32);
  const int immediate=(immediate6&32) ? int(immediate6)-64 : int(immediate6);
  const auto i=[](unsigned op,unsigned rd,unsigned rs1,unsigned funct,unsigned imm) {
    return ((imm&4095)<<20)|(rs1<<15)|(funct<<12)|(rd<<7)|op;
  };
  const auto r=[](unsigned op,unsigned rd,unsigned rs1,unsigned rs2,unsigned funct,unsigned high=0) {
    return (high<<25)|(rs2<<20)|(rs1<<15)|(funct<<12)|(rd<<7)|op;
  };
  if(quadrant==0 && funct==0) {
    const unsigned imm=(((raw>>6)&1)<<2)|(((raw>>5)&1)<<3)|(((raw>>11)&3)<<4)|(((raw>>7)&15)<<6);
    if(imm) return CompressedAlu{i(0x13,prime2,2,0,imm),"C.ADDI4SPN"};
  }
  if(quadrant==1) {
    if(funct==0) return CompressedAlu{i(0x13,rd,rd,0,immediate),raw==1?"C.NOP":"C.ADDI"};
    if(funct==1 && rd) return CompressedAlu{i(0x1b,rd,rd,0,immediate),"C.ADDIW"};
    if(funct==2) return CompressedAlu{i(0x13,rd,0,0,immediate),"C.LI"};
    if(funct==3 && rd) {
      if(rd==2) {
        unsigned bits=(((raw>>6)&1)<<4)|(((raw>>2)&1)<<5)|(((raw>>5)&1)<<6)|(((raw>>3)&3)<<7)|(((raw>>12)&1)<<9);
        if(bits) {
          const int imm=(bits&512)?int(bits)-1024:int(bits);
          return CompressedAlu{i(0x13,2,2,0,imm),"C.ADDI16SP"};
        }
      } else if(immediate) return CompressedAlu{((uint32_t(immediate)&0xfffff)<<12)|(rd<<7)|0x37,"C.LUI"};
    }
    if(funct==4) {
      const unsigned group=(raw>>10)&3;
      if(group==0) return CompressedAlu{i(0x13,prime1,prime1,5,immediate6),"C.SRLI"};
      if(group==1) return CompressedAlu{i(0x13,prime1,prime1,5,immediate6|0x400),"C.SRAI"};
      if(group==2) return CompressedAlu{i(0x13,prime1,prime1,7,immediate),"C.ANDI"};
      const unsigned operation=(raw>>5)&3;
      if(!(raw&0x1000)) {
        static constexpr unsigned funcs[]={0,4,6,7};
        static constexpr const char* names[]={"C.SUB","C.XOR","C.OR","C.AND"};
        return CompressedAlu{r(0x33,prime1,prime1,prime2,funcs[operation],operation==0?0x20:0),names[operation]};
      }
      if(operation<2) return CompressedAlu{r(0x3b,prime1,prime1,prime2,0,operation==0?0x20:0),operation==0?"C.SUBW":"C.ADDW"};
    }
  }
  if(quadrant==2) {
    if(funct==0 && rd) return CompressedAlu{i(0x13,rd,rd,1,immediate6),"C.SLLI"};
    if(funct==4 && rd && rs2) {
      const bool add=raw&0x1000;
      return CompressedAlu{r(0x33,rd,add?rd:0,rs2,0),add?"C.ADD":"C.MV"};
    }
  }
  return {};
}
} // namespace iris::shuttle
