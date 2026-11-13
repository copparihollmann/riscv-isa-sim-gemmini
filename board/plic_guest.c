#include "runtime.h"
#ifndef PLIC_MODE
#define PLIC_MODE 5
#endif
#define PLIC 0x0c000000UL
#define UART 0x10020000UL
#define MEIP (1UL << 11)
#define SEIP (1UL << 9)
static volatile uint64_t observed[3];
static volatile uint64_t external_seen[3];
static volatile uint32_t *reg32(uint64_t offset) { return (volatile uint32_t *)(PLIC + offset); }
static uint64_t pending_bits(void) {
  uint64_t value;
  __asm__ volatile("csrr %0,mip" : "=r"(value) :: "memory");
  return value & (MEIP | SEIP);
}
static void require(int good, unsigned h, unsigned line) {
  if (!good) fail(h, 253, line, 0);
}
extern uint64_t base_trap_dispatch(uint64_t, uint64_t, uint64_t, unsigned);
uint64_t trap_dispatch(uint64_t cause, uint64_t pc, uint64_t value, unsigned h) {
  if (cause == ((1ULL << 63) | 11) || cause == ((1ULL << 63) | 9)) {
    unsigned supervisor = (cause & 63) == 9;
    unsigned context = 2 * h + supervisor;
    require(*reg32(0x200004 + context * 0x1000) == 1, h, __LINE__);
    *(volatile uint32_t *)(UART + 0x10) = 0;
    *reg32(0x200004 + context * 0x1000) = 1;
    external_seen[h] = cause & 63;
    return pc;
  }
  return base_trap_dispatch(cause, pc, value, h);
}

void benchmark_main(unsigned h) {
  __asm__ volatile("csrw mie,zero" ::: "memory");
  set_timer(h, UINT64_MAX);
#if PLIC_MODE == 9
  // Hart 0 parks with an enabled but currently known-low line. Hart 1 then
  // raises the source while its PLIC configuration remains unknown. No next
  // instruction on hart 0 is needed to detect the now-observable unknown.
  barrier();
  if (h == 0) {
    observed[0] = 1;
    memory_fence();
    __asm__ volatile("li t0,2048\n\tcsrw mie,t0\n\twfi" ::: "t0", "memory");
    putstr("UNEXPECTED unknown PLIC WFI wakeup accepted\n"); finish(1);
  }
  if (h == 1) {
    while (!observed[0]) {}
    for (unsigned spin = 0; spin < 10000; ++spin) __asm__ volatile("nop");
    *(volatile uint32_t *)(UART + 8) = 0x10001;
    *(volatile uint32_t *)(UART + 0x10) = 1;
  }
  for (;;) __asm__ volatile("wfi");
#else
#if PLIC_MODE != 5
  if (h) for (;;) __asm__ volatile("wfi");
#if PLIC_MODE == 0
  (void)*reg32(4);
#elif PLIC_MODE == 1
  (void)*reg32(0x2000);
#elif PLIC_MODE == 2
  (void)*reg32(0x200000);
#elif PLIC_MODE == 3 || PLIC_MODE == 4
  // With an empty TX FIFO and watermark one, this is a real UART source-high
  // condition too. This regression checks PLIC semantics, not UART timing.
  *(volatile uint32_t *)(UART + 8) = 0x10001;
  *(volatile uint32_t *)(UART + 0x10) = 1;
#if PLIC_MODE == 3
  __asm__ volatile("li t0,2048\n\tcsrw mie,t0\n\tnop" ::: "t0", "memory");
#else
  (void)pending_bits();
#endif
#elif PLIC_MODE == 6
  require(*reg32(4) == 0 && *reg32(0x2000) == 0 && *reg32(0x200000) == 0, h, __LINE__);
  putstr("PASSED generic PLIC compatibility\n"); finish(0);
#elif PLIC_MODE == 7 || PLIC_MODE == 8
  *reg32(4) = 1;
  for (unsigned c = 0; c < 6; ++c) {
    *reg32(0x2000 + c * 0x80) = c == (PLIC_MODE == 8) ? 2 : 0;
    *reg32(0x200000 + c * 0x1000) = 0;
  }
  *(volatile uint32_t *)(UART + 8) = 0x10001;
  *(volatile uint32_t *)(UART + 0x10) = 1;
  uint64_t enable = PLIC_MODE == 8 ? SEIP : MEIP;
  __asm__ volatile("csrw mie,%0" :: "r"(enable) : "memory");
  for (unsigned spin = 0; spin < 100000 && !external_seen[h]; ++spin)
    __asm__ volatile("nop");
  __asm__ volatile("csrw mie,zero" ::: "memory");
  require(external_seen[h] == (PLIC_MODE == 8 ? 9 : 11), h, __LINE__);
  putstr("PASSED physical PLIC external trap cause "); putuint(external_seen[h]); putstr("\n");
  finish(0);
#endif
  putstr("UNEXPECTED unknown PLIC state accepted\n"); finish(1);
#else
  barrier();
  if (h == 0) {
    *reg32(4) = 1;
    for (unsigned c = 0; c < 6; ++c) {
      *reg32(0x2000 + c * 0x80) = 2;
      *reg32(0x200000 + c * 0x1000) = 0;
    }
    *(volatile uint32_t *)(UART + 8) = 0x10001;
    *(volatile uint32_t *)(UART + 0x10) = 1;
    memory_fence();
  }
  barrier();
  require(pending_bits() == (MEIP | SEIP), h, __LINE__);
  observed[h] = 1;
  barrier();
  if (h == 0) {
    *(volatile uint32_t *)(UART + 0x10) = 0;
    *reg32(0x203000) = 1; // Context 3 = hart 1 supervisor; mask only its IRQ.
    memory_fence();
  }
  barrier();
  require(pending_bits() == (h == 1 ? MEIP : MEIP | SEIP), h, __LINE__);
  ++observed[h];
  barrier();
  if (h == 0) {
    require(*reg32(0x203004) == 1, h, __LINE__); // Claim ignores threshold.
    require(*reg32(0x200004) == 0, h, __LINE__); // Source cannot be claimed twice.
    require(*reg32(0x1000) == 0, h, __LINE__);
    *reg32(0x205004) = 3; // Different enabled context, low-bit source ID aliases 1.
  }
  barrier();
  require(pending_bits() == 0, h, __LINE__);
  ++observed[h];
  barrier();
  if (h == 0) {
    *reg32(0x203000) = 0;
    *(volatile uint32_t *)(UART + 0x10) = 1;
    *reg32(4) = 0;
    require(*reg32(0x200004) == 0 && *reg32(0x1000) == 2, h, __LINE__);
    *reg32(4) = 1;
    require(*reg32(0x204004) == 1, h, __LINE__);
    *(volatile uint32_t *)(UART + 0x10) = 0;
    *reg32(0x200004) = 1;
    require(*(volatile uint32_t *)(PLIC + 0x3fffffc) == 0, h, __LINE__);
    for (unsigned i = 0; i < 3; ++i) {
      require(observed[i] == 3, h, __LINE__);
      putstr("IRIS_PLIC {\"hart\":"); putuint(i);
      putstr(",\"irq_checks\":"); putuint(observed[i]); putstr("}\n");
    }
    putstr("PASSED physical PLIC register and interrupt integration\n");
    finish(0);
  }
  for (;;) __asm__ volatile("wfi");
#endif
#endif
}
