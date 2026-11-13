#include "iris_fp8.hpp"
#include <atomic>
#include <iostream>
#include <thread>
#include <vector>
#include <stdexcept>
extern "C" unsigned iris_saturn_fp8_fma(unsigned,unsigned,unsigned,unsigned,unsigned,unsigned);
int main(){std::atomic<unsigned> checks{0},refusals{0};std::atomic<bool> failed{false};std::vector<std::thread> threads;
 for(unsigned id=0;id<8;++id)threads.emplace_back([&,id]{try{
  softfloat_roundingMode=id%5;softfloat_exceptionFlags=(id*7)&31;softfloat_detectTininess=id%2;
  const auto mode=softfloat_roundingMode,flags=softfloat_exceptionFlags,tiny=softfloat_detectTininess;
  for(unsigned n=0;n<1000;++n)for(unsigned fa=0;fa<2;++fa)for(unsigned fb=0;fb<2;++fb)for(unsigned rm=0;rm<5;++rm){
   if(iris_saturn_fp8_fma(fa?0x3c:0x38,fb?0x3c:0x38,0x3f800000,fa,fb,rm)!=0x40000000)throw std::runtime_error("Exact1*1+1 differs");
   if(softfloat_roundingMode!=mode||softfloat_exceptionFlags!=flags||softfloat_detectTininess!=tiny)throw std::runtime_error("DPI modified caller FP state");++checks;
  }
  for(unsigned rm=5;rm<8;++rm){bool refused=false;try{iris_saturn_fp8_fma(0,0,0,0,0,rm);}catch(const std::invalid_argument&){refused=true;}
   if(!refused||softfloat_roundingMode!=mode||softfloat_exceptionFlags!=flags||softfloat_detectTininess!=tiny)throw std::runtime_error("Unqualified rounding did not fail closed");++refusals;}
 }catch(...){failed=true;}});
 for(auto&t:threads)t.join();if(failed)return 2;
 std::cout<<"{\"concurrent_thread_count\":8,\"exact_result_and_caller_state_checks\":"<<checks<<",\"reserved_rounding_refusals\":"<<refusals<<"}\n";return 0;}
