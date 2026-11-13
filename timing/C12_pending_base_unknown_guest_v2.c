#include "runtime.h"
#ifndef IRIS_BAD_HART
#error IRIS_BAD_HART required
#endif
void benchmark_main(unsigned h){
 volatile uint8_t*p=(volatile uint8_t*)(0x90001000ul+h*128);*p=7;
 memory_fence();barrier();
 if(h==IRIS_BAD_HART){
  /* Establish a cache response while preserving the partial known mask. */
  __asm__ volatile("ld t0,0(%0)\nsd t0,0(%1)"::"r"(p),"r"(p+64):"t0","memory");
  memory_fence();
  __asm__ volatile(".option push\n.option norvc\n.globl pending_unknown_load\npending_unknown_load:\nld t0,0(%0)\naddi t0,t0,0\n.globl pending_unknown_consumer\npending_unknown_consumer:\nld t1,0(t0)\n.option pop"::"r"(p):"t0","t1","memory");
 }
 barrier();if(h==0)finish(1);for(;;)__asm__ volatile("wfi");
}
