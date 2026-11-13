#include "runtime.h"
#include "uart_drain.h"
volatile uint64_t tohost __attribute__((section(".tohost"),aligned(64)));
volatile uint64_t fromhost __attribute__((section(".tohost"),aligned(64)));
volatile uint64_t ipi_seen[IRIS_HARTS], timer_seen[IRIS_HARTS];
volatile uint64_t expect_illegal[IRIS_HARTS], illegal_seen[IRIS_HARTS];
static unsigned arrivals, generation;
void putstr(const char *s) {
  volatile uint32_t *tx = (volatile uint32_t *)0x10020000UL;
  while (*s) { while ((int32_t)*tx < 0) {} *tx = (uint8_t)*s++; }
}
void putuint(uint64_t value) {
  char buffer[21]; unsigned n=0;
  do { buffer[n++] = '0' + value%10; value/=10; } while(value);
  while(n) { char c[2]={buffer[--n],0}; putstr(c); }
}
void finish(unsigned status) {
  iris_uart_drain();
  memory_fence(); tohost = ((uint64_t)status << 1) | 1; memory_fence();
  for (;;) __asm__ volatile("nop"); /* post-ROI HTIF host handoff */
}
void fail(unsigned h, uint64_t cause, uint64_t pc, uint64_t value) {
  putstr("IRIS_FATAL {\"hart\":"); putuint(h);
  putstr(",\"cause\":"); putuint(cause);
  putstr(",\"pc\":"); putuint(pc);
  putstr(",\"trap_value\":"); putuint(value); putstr("}\n");
  finish(1);
}
uint64_t trap_dispatch(uint64_t cause, uint64_t pc, uint64_t value, unsigned h) {
  if (cause == ((1ULL<<63)|3)) {
    *(volatile uint32_t *)(IRIS_CLINT + 4*h)=0;
    memory_fence(); ++ipi_seen[h]; return pc;
  }
  if (cause == ((1ULL<<63)|7)) {
    set_timer(h, UINT64_MAX); ++timer_seen[h]; return pc;
  }
  if (cause == 2 && expect_illegal[h]) {
    expect_illegal[h]=0; ++illegal_seen[h]; return pc+4;
  }
  fail(h,cause,pc,value);
}
/* Reusable generation barrier. DRAM atomics publish before MMIO wakeups.
 * Global MIE stays masked across generation-check -> WFI, so an MSIP arriving
 * in that interval remains pending and makes WFI return instead of being lost.
 * Local mie.MSIE is initialized by unchanged start.S; preserve caller MIE.
 */
void barrier(void) {
  unsigned h=hart_id();
  unsigned g=__atomic_load_n(&generation,__ATOMIC_ACQUIRE);
  if (__atomic_add_fetch(&arrivals,1,__ATOMIC_ACQ_REL)==IRIS_HARTS) {
    __atomic_store_n(&arrivals,0,__ATOMIC_RELAXED);
    __atomic_add_fetch(&generation,1,__ATOMIC_RELEASE);
    __asm__ volatile("fence iorw,iorw" ::: "memory");
    for(unsigned peer=0;peer<IRIS_HARTS;++peer)if(peer!=h)send_ipi(peer);
  } else for (;;) {
    unsigned long saved;
    __asm__ volatile("csrrc %0,mstatus,%1":"=r"(saved):"r"(8UL):"memory");
    unsigned next=__atomic_load_n(&generation,__ATOMIC_ACQUIRE);
    if(next==g)__asm__ volatile("wfi" ::: "memory");
    if(saved&8UL)__asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
    if(next!=g)break;
  }
}
