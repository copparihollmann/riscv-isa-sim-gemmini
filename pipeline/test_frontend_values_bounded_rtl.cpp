#include "frontend_values_bounded.hpp"
#include "VIrisPureAlu.h"
#include <fstream>
#include <iostream>
#include <stdexcept>
int main(int argc,char**argv) {
  if(argc!=2)throw std::invalid_argument("actual ALU corpus required");
  VIrisPureAlu rtl;std::ifstream source(argv[1]);uint64_t x,pc,a,b,want,rows=0;
  while(source>>x>>pc>>a>>b>>want) {
    const unsigned code=x&127,f=(x>>12)&7;const bool word=code==0x1b || code==0x3b;
    unsigned fn=0;uint64_t lhs=a,rhs=b;
    if(code==0x37 || code==0x17) {
      lhs=code==0x17?pc:0;rhs=iris::frontend::PureAluValue::sext(x&0xfffff000,32);
    } else {
      const bool immediate=code==0x13 || code==0x1b;
      if(immediate)rhs=iris::frontend::PureAluValue::sext(x>>20,12);
      switch(f) {
        case 0:fn=!immediate && (x>>25)==32?10:0;break;
        case 1:fn=1;break;
        case 2:fn=12;break;
        case 3:fn=14;break;
        case 4:fn=4;break;
        case 5:fn=(x&(1ull<<30))?11:5;break;
        case 6:fn=6;break;
        case 7:fn=7;break;
      }
    }
    rtl.io_in1=lhs;rtl.io_in2=rhs;rtl.io_dw=!word;rtl.io_fn=fn;rtl.eval();
    if(rtl.shuttle_out!=want || rtl.rocket_out!=want)throw std::runtime_error("source ALU/independent oracle differs row="+std::to_string(rows));
    ++rows;
  }
  if(!source.eof() || rows<20000)throw std::runtime_error("incomplete ALU hardware corpus");
  std::cout<<"PASS source pure-ALU full-width result comparisons="<<rows*2<<"\n";
}
