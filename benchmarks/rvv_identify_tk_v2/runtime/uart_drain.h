#ifndef IRIS_BENCH_UART_DRAIN_H
#define IRIS_BENCH_UART_DRAIN_H
#include "runtime.h"

/* Source-bound Iris UART/CLINT clocks (hardware/memory-paths.json):
 * UART500MHz, mtime500kHz. Use RTC rather than writable/inhibitable mcycle.
 * Producers must be quiescent and controls stable while this function drains.
 * UART.scala/TX retains an old prescaler when DIV changes. The universal bound
 * includes that full16-bit residue, remaining frame pulses and final stop time.
 */
static inline void iris_uart_drain(void) {
  volatile uint32_t *uart=(volatile uint32_t *)0x10020000ul;
  const uint32_t control=uart[2];
  uart[2]=(control & ~(0x1ffu<<16)) | (1u<<16);
  memory_fence();
  while (!(uart[5]&1u)) {}
  const uint64_t divisor=uart[6]&0xffffu;
  const uint64_t edges=65536ull+11ull*(divisor+1);
  const uint64_t ticks=(edges+999)/1000+1;
  const uint64_t begin=mtime();
  while ((uint64_t)(mtime()-begin)<ticks) {}
  memory_fence();
}
#endif
