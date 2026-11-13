#include "runtime.h"
static volatile uint64_t shared __attribute__((aligned(64)));
static uint64_t rows[3][2] __attribute__((aligned(64)));
void benchmark_main(unsigned h){if(h==0)shared=1;memory_fence();barrier();uint64_t warm=shared;__asm__ volatile(""::"r"(warm):"memory");barrier();uint64_t bad=0,count=0;
 if(h==0){for(unsigned i=0;i<1024;++i){uint64_t v;__asm__ volatile(".option push\n.option norvc\n.globl late_coh_load\nlate_coh_load:\nld t0,0(%1)\n.globl late_coh_ALU\nlate_coh_ALU:\naddi %0,t0,1\n.option pop":"=&r"(v):"r"(&shared):"t0","memory");bad+=v<2||v>4;++count;}}
 else for(unsigned i=0;i<1024;++i)__asm__ volatile("sd %0,0(%1)"::"r"((uint64_t)(h+1)),"r"(&shared):"memory");
 rows[h][0]=bad;rows[h][1]=count;barrier();if(h==0){putstr("LATE_COH ");putuint(rows[0][0]);putstr(" ");putuint(rows[0][1]);putstr("\n");finish(rows[0][0]);}for(;;)__asm__ volatile("wfi");}
