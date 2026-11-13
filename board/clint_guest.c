#include "runtime.h"
#ifndef CLINT_MODE
#define CLINT_MODE 0
#endif

void benchmark_main(unsigned h) {
  __asm__ volatile("csrw mie,zero" ::: "memory");
  if (h) for (;;) __asm__ volatile("wfi");
  volatile uint64_t *compare = (volatile uint64_t *)(IRIS_CLINT + 0x4000);
#if CLINT_MODE == 0
  (void)*compare;
#elif CLINT_MODE == 1
  __asm__ volatile("li t0,128\n\tcsrw mie,t0\n\tnop" ::: "t0", "memory");
#elif CLINT_MODE == 2
  __asm__ volatile("csrr t0,mip" ::: "t0", "memory");
#elif CLINT_MODE == 3
  volatile uint32_t *halves = (volatile uint32_t *)compare;
  halves[0] = 0xffffffff;
  (void)*compare;
#elif CLINT_MODE == 4
  volatile uint32_t *halves = (volatile uint32_t *)compare;
  halves[1] = 0xffffffff;
  halves[0] = 0xffffffff;
  if (*compare != UINT64_MAX) fail(h, 255, __LINE__, *compare);
  __asm__ volatile("csrr t0,mip" ::: "t0", "memory");
  *compare = 0;
  uint64_t pending;
  __asm__ volatile("csrr %0,mip" : "=r"(pending) :: "memory");
  if (!(pending & 128)) fail(h, 255, __LINE__, pending);
  *compare = UINT64_MAX;
  __asm__ volatile("csrr %0,mip" : "=r"(pending) :: "memory");
  if (pending & 128) fail(h, 255, __LINE__, pending);
  putstr("PASSED initialized CLINT compare and MTIP\n"); finish(0);
#elif CLINT_MODE == 5
  /* No pending value reaches software; these input bits are read-only. */
  __asm__ volatile("csrw mip,zero\n\tcsrrs zero,mip,zero\n\tcsrrc zero,mip,zero" ::: "memory");
  putstr("PASSED unobserved pending CSR\n"); finish(0);
#endif
  putstr("UNEXPECTED uninitialized CLINT accepted\n"); finish(1);
}
