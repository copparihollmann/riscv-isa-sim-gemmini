/* Unknown address must remain unknown; an annulled store must not observe it. */
#include "runtime.h"
#ifndef IRIS_BAD_HART
#define IRIS_BAD_HART 0
#endif
#ifndef IRIS_STORE_WRONGPATH
#define IRIS_STORE_WRONGPATH 0
#endif
void benchmark_main(unsigned h) {
  volatile uint8_t *opaque=(volatile uint8_t *)(uintptr_t)(0x94000000ul+128*h);
  *opaque=7;memory_fence();barrier();
  if (h==IRIS_BAD_HART) {
    if (IRIS_STORE_WRONGPATH)
      __asm__ volatile("ld t0,0(%0)\nli t1,1\nbnez t1,1f\nsd zero,0(t0)\n1:"
                       ::"r"(opaque):"t0","t1","memory");
    else __asm__ volatile("ld t0,0(%0)\nsd zero,0(t0)"::"r"(opaque):"t0","memory");
  }
  barrier();
  if (h==0) {putstr("IRIS_UNKNOWN_STORE_WRONGPATH_PASS\n");finish(0);}
  for (;;) __asm__ volatile("wfi");
}
