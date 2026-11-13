/* Cold opaque RVV traffic checks resource layering, never numeric calibration. */
#include "runtime.h"
void benchmark_main(unsigned h){
 const uintptr_t src=0xb0000000ul+64*h,dst=0xb0100000ul+64*h;
 barrier();
 __asm__ volatile("vsetivli zero,16,e8,m1,ta,ma\nvle8.v v8,(%0)\nvse8.v v8,(%1)"::"r"(src),"r"(dst):"memory");
 memory_fence();barrier();
 if(h==0){putstr("IRIS_VECTOR_LAYER_DONE\n");finish(0);}
 for(;;)__asm__ volatile("wfi");
}
