#include "iris_fp8.hpp"
#include "wide_fp8_cases.hpp"
#include <iostream>
int main(){
 for(const auto& c:wide_cases){
  IrisSoftfloatScope scope(c.rm);
  auto n=[&](uint8_t raw){return uint16_t(iris_fp8_to_f32(raw,c.fmt)>>16);};
  auto w=[&](uint16_t raw){return uint16_t(!(c.lane&3)&&(raw&0x7f80)==0x7f80&&(raw&127)?0x7fc0:raw);};
  uint16_t a=c.code>=4&&c.code<=7?w(c.a):n(c.a),b=n(c.b),acc=w(c.c);unsigned cmd=0;
  if(c.code<8){acc=b;b=0x3f80;cmd=c.code==2||c.code==3||c.code==6||c.code==7?1:0;}
  else if(c.code<10)acc=(a^b)&0x8000;
  else {const unsigned signs[]={0,3,1,2};cmd=signs[(c.code-10)/2];}
  if(cmd&2)a^=0x8000;if(cmd&1)acc^=0x8000;
  auto out=bf16_mulAdd(float16_t{a},float16_t{b},float16_t{acc});
  const auto flags=bool(softfloat_exceptionFlags&softfloat_flag_invalid);
  if(out.v!=c.out||flags!=c.flags){std::cerr<<"wide oracle mismatch case="<<(&c-wide_cases)<<" got="<<out.v<<","<<flags<<" want="<<c.out<<","<<unsigned(c.flags)<<"\n";return 1;}
 }
 std::cout<<"wide_fp8_exact_oracle="<<std::size(wide_cases)<<" pass\n";
}
