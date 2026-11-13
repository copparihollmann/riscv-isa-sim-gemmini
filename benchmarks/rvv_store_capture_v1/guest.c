#include "runtime.h"
static uint32_t source[3][64] __attribute__((aligned(256)));
static volatile uint32_t output[3][64] __attribute__((aligned(256)));
static uint64_t checks[3],bad[3];
void benchmark_main(unsigned h){
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");
 for(unsigned n=1;n<=64;n*=2){
  for(unsigned i=0;i<64;++i){source[h][i]=h*10000+n*100+i;output[h][i]=0xa5a5a5a5u;}
  __asm__ volatile("csrw vstart,zero\ncsrw vxrm,zero\ncsrw fcsr,zero":::"memory");
  unsigned long vl;
  __asm__ volatile("vsetvli %0,%1,e32,m8,ta,ma":"=r"(vl):"r"((unsigned long)n):"memory");
  if(vl!=n)fail(h,1,vl,n);
#ifndef IRIS_TEST_UNDEFINED_SOURCE
  __asm__ volatile("vle32.v v8,(%0)\nvadd.vi v8,v8,1"::"r"(source[h]):"memory");
#endif
#ifdef IRIS_TEST_MASKED_STORE
  __asm__ volatile("vmseq.vi v0,v8,0\nvse32.v v8,(%0),v0.t"::"r"(output[h]):"memory");
#else
  __asm__ volatile("vse32.v v8,(%0)"::"r"(output[h]):"memory");
#endif
  memory_fence();
  for(unsigned i=0;i<64;++i){unsigned want=i<n?source[h][i]+1:0xa5a5a5a5u;bad[h]|=output[h][i]^want;++checks[h];}
 }
 barrier();if(h==0){unsigned errors=0;for(unsigned i=0;i<3;++i){putstr("IRIS_VSE_CAPTURE {\"hart\":");putuint(i);putstr(",\"checked_words\":");putuint(checks[i]);putstr(",\"mismatch_or\":");putuint(bad[i]);putstr("}\n");errors|=bad[i]!=0;}putstr("IRIS_VSE_CAPTURE_DONE\n");finish(errors);}
 for(;;)__asm__ volatile("wfi");
}
