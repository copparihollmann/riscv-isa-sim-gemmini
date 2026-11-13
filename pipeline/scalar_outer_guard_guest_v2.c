#include "runtime.h"
#ifndef ACTIVE_HART
#define ACTIVE_HART 0
#endif
typedef struct __attribute__((aligned(64))){uint32_t word[16];}line_t;
static volatile line_t source,destination;
extern uintptr_t outer_chase(uintptr_t,unsigned);
__asm__(".text\n.option push\n.option norvc\n.balign 4\n.globl outer_chase\n.type outer_chase,@function\nouter_chase:\n1:ld a0,0(a0)\naddi a1,a1,-1\nbnez a1,1b\nret\n.size outer_chase,.-outer_chase\n.option pop\n");
void benchmark_main(unsigned h){
 if(h!=ACTIVE_HART)for(;;)__asm__ volatile("wfi");
 uintptr_t base=0x90000000UL+h*0x08000000UL;
 for(unsigned i=0;i<512;++i)*(volatile uintptr_t*)(base+0x20000UL*i)=base+0x20000UL*((i+1)&511);
 uintptr_t warm=(uintptr_t)&warm;unsigned failed=outer_chase((uintptr_t)&warm,1)!=(uintptr_t)&warm;
 memory_fence();uint64_t sa=cycles();uintptr_t result=outer_chase(base,512);memory_fence();uint64_t sb=cycles();failed+=result!=base;
 for(unsigned i=0;i<8;++i)source.word[i]=100+h+i;
 for(unsigned i=1;i<=6;++i)*(volatile uint64_t*)((uintptr_t)source.word+0x20000UL*i)=i;
 memory_fence();unsigned long vl;__asm__ volatile("vsetivli %0,8,e32,m1,ta,ma":"=r"(vl)::"memory");
 uint64_t a,b,c,d;__asm__ volatile("csrr %0,mcycle\nvle32.v v8,(%2)\nvle32.v v9,(%2)\ncsrr %1,mcycle":"=&r"(a),"=&r"(b):"r"(source.word):"memory");
 __asm__ volatile("vadd.vv v8,v8,v9":::"memory");
 __asm__ volatile("csrr %0,mcycle\nvse32.v v8,(%2)\nvse32.v v8,(%2)\ncsrr %1,mcycle":"=&r"(c),"=&r"(d):"r"(destination.word):"memory");
 memory_fence();failed+=vl!=8;for(unsigned i=0;i<8;++i)failed+=destination.word[i]!=2*(100+h+i);
 putstr("IRIS_SCALAR_OUTER_GUARD ");putuint(h);putstr(" ");putuint(sa);putstr(" ");putuint(sb);putstr(" ");putuint(a);putstr(" ");putuint(b);putstr(" ");putuint(c);putstr(" ");putuint(d);putstr(" ");putuint(failed);putstr("\n");finish(failed);
}
