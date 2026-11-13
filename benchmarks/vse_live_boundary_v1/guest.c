#include "runtime.h"
#ifndef IRIS_ACTIVE_HART
#define IRIS_ACTIVE_HART 0
#endif
static volatile uint32_t output[8][64] __attribute__((aligned(256)));
static uint64_t boot[3] __attribute__((aligned(64)));
static const unsigned lengths[8]={1,4,8,16,32,64,64,4};
void benchmark_main(unsigned h){
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");
 __atomic_store_n(&boot[h],1,__ATOMIC_RELEASE);
 if(h!=IRIS_ACTIVE_HART){
#ifdef IRIS_TEST_BUSY_PEER
  for(;;)__asm__ volatile("addi zero,zero,0");
#else
  for(;;)__asm__ volatile("wfi");
#endif
 }
 for(unsigned p=0;p<3;++p)while(!__atomic_load_n(&boot[p],__ATOMIC_ACQUIRE)){}
 for(volatile unsigned i=0;i<32;++i){}
 for(unsigned j=0;j<8;++j)for(unsigned i=0;i<64;++i)output[j][i]=0xa5a5a5a5;
#ifdef IRIS_TEST_IRQ_ENABLE
 __asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
#endif
#ifdef IRIS_TEST_PENDING_IRQ
 __asm__ volatile("csrw mie,%0"::"r"(8UL):"memory");*(volatile uint32_t*)(IRIS_CLINT+4*h)=1;memory_fence();
#endif
 __asm__ volatile("csrw vstart,zero\ncsrw vxrm,zero\ncsrw fcsr,zero":::"memory");
 unsigned long vl;
 // A wrong-path store has no source owner and must never trigger COM capture.
 __asm__ volatile("beq zero,zero,1f\nvse32.v v8,(zero)\n1:":::"memory");
 for(unsigned j=0;j<8;++j){
  unsigned long n=lengths[j],add=13+11*j;volatile uint32_t*dst=output[j];
  __asm__ volatile("vsetvli %0,%1,e32,m8,ta,ma":"=r"(vl):"r"(n):"memory");
  if(vl!=n)fail(h,1,vl,n);
#ifndef IRIS_TEST_UNKNOWN_SOURCE
  __asm__ volatile("vid.v v8\nvadd.vx v8,v8,%0"::"r"(add):"memory");
#else
  (void)add;
#endif
#ifdef IRIS_TEST_MISALIGNED
  dst=(volatile uint32_t*)((uintptr_t)dst+4);
#endif
#ifdef IRIS_TEST_WRONG_EEW
  __asm__ volatile("vse16.v v8,(%0)"::"r"(dst):"memory");
#else
  __asm__ volatile("vse32.v v8,(%0)"::"r"(dst):"memory");
#endif
 }
 memory_fence();
 uint64_t bad=0,sum=0;for(unsigned j=0;j<8;++j)for(unsigned i=0;i<64;++i){
  const uint32_t expected=i<lengths[j]?13+11*j+i:0xa5a5a5a5;const uint32_t got=output[j][i];bad|=got^expected;sum+=got;
 }
 putstr("IRIS_VSE_BOUNDARY {\"hart\":");putuint(h);putstr(",\"checked_words\":512,\"stored_words\":193,\"mismatch_or\":");putuint(bad);putstr(",\"checksum\":");putuint(sum);putstr("}\nIRIS_VSE_BOUNDARY_DONE\n");finish(bad?1:0);
}
