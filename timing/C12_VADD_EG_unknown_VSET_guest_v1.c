#include "runtime.h"
#ifndef IRIS_BAD
#define IRIS_BAD 1
#endif
#ifndef IRIS_ACTIVE_HART
#define IRIS_ACTIVE_HART 0
#endif
void benchmark_main(unsigned h){
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");set_timer(h,UINT64_MAX);*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;memory_fence();if(h!=IRIS_ACTIVE_HART)for(;;)__asm__ volatile("wfi");
 __asm__ volatile("vsetivli zero,8,e32,m1,ta,ma\nvmv.v.i v8,3\nvmv.v.i v16,1":::"memory");memory_fence();
#if IRIS_BAD==1
 // Unknown low bits remain; the known high AVL bit would yield fullVL8
 // for every concrete value if the ordinary input-definedness guard vanished.
 __asm__ volatile("li t0,0xa0000000\nld t1,0(t0)\nori t1,t1,256\nli t2,0xd0\nvsetvl zero,t1,t2":::"t0","t1","t2","memory");
#elif IRIS_BAD==2
 // Concrete reset RAM bits may look like legal m1 type0xd0, while its LMUL
 // bits are unknown. No internal knownness assignment is used by this test.
 __asm__ volatile("li t0,0xa0000000\nld t2,0(t0)\nandi t2,t2,7\nori t2,t2,208\nli t1,8\nvsetvl zero,t1,t2":::"t0","t1","t2","memory");
#elif IRIS_BAD==3
 __asm__ volatile("li t0,0xa0000000\nld t1,0(t0)\nori t1,t1,256\nvsetvli zero,t1,e32,m1,ta,ma":::"t0","t1","memory");
#else
 __asm__ volatile("li t1,256\nli t2,0xd0\nvsetvl zero,t1,t2":::"t1","t2","memory");
#endif
 __asm__ volatile("vadd.vv v8,v8,v16":::"memory");memory_fence();putstr("UNEXPECTED_VSET_REACHED ");putuint(IRIS_BAD);putstr("\n");finish(0);
}
