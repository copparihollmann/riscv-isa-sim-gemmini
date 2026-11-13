#include "runtime.h"
#include "vme.h"
#ifndef GUARD_MODE
#define GUARD_MODE 0
#endif
extern void long_same(void);
__attribute__((noreturn,noinline))void abort(void){fail(hart_id(),251,0,GUARD_MODE);}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 if(h==0){
  vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);VME_VTZERO(0);memory_fence();
  __asm__ volatile("vmv.v.i v8,1\nvmv.v.i v16,1":::"memory");memory_fence();
#if GUARD_MODE==0
  vme_vsettk(2);VME_MM_U_U(0,8,16);
#elif GUARD_MODE==1
  vme_vsettm(0);VME_MM_U_U(0,8,16);
#elif GUARD_MODE==2
  VME_MM_U_U(0,24,16);
#elif GUARD_MODE==3
  long_same();memory_fence();set_timer(h,mtime()+4);__asm__ volatile("csrs mie,%0"::"r"(128UL):"memory");
  for(unsigned k=0;k<8;++k)long_same();
#endif
  memory_fence();abort();
 }
 for(;;)__asm__ volatile("wfi");
}
