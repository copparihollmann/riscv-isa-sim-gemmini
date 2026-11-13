#include "runtime.h"
#ifndef TEST_HART
#define TEST_HART 2
#endif
void benchmark_main(unsigned h) {
  barrier();
  if(h!=TEST_HART)for(;;)__asm__ volatile("wfi");
  expect_illegal[h]=1;
  __asm__ volatile(".word 0x30500073":::"memory");
  unsigned bad=illegal_seen[h]!=1;
  putstr("PASSED source Shuttle CEASE refusal\n");finish(bad);
}
