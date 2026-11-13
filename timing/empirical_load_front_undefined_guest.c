/* Each derived ELF makes one hart observe an opaque partially unknown load. */
#include "runtime.h"
#ifndef IRIS_BAD_HART
#error IRIS_BAD_HART required
#endif
void benchmark_main(unsigned h){
 volatile uint8_t*unknown=(volatile uint8_t*)(uintptr_t)(0x90000000ul+128*h);
 *unknown=7;memory_fence();barrier();
 if(h==IRIS_BAD_HART)__asm__ volatile("ld t0,0(%0)\naddi t1,t0,1"::"r"(unknown):"t0","t1","memory");
 barrier();if(h==0)finish(1);for(;;)__asm__ volatile("wfi");
}
