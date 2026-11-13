#include <cstdint>
#include <iostream>
#include <stdexcept>
#include "softfloat.h"
#include "iris_fp8.hpp"
#include "iris_ieee_fma.hpp"
#include "ieee_fma_cases.hpp"
int main(){
 for(const auto& t:ieee_cases){
  const auto in=iris_fma::Kind(t.kind),out=t.code>=23?(in==iris_fma::S?iris_fma::D:iris_fma::S):in;
  const bool wi=t.code==27||t.code==28||t.code==29||t.code==30;
  uint64_t a,b,c;{IrisSoftfloatScope scope(t.rm);a=iris_fma::input(t.a,wi?out:in,out,t.lane);b=iris_fma::input(t.b,in,out,t.lane);c=iris_fma::input(t.c,out,out,t.lane);}
  unsigned cmd=0;
  if(t.code<5||(t.code>=23&&t.code<=30)){c=b;b=iris_fma::one(out);cmd=t.code==2||t.code==3||t.code==25||t.code==26||t.code==29||t.code==30?1:t.code==4?2:0;}
  else if(t.code==5||t.code==6||t.code==31||t.code==32)c=(a^b)&iris_fma::signbit(out);
  else{
   const unsigned m=(t.code<23?(t.code-7)/2:(t.code-33)/2);
   const unsigned cmds[]={0,3,1,2,0,3,1,2};cmd=cmds[m];
   if(t.code>=15&&t.code<23){const uint64_t temp=a;a=c;c=temp;}
  }
  uint8_t flags=0;auto got=iris_fma::fused(a,b,c,out,t.rm,cmd,flags);
  if(got!=t.out||flags!=t.flags){std::cerr<<"IEEE math mismatch case "<<(&t-ieee_cases)<<" kind"<<t.kind<<" code"<<t.code<<" got "<<std::hex<<got<<" flags"<<unsigned(flags)<<" expected "<<t.out<<","<<unsigned(t.flags)<<"\n";return 1;}
 }
 std::cout<<"ieee_fma_integer_oracle="<<std::size(ieee_cases)<<" pass\n";
}
