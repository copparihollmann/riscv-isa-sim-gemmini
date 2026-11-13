#include <cstdint>
#include <iostream>
#include <stdexcept>
#include "softfloat.h"
#include "iris_fp8.hpp"
#include "iris_ieee_fma.hpp"
#include "iris_shared_fma.hpp"
#include "encoding.h"
#include "shared_fma_cases.hpp"
static const uint32_t operations[]={
 MATCH_VFADD_VV,MATCH_VFADD_VF,MATCH_VFSUB_VV,MATCH_VFSUB_VF,MATCH_VFRSUB_VF,MATCH_VFMUL_VV,MATCH_VFMUL_VF,
 MATCH_VFMACC_VV,MATCH_VFMACC_VF,MATCH_VFNMACC_VV,MATCH_VFNMACC_VF,MATCH_VFMSAC_VV,MATCH_VFMSAC_VF,
 MATCH_VFNMSAC_VV,MATCH_VFNMSAC_VF,MATCH_VFMADD_VV,MATCH_VFMADD_VF,MATCH_VFNMADD_VV,MATCH_VFNMADD_VF,
 MATCH_VFMSUB_VV,MATCH_VFMSUB_VF,MATCH_VFNMSUB_VV,MATCH_VFNMSUB_VF,
 MATCH_VFWADD_VV,MATCH_VFWADD_VF,MATCH_VFWSUB_VV,MATCH_VFWSUB_VF,MATCH_VFWADD_WV,MATCH_VFWADD_WF,
 MATCH_VFWSUB_WV,MATCH_VFWSUB_WF,MATCH_VFWMUL_VV,MATCH_VFWMUL_VF,MATCH_VFWMACC_VV,MATCH_VFWMACC_VF,
 MATCH_VFWNMACC_VV,MATCH_VFWNMACC_VF,MATCH_VFWMSAC_VV,MATCH_VFWMSAC_VF,MATCH_VFWNMSAC_VV,MATCH_VFWNMSAC_VF};
int main(){
 for(const auto& c:shared_cases){
  uint8_t flags=0;uint64_t output=c.c;
  if(c.vl){const auto result=iris_shared::operation(operations[c.code]>>26,iris_fma::Kind(c.kind),c.a,c.b,c.c,c.rm,flags);if(c.active)output=result;}
  if(output!=c.out||flags!=c.flags){std::cerr<<"shared arithmetic mismatch "<<(&c-shared_cases)<<" got="<<std::hex<<output<<","<<unsigned(flags)<<" expected="<<c.out<<","<<unsigned(c.flags)<<"\n";return 1;}
 }
 for(const auto& c:shared_reductions){
  const auto in=iris_fma::Kind(c.kind),out=c.wide?(in==iris_fma::S?iris_fma::D:iris_fma::S):in;
  uint8_t flags=0;uint64_t acc=0xa5a5a5a5a5a5a5a5ULL;
  if(iris_fma::width(out)==16)acc=uint16_t(acc);else if(iris_fma::width(out)==32)acc=uint32_t(acc);
  if(c.vl){acc=c.seed;for(unsigned i=0;i<c.vl;++i){const auto value=iris_shared::add(acc,c.data[i],in,out,c.rm,flags);if(c.mask[i/8]&(1<<(i%8)))acc=value;}acc=iris_shared::add(acc,0,out,out,c.rm,flags);}
  if(acc!=c.out||flags!=c.flags){std::cerr<<"shared reduction mismatch "<<(&c-shared_reductions)<<"\n";return 1;}
 }
 std::cout<<"shared_fma_integer_oracle="<<std::size(shared_cases)<<" reductions="<<std::size(shared_reductions)<<" pass\n";
}
