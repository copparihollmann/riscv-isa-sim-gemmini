#include "runtime.h"
#ifndef IRIS_ACTIVE_HART
#define IRIS_ACTIVE_HART 0
#endif
static volatile uint32_t output[4][64] __attribute__((aligned(256)));
static uint64_t boot[3] __attribute__((aligned(64)));
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
 // Permit the last arriving peer to execute its actual WFI instruction.
 for(volatile unsigned i=0;i<32;++i){}
 for(unsigned j=0;j<4;++j)for(unsigned i=0;i<64;++i)output[j][i]=0xa5a5a5a5;
 unsigned long vl,n=64;
 __asm__ volatile("csrw vstart,zero\ncsrw vxrm,zero\ncsrw fcsr,zero\nvsetvli %0,%1,e32,m8,ta,ma\nvmv.v.i v8,3":"=r"(vl):"r"(n):"memory");
 if(vl!=64)fail(h,1,vl,64);
 memory_fence();
#ifdef IRIS_TEST_PENDING_IRQ
 __asm__ volatile("csrw mie,%0"::"r"(8UL):"memory");*(volatile uint32_t*)(IRIS_CLINT+4*h)=1;memory_fence();
#endif
#ifdef IRIS_TEST_IRQ_ENABLE
 __asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
#endif
 #ifdef IRIS_TEST_KILLED_STORE
 __asm__ volatile("beq zero,zero,1f\nvse32.v v8,(zero)\n1:":::"memory");
#endif
 uint64_t start,issue,end,ir0,ir1;
 __asm__ volatile(
 "csrr %[s],mcycle\ncsrr %[i0],minstret\n"
 "vse32.v v8,(%[p0])\nli t0,32\n1: addi t0,t0,-1\nbnez t0,1b\n"
 "vadd.vi v8,v8,1\nvse32.v v8,(%[p1])\n"
 "vadd.vi v8,v8,1\nvse32.v v8,(%[p2])\n"
 "vadd.vi v8,v8,1\nvse32.v v8,(%[p3])\n"
 "csrr %[is],mcycle\nfence rw,rw\ncsrr %[e],mcycle\ncsrr %[i1],minstret"
 :[s]"=&r"(start),[is]"=&r"(issue),[e]"=&r"(end),[i0]"=&r"(ir0),[i1]"=&r"(ir1)
 :[p0]"r"(output[0]),[p1]"r"(output[1]),[p2]"r"(output[2]),[p3]"r"(output[3]):"t0","memory");
 uint64_t bad=0,sum=0;for(unsigned j=0;j<4;++j)for(unsigned i=0;i<64;++i){bad|=output[j][i]^(3+j);sum+=output[j][i];}
 putstr("IRIS_VSE_ACTOR {\"hart\":");putuint(h);putstr(",\"checked_words\":256,\"mismatch_or\":");putuint(bad);putstr(",\"checksum\":");putuint(sum);putstr(",\"start\":");putuint(start);putstr(",\"issue_end\":");putuint(issue);putstr(",\"fence_end\":");putuint(end);putstr(",\"instret\":");putuint(ir1-ir0);putstr("}\nIRIS_VSE_ACTOR_DONE\n");finish(bad?1:0);
}
