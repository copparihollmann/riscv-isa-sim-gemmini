#include "runtime.h"
extern void source_wake_pulse(void);
static volatile uint64_t ready,done;
void benchmark_main(unsigned h) {
  barrier();
  __asm__ volatile("csrc mstatus,%0; csrw mie,zero"::"r"(8UL):"memory");
  if(h==1)for(;;)__asm__ volatile("wfi");
  if(h==2) {
    __asm__ volatile("csrw mie,%0"::"r"(8UL):"memory");
    ready=1;memory_fence();
    __asm__ volatile(".global source_pulse_park\nsource_pulse_park:\nwfi":::"memory");
    done=1;memory_fence();
    for(;;)__asm__ volatile("wfi");
  }
  while(!ready){}
  __asm__ volatile(".rept 64\naddi zero,zero,0\n.endr":::"memory");
  source_wake_pulse();
  while(!done){}
  putstr("PASSED source wake persists after pulse clears before Rocket RRD\n");finish(0);
}
