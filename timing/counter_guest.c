#include "runtime.h"

struct sample {
  uint64_t cycles, instructions, frozen, resumed, written, ret_written, ret_frozen, illegal;
  uint64_t time_before, clint, time_after, rdtime_illegal, wake_cycles, wake_ticks, woke, checksum;
};
static struct sample samples[3] __attribute__((aligned(64)));
static unsigned failed;
static uint64_t work(unsigned n, uint64_t x) {
  for (unsigned i = 0; i < n; ++i) __asm__ volatile("addi %0,%0,3":"+r"(x));
  return x;
}
static void field(const char* name, uint64_t value) { putstr(name); putuint(value); }
void benchmark_main(unsigned hart) {
  barrier();
  struct sample s;
  uint64_t start = cycles(), begin = retired();
  s.checksum = work(64, hart + 1);
  s.instructions = retired() - begin; s.cycles = cycles() - start;
  __asm__ volatile("csrs mcountinhibit,%0"::"r"(1UL):"memory");
  start = cycles(); work(32, 1); s.frozen = cycles() - start;
  __asm__ volatile("csrc mcountinhibit,%0"::"r"(1UL):"memory");
  start = cycles(); work(16, 1); s.resumed = cycles() - start;
  __asm__ volatile("csrs mcountinhibit,%0"::"r"(4UL):"memory");
  begin = retired();
  work(16, 1); expect_illegal[hart] = 1;
  __asm__ volatile(".globl iris_counter_fault\niris_counter_fault:\n.word 0x0000007b":::"memory");
  s.ret_frozen = retired() - begin; s.illegal = illegal_seen[hart];
  __asm__ volatile("csrc mcountinhibit,%0"::"r"(4UL):"memory");
  __asm__ volatile("li t0,100\n\tcsrw minstret,t0\n\tcsrr %0,minstret":"=r"(s.ret_written)::"t0","memory");
  __asm__ volatile("li t0,7\n\tcsrw mcycle,t0\n\tcsrr %0,mcycle":"=r"(s.written)::"t0","memory");
  s.time_before = mtime();
  const uint64_t prior_illegal=illegal_seen[hart];
  expect_illegal[hart]=1;
  __asm__ volatile(".globl iris_counter_time_fault\niris_counter_time_fault:\n.word 0xc01022f3":::"t0","memory");
  s.rdtime_illegal=illegal_seen[hart]-prior_illegal;
  if(expect_illegal[hart])fail(hart,255,__LINE__,expect_illegal[hart]);
  s.clint = mtime(); s.time_after = mtime();
  uint64_t previous = timer_seen[hart], target = mtime() + 16;
  set_timer(hart, target);
  __asm__ volatile("csrs mie,%0"::"r"(128UL):"memory");
  start = cycles(); uint64_t tick_start = mtime();
  while (timer_seen[hart] == previous) {
    __asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory");
    if (timer_seen[hart] == previous) __asm__ volatile("wfi":::"memory");
    __asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
  }
  s.wake_cycles = cycles() - start; s.wake_ticks = mtime() - tick_start;
  s.woke = timer_seen[hart] - previous;
  __asm__ volatile("csrc mie,%0"::"r"(128UL):"memory");
  samples[hart] = s;
  barrier();
  if (hart == 0) {
    for (unsigned h = 0; h < 3; ++h) {
      struct sample v = samples[h];
      if (v.checksum != 193 + h || v.frozen || v.ret_frozen || v.ret_written != 100 ||
          v.illegal != 1 || !v.resumed || v.written < 7 ||
          v.written > 1000 || v.rdtime_illegal!=1 || !v.time_before || v.time_before > v.clint ||
          v.clint > v.time_after || v.woke != 1) ++failed;
      putstr("IRIS_TIMING {\"hart\":"); putuint(h);
      field(",\"cycles\":", v.cycles); field(",\"instructions\":", v.instructions);
      field(",\"frozen\":", v.frozen); field(",\"resumed\":", v.resumed);
      field(",\"written\":", v.written); field(",\"time_before\":", v.time_before);
      field(",\"ret_written\":", v.ret_written); field(",\"ret_frozen\":", v.ret_frozen);
      field(",\"illegal\":", v.illegal);
      field(",\"rdtime_illegal\":", v.rdtime_illegal);
      field(",\"clint\":", v.clint); field(",\"time_after\":", v.time_after);
      field(",\"wake_cycles\":", v.wake_cycles); field(",\"wake_ticks\":", v.wake_ticks);
      field(",\"woke\":", v.woke); field(",\"checksum\":", v.checksum);
      putstr("}\n");
    }
    putstr(failed ? "FAILED timing integration\n" : "PASSED timing integration\n");
    finish(failed ? 1 : 0);
  }
  for (;;) __asm__ volatile("wfi");
}
