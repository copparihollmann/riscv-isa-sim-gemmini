#include <zephyr/kernel.h>
#include <zephyr/devicetree.h>
#include <zephyr/sys/sys_io.h>
#include <stdint.h>
#include <string.h>
#include "kernels.h"
typedef struct { unsigned tier, kind, bytes, repeats, pitch, rows; } roof_case;
#include "cases.inc"
enum { MAX_BYTES = 8388608, GUARD = 64 };
unsigned char roof_dram[3 * (MAX_BYTES + 2 * GUARD)] __attribute__((aligned(64)));
extern volatile uint64_t tohost;
static struct k_sem start, done;
static struct k_thread worker_thread, control_thread;
K_THREAD_STACK_DEFINE(worker_stack, 8192);
K_THREAD_STACK_DEFINE(control_stack, 8192);
static unsigned case_index, pass_index, failed;
typedef struct { uint64_t begin, end, ibegin, iend, tb, te, value; } sample;
static sample measured;
static unsigned char *pa, *pb, *pc;
static inline uint64_t cycle(void) { uint64_t x; __asm__ volatile("csrr %0,mcycle":"=r"(x)); return x; }
static inline uint64_t retired(void) { uint64_t x; __asm__ volatile("csrr %0,minstret":"=r"(x)); return x; }
static inline unsigned hart(void) { unsigned long x; __asm__ volatile("csrr %0,mhartid":"=r"(x)); return x; }
static inline uint64_t ticks(void) { return *(volatile uint64_t *)0x0200bff8UL; }
static void fence(void) { __asm__ volatile("fence rw,rw" ::: "memory"); }
static uint32_t aval(size_t i) { return (17 * i + 11) & 65535; }
static uint32_t bval(size_t i) { return (29 * i + 23) & 65535; }
static size_t footprint(const roof_case *c) { return c->kind == PANEL ? c->pitch * c->rows : c->bytes; }
static void select_memory(const roof_case *c) {
  size_t stride = c->tier == 0 ? MAX_BYTES + 128 : c->tier == 1 ? 16384 + 128 : 32768 + 128;
  uintptr_t base = c->tier == 0 ? (uintptr_t)roof_dram : c->tier == 1 ? 0x70010000UL : 0x580000000UL;
  pa = (unsigned char *)base + GUARD; pb = pa + stride; pc = pb + stride;
}
static void prepare(const roof_case *c) {
  size_t n = footprint(c);
  for (unsigned which = 0; which < 3; ++which) {
    unsigned char *p = which == 0 ? pa : which == 1 ? pb : pc;
    memset(p - GUARD, 0x5a, GUARD); memset(p + n, 0x5a, GUARD);
  }
  if (c->kind == PANEL) {
    for (size_t row = 0; row < c->rows; ++row)
      for (size_t i = 0; i < c->bytes / 4; ++i)
        ((uint32_t *)(pa + row * c->pitch))[i] = aval(row * c->pitch / 4 + i);
    fence(); return;
  }
  uint32_t *a = (uint32_t *)pa, *b = (uint32_t *)pb;
  for (size_t i = 0; i < n / 4; ++i) { a[i] = aval(i); b[i] = bval(i); }
  memset(pc, 0xa5, n);
  if (c->kind == CHASE) {
    size_t nodes = c->bytes / 64;
    for (size_t i = 0; i < nodes; ++i)
      *(uintptr_t *)(pa + 64 * ((i * 13) & (nodes - 1))) =
          (uintptr_t)(pa + 64 * (((i + 1) * 13) & (nodes - 1)));
  }
  fence();
}
static int validate(const roof_case *c, uint64_t *checksum) {
  size_t n = footprint(c); uint64_t value = 0;
  for (unsigned which = 0; which < 3; ++which) {
    unsigned char *p = which == 0 ? pa : which == 1 ? pb : pc;
    for (unsigned i = 0; i < GUARD; ++i)
      if (p[-GUARD + (int)i] != 0x5a || p[n + i] != 0x5a) return -1;
  }
  if (c->kind == CHASE) {
    uint64_t nodes = c->bytes / 64, laps = c->repeats;
    value = laps * (nodes * (uintptr_t)pa + 64 * (nodes * (nodes - 1) / 2));
  } else if (c->kind == READ_SUM || c->kind == SCALAR_SUM || c->kind == PANEL) {
    uint32_t s = 0;
    for (size_t row = 0; row < (c->kind == PANEL ? c->rows : 1); ++row)
      for (size_t i = 0; i < c->bytes / 4; ++i) s += aval(row * c->pitch / 4 + i);
    value = (uint32_t)(s * c->repeats);
  } else {
    uint32_t *out = (uint32_t *)pc;
    for (size_t i = 0; i < c->bytes / 4; ++i) {
      uint32_t expected = c->kind == WRITE ? UINT32_C(0x3c3c3c3c) :
          c->kind == COPY ? aval(i) : aval(i) + 3 * bval(i);
      if (out[i] != expected) return -2;
      value += (uint64_t)out[i] * (i + 1);
    }
    *checksum = value; return 0;
  }
  *checksum = value; return measured.value == value ? 0 : -3;
}
static void worker(void *x, void *y, void *z) {
  (void)x; (void)y; (void)z;
  for (;;) {
    k_sem_take(&start, K_FOREVER);
    const roof_case *c = &roof_cases[case_index];
    if (hart() != 0) k_panic();
    fence(); measured.tb = ticks(); measured.begin = cycle(); measured.ibegin = retired();
#ifndef ROOF_SKIP_KERNEL
    measured.value = roof_kernel(c->kind, pa, pb, pc, c->bytes, c->repeats, c->pitch, c->rows);
#else
    measured.value = 0;
#endif
    /* Stores must complete architecturally before ending the window. This
     * fence is measured; it does not force dirty cache lines to DRAM. */
    fence(); measured.iend = retired(); measured.end = cycle(); measured.te = ticks();
    k_sem_give(&done);
  }
}
static void controller(void *x, void *y, void *z) {
  (void)x; (void)y; (void)z;
  if (hart() != 2) k_panic();
  printk("IRIS_PROGRESS v1 START %u\n", (unsigned)(ROOF_CASES * 3));
  unsigned completed = 0;
  for (case_index = 0; case_index < ROOF_CASES && !failed; ++case_index) {
    const roof_case *c = &roof_cases[case_index]; select_memory(c); prepare(c);
    for (pass_index = 0; pass_index < 3 && !failed; ++pass_index) {
      /* Reject stale correct output if a later invocation omits stores.
       * Correctness poisoning stays outside the measured H0 window. */
      if (c->kind == WRITE || c->kind == COPY || c->kind == TRIAD) {
        memset(pc, 0xa5, c->bytes); fence();
      }
      /* H2 blocks during the measured H0 kernel; no polling or UART traffic. */
      k_sem_give(&start); k_sem_take(&done, K_FOREVER);
      uint64_t checksum = 0; int status = validate(c, &checksum);
      failed = status != 0;
      printk("IRIS_REGION {\"case_id\":\"memroof_c%u_r%u\",\"region\":\"memory_kernel\",\"hart\":0,\"start_cycle\":%llu,\"end_cycle\":%llu,\"start_instret\":%llu,\"end_instret\":%llu,\"instret_delta\":%llu,\"checksum\":%llu,\"warmup\":false,\"pass\":%s}\n",
          case_index, pass_index, measured.begin, measured.end, measured.ibegin, measured.iend,
          measured.iend - measured.ibegin, checksum, status ? "false" : "true");
      printk("IRIS_MEMROOF %u %u %u %u %u %u %u %u %llu %llu %llu %d\n",
          case_index, pass_index, c->tier, c->kind, c->bytes, c->repeats, c->pitch, c->rows,
          measured.tb, measured.te, checksum, status);
      if (!failed) printk("IRIS_PROGRESS v1 DONE %u memroof_c%u_r%u %llu\n", ++completed, case_index, pass_index, checksum);
    }
  }
  printk("IRIS_BATCH_DONE passed=%u failed=%u\n", completed, failed);
  if (!failed) printk("DONE\n");
#if DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), sifive_uart0)
  uintptr_t uart = DT_REG_ADDR(DT_CHOSEN(zephyr_console));
  uint32_t ctrl = sys_read32(uart + 8);
  sys_write32((ctrl & ~(0x1ffu << 16)) | (1u << 16), uart + 8);
  while (!(sys_read32(uart + 0x14) & 1)) k_yield();
  k_sleep(K_MSEC(1));
#endif
  fence(); tohost = failed ? 3 : 1; fence();
  for (;;) __asm__ volatile("wfi");
}
int main(void) {
  k_sem_init(&start, 0, 1); k_sem_init(&done, 0, 1);
  k_tid_t w = k_thread_create(&worker_thread, worker_stack, K_THREAD_STACK_SIZEOF(worker_stack), worker,
      NULL, NULL, NULL, K_PRIO_COOP(0), 0, K_FOREVER);
  k_tid_t c = k_thread_create(&control_thread, control_stack, K_THREAD_STACK_SIZEOF(control_stack), controller,
      NULL, NULL, NULL, K_PRIO_COOP(0), 0, K_FOREVER);
  if (k_thread_cpu_pin(w, 0) || k_thread_cpu_pin(c, 2)) k_panic();
  k_thread_start(w); k_thread_start(c);
  for (;;) k_sleep(K_SECONDS(3600));
}
