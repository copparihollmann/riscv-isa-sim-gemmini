#include "runtime.h"
#ifndef IRIS_ACTIVE_HART
#define IRIS_ACTIVE_HART 0
#endif
static uint32_t output[64] __attribute__((aligned(128)));
static void setup(void){unsigned long vl;__asm__ volatile("csrw frm,zero\ncsrw fflags,%2\nvsetvli %0,%1,e32,m8,ta,ma\nvmv.v.x v8,%3\nvmv.v.x v16,%3":"=&r"(vl):"r"(64UL),"r"(31UL),"r"(0x3f800000UL):"memory");if(vl!=64)fail(IRIS_ACTIVE_HART,1,vl,64);memory_fence();}
#define RUN(CSR,FORM,COUNTER) {setup();unsigned long value,after; __asm__ volatile("vfadd.vv v8,v8,v16\n.word %2\n" COUNTER_FENCE(COUNTER) "csrr t2,mcycle\nmv %0,t1\nmv %1,t2\nvse32.v v8,(%3)":"=&r"(value),"=&r"(after):"i"(((CSR)<<20)|((FORM)<<12)|(6<<7)|0x73),"r"(output):"t1","t2","memory");memory_fence();unsigned bad=0;for(unsigned i=0;i<64;++i)bad+=output[i]!=0x40000000U;unsigned long flags;__asm__ volatile("csrr %0,fflags":"=r"(flags));bad+=flags!=31;failed+=bad;putstr("IRIS_FADD_COUNTER ");putuint(h);putstr(" ");putuint(CSR);putstr(" ");putuint(FORM);putstr(" ");putuint(COUNTER);putstr(" ");putuint(value);putstr(" ");putuint(after);putstr(" ");putuint(bad);putstr("\n");++cases;}
#define COUNTER_FENCE_1 "fence rw,rw\n"
#define COUNTER_FENCE_0 ""
#define COUNTER_FENCE_I(X) COUNTER_FENCE_##X
#define COUNTER_FENCE(X) COUNTER_FENCE_I(X)
void benchmark_main(unsigned h){__asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");set_timer(h,UINT64_MAX);*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;memory_fence();if(h!=IRIS_ACTIVE_HART)for(;;)__asm__ volatile("wfi");unsigned failed=0,cases=0;
 RUN(2816,2,1);
 RUN(2816,3,1);
 RUN(2816,6,1);
 RUN(2816,7,1);
 RUN(2818,2,1);
 RUN(2818,3,1);
 RUN(2818,6,1);
 RUN(2818,7,1);
 RUN(3072,2,1);
 RUN(3072,3,1);
 RUN(3072,6,1);
 RUN(3072,7,1);
 RUN(3074,2,1);
 RUN(3074,3,1);
 RUN(3074,6,1);
 RUN(3074,7,1);
 RUN(1,2,0);
 RUN(2,2,0);
 RUN(3,2,0);
 RUN(768,2,0);
 RUN(3104,2,0);
 RUN(3105,2,0);
 RUN(3106,2,0);
 putstr("IRIS_FADD_COUNTER_DONE ");putuint(h);putstr(" ");putuint(cases);putstr(" ");putuint(failed);putstr("\n");finish(failed);
}
