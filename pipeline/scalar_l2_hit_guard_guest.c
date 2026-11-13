/* Synthetic executed-ELF mechanics, never a calibrated workload. */
#include "runtime.h"
typedef struct __attribute__((aligned(64))){uint32_t word[16];}line_t;
static volatile line_t source[3],destination[3];
static uintptr_t chain[3][512][8] __attribute__((aligned(64)));
typedef struct __attribute__((aligned(64))){uint64_t scalar_start,scalar_end,load_start,load_end,store_start,store_end,failed;}record_t;
static record_t records[3];
extern uintptr_t scalar_l2_chase(uintptr_t,unsigned);
__asm__(".text\n.option push\n.option norvc\n.balign 4\n.globl scalar_l2_chase\n.type scalar_l2_chase,@function\nscalar_l2_chase:\n1:ld a0,0(a0)\naddi a1,a1,-1\nbnez a1,1b\nret\n.size scalar_l2_chase,.-scalar_l2_chase\n.option pop\n");
void benchmark_main(unsigned h){
 for(unsigned i=0;i<512;++i)chain[h][i][0]=(uintptr_t)&chain[h][(i+1)&511][0];
 memory_fence();barrier();
 uint64_t sa=cycles();uintptr_t p=scalar_l2_chase((uintptr_t)&chain[h][0][0],512);memory_fence();uint64_t sb=cycles();
 unsigned failed=p!=(uintptr_t)&chain[h][0][0];
 for(unsigned i=0;i<8;++i)source[h].word[i]=100+h+i;
 memory_fence();
 // Actual stores to six same-bank/set aliases evict source under the explicit
 // LRU model, without touching its architectural bytes. This checks the cold
 // vector OUTER path, not physical cache replacement or measured bandwidth.
 for(unsigned i=1;i<=6;++i)*(volatile uint64_t*)((uintptr_t)source[h].word+0x20000UL*i)=i;
 memory_fence();barrier();
 unsigned long vl;__asm__ volatile("vsetivli %0,8,e32,m1,ta,ma":"=r"(vl)::"memory");
 uint64_t a,b,c,d;
 __asm__ volatile("csrr %0,mcycle\nvle32.v v8,(%2)\nvle32.v v9,(%2)\ncsrr %1,mcycle":"=&r"(a),"=&r"(b):"r"(source[h].word):"memory");
 __asm__ volatile("vadd.vv v8,v8,v9":::"memory");
 __asm__ volatile("csrr %0,mcycle\nvse32.v v8,(%2)\nvse32.v v8,(%2)\ncsrr %1,mcycle":"=&r"(c),"=&r"(d):"r"(destination[h].word):"memory");
 memory_fence();failed+=vl!=8;for(unsigned i=0;i<8;++i)failed+=destination[h].word[i]!=2*(100+h+i);
 records[h]=(record_t){sa,sb,a,b,c,d,failed};barrier();
 if(h==0){unsigned total=0;for(unsigned i=0;i<3;++i){record_t*r=&records[i];putstr("IRIS_SCALAR_L2_GUARD ");putuint(i);putstr(" ");putuint(r->scalar_start);putstr(" ");putuint(r->scalar_end);putstr(" ");putuint(r->load_start);putstr(" ");putuint(r->load_end);putstr(" ");putuint(r->store_start);putstr(" ");putuint(r->store_end);putstr(" ");putuint(r->failed);putstr("\n");total+=r->failed;}finish(total);}
 for(;;)__asm__ volatile("wfi");
}
