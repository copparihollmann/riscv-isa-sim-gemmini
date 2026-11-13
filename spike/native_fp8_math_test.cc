#include "iris_native_fp8.hpp"
#include "native_fp8_cases.hpp"
#include <iostream>
int main(){
  for(const auto& c:native_cases){
    const auto r=iris_fp8::fma(c.a,c.b,c.c,c.fmt,c.rm,c.op,c.lane);
    if(r.bits!=c.out||r.flags!=c.flags){std::cerr<<"native FP8 oracle mismatch case="<<(&c-native_cases)<<" got="<<r.bits<<","<<unsigned(r.flags)<<" expected="<<unsigned(c.out)<<","<<unsigned(c.flags)<<"\n";return 1;}
  }
  std::cout<<"native_fp8_integer_oracle="<<std::size(native_cases)<<" pass\n";
}
