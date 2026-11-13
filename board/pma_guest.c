#include "runtime.h"

struct recovery { volatile uint64_t pc, cause, address, seen; };
static struct recovery recovery[IRIS_HARTS] __attribute__((aligned(64)));

uint64_t trap_dispatch(uint64_t cause, uint64_t pc, uint64_t value, unsigned h) {
  struct recovery *r = &recovery[h];
  if (r->cause == cause && r->address == value && r->pc) {
    r->cause = 0; ++r->seen; return r->pc;
  }
  fail(h, cause, pc, value);
}

#define FAULT(INSTRUCTION, ADDRESS, CAUSE) do { \
  uint64_t address_ = (ADDRESS), before_ = recovery[h].seen; \
  recovery[h].cause = (CAUSE); recovery[h].address = address_; \
  __asm__ volatile("la t1,1f\n\tsd t1,0(%1)\n\t" INSTRUCTION "\n1:" \
    :: "r"(address_), "r"(&recovery[h].pc) : "t0", "t1", "memory"); \
  if (recovery[h].cause || recovery[h].seen != before_ + 1) fail(h, 255, __LINE__, address_); \
} while (0)

void benchmark_main(unsigned h) {
  __asm__ volatile("csrw mie,zero" ::: "memory");
  set_timer(h, UINT64_MAX);
  FAULT("ld t0,0(%0)", 0x60000000ULL, 5);
  FAULT("sd zero,0(%0)", 0x10000ULL, 7);
  FAULT("jalr zero,0(%0)", 0x10020000ULL, 1);
  FAULT("lr.d t0,(%0)", 0x580000000ULL + 64*h, 5);
  FAULT("sc.d t0,zero,(%0)", 0x580000000ULL + 64*h, 7);
  FAULT("amoadd.d t0,zero,(%0)", 0x580000000ULL + 64*h, 7);
  FAULT("ld t0,0(%0)", 0x180000000ULL, 5);
  FAULT("ld t0,0(%0)", 0x580020000ULL, 5);
  /* PMA must distinguish ordinary executable RAM from nonexecutable MMIO. */
  volatile uint32_t *tcm = (volatile uint32_t *)(0x70000000ULL + h*64);
  volatile uint32_t *scratch = (volatile uint32_t *)(0x580000000ULL + h*64);
  tcm[0] = scratch[0] = 0x02a00513; /* addi a0,zero,42 */
  tcm[1] = scratch[1] = 0x00008067; /* jalr zero,ra,0 */
  __asm__ volatile("fence rw,rw\n\tfence.i" ::: "memory");
  if (((uint64_t (*)(void))(uintptr_t)tcm)() != 42 ||
      ((uint64_t (*)(void))(uintptr_t)scratch)() != 42) fail(h, 255, __LINE__, 0);
  volatile uint64_t *last = (volatile uint64_t *)(0x17ffffff8ULL - h*64);
  *last = 100 + h;
  if (*last != 100 + h) fail(h, 255, __LINE__, *last);
  unsigned aliases=0;
  if (h < 2) {
    uint64_t own=0x70000000ULL+h*0x20000ULL;
    volatile uint64_t *canonical=(volatile uint64_t *)(own+0x100);
    for (unsigned copy=0;copy<4;++copy) {
      volatile uint64_t *alias=(volatile uint64_t *)(0x70080000ULL+copy*0x20000ULL+0x100);
      uint64_t value=1000+h*10+copy,old;
      *alias=value;
      if (*canonical!=value) fail(h,255,__LINE__,*canonical);
      __asm__ volatile("amoadd.d %0,%2,(%1)":"=r"(old):"r"(alias),"r"(1UL):"memory");
      if (old!=value || *canonical!=value+1) fail(h,255,__LINE__,old);
      /* Uncached TCM supports AMOs, but source TLBs prohibit LR/SC. */
      FAULT("lr.d t0,(%0)",(uintptr_t)alias,5);
      FAULT("sc.d t0,zero,(%0)",(uintptr_t)alias,7);
      volatile uint32_t *code=(volatile uint32_t *)(own+0x200);
      code[0]=0x02a00513; code[1]=0x00008067;
      __asm__ volatile("fence rw,rw\n\tfence.i":::"memory");
      if (((uint64_t (*)(void))(0x70080000ULL+copy*0x20000ULL+0x200))()!=42)
        fail(h,255,__LINE__,copy);
      ++aliases;
    }
    volatile uint32_t *source=(volatile uint32_t *)(own+0x400), *dest=(volatile uint32_t *)(own+0x440);
    for(unsigned i=0;i<4;++i) source[i]=200+h*10+i;
    __asm__ volatile("vsetivli zero,4,e32,m1,ta,ma\n\tvle32.v v8,(%0)\n\tvse32.v v8,(%1)\n\tfence rw,rw"
      ::"r"(0x700c0400ULL),"r"(dest):"memory");
    for(unsigned i=0;i<4;++i) if(dest[i]!=source[i]) fail(h,255,__LINE__,dest[i]);
  } else {
    for(unsigned copy=0;copy<4;++copy) FAULT("ld t0,0(%0)",0x70080000ULL+copy*0x20000ULL,5);
    FAULT("sd zero,0(%0)",0x70080000ULL,7);
    FAULT("jalr zero,0(%0)",0x70080000ULL,1);
  }
  FAULT("lr.d t0,(%0)",0x70000000ULL+h*64,5);
  FAULT("sc.d t0,zero,(%0)",0x70000000ULL+h*64,7);
  barrier();
  for(unsigned owner=0;owner<2;++owner) {
    volatile uint64_t *canonical=(volatile uint64_t *)(0x70000100ULL+owner*0x20000ULL);
    if(h==owner) *canonical=1;
    barrier();
    if(h==2) {
      uint64_t old;
      __asm__ volatile("amoswap.d.aqrl %0,%2,(%1)":"=r"(old):"r"(canonical),"r"(777UL):"memory");
      if(old!=1) fail(h,255,__LINE__,old);
    }
    barrier();
    if(h==owner) {
      if(*(volatile uint64_t *)0x70080100ULL!=777 || *canonical!=777)
        fail(h,255,__LINE__,*canonical);
    }
    barrier();
  }
  if(h<2) {
    /* Compute harts implement no PMP entries. */
    FAULT(".word 0x3b001073",0x3b001073ULL,2);
  } else {
    volatile uint64_t *canonical=(volatile uint64_t *)0x70002500ULL;
    *canonical=55;
    uint64_t pmp_address=0x70002500ULL>>2;
    /* Rocket has eight PMP entries and supports locked read-only NAPOT8. */
    __asm__ volatile("csrw pmpaddr0,%0\n\tli t0,153\n\tcsrw pmpcfg0,t0"::"r"(pmp_address):"t0","memory");
    if(*canonical!=55) fail(h,255,__LINE__,*canonical);
    FAULT("sd zero,0(%0)",0x70002500ULL,7);
    uint64_t absent;
    __asm__ volatile("li t0,1\n\tcsrw pmpaddr8,t0\n\tcsrr %0,pmpaddr8":"=r"(absent)::"t0","memory");
    if(absent) fail(h,255,__LINE__,absent);
  }
  barrier();
  for (unsigned row=0; row<IRIS_HARTS; ++row) {
    if (h == row) {
      putstr("IRIS_PMA {\"hart\":"); putuint(h);
      putstr(",\"faults\":"); putuint(recovery[h].seen);
      putstr(",\"private_aliases\":"); putuint(aliases);
      putstr(",\"pmp_regions\":"); putuint(h<2?0:8);
      putstr(",\"uncached_lrsc_refused\":true,\"alias_peer_atomic_storage\":true,\"ram_execute\":true,\"dram_last_page\":true}\n");
    }
    barrier();
  }
  if (!h) { putstr("PASSED physical PMA\n"); finish(0); }
}
