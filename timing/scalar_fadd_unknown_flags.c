#include "runtime.h"
#ifndef SCALAR_UNKNOWN_HART
#define SCALAR_UNKNOWN_HART 0
#endif

void benchmark_main(unsigned hart) {
  if (hart != SCALAR_UNKNOWN_HART) {
    for (;;) __asm__ volatile("wfi");
  }
  const uint64_t one = UINT64_C(0x3ff0000000000000);
  uint64_t result;
  __asm__ volatile("fmv.d.x ft0,%1\nfmv.d.x ft1,%1\n"
                   "fadd.d ft2,ft0,ft1,rne\nfmv.x.d %0,ft2"
                   : "=r"(result) : "r"(one) : "ft0", "ft1", "ft2");
  if (result != UINT64_C(0x4000000000000000)) finish(1);
  /* Exact2 has no exception flags. ORing zero must preserve unreset unknowns. */
  uint64_t flags;
  __asm__ volatile("csrr %0,fflags" : "=r"(flags));
  /* Copies transport masks. Require those bits through actual dynamic FRM. */
  __asm__ volatile("csrw frm,%0\nfadd.d ft3,ft0,ft1,dyn"
                   :: "r"(flags) : "ft3");
  finish(2); /* A defined FFLAGS value here would violate the source contract. */
}
