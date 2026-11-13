#include "runtime.h"
#include "uart_drain.h"
void benchmark_main(unsigned h) {
  if(h<2) {
    expect_illegal[h]=1;
    __asm__ volatile(".word 0x30500073" ::: "memory");
    if(expect_illegal[h] || illegal_seen[h]!=1)fail(h,255,__LINE__,illegal_seen[h]);
  }
  barrier();
  if(!h) {
    putstr("PASSED compute CEASE illegal probes on harts0/1\n");
    /* The expected native capability refusal below stops the process directly. */
    iris_uart_drain();
  }
  barrier();
  if(h==2) {
    __asm__ volatile(".word 0x30500073" ::: "memory");
    putstr("UNEXPECTED hart2 CEASE returned\n");finish(1);
  }
  for(;;)__asm__ volatile("wfi");
}
