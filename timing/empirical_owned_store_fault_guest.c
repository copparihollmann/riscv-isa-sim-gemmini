/* Finite fallback witness; not fitting data or a complete MMU test. */
#include "runtime.h"
#ifndef IRIS_STORE_TEST_MPRV
#define IRIS_STORE_TEST_MPRV 0
#endif
extern volatile uint64_t expected_store_fault[3], store_fault_seen[3];
typedef struct __attribute__((aligned(64))) { uint64_t words[8]; } line_t;
typedef struct __attribute__((aligned(64))) { uint64_t failed, faults; } row_t;
static line_t lines[3];
static row_t rows[3];
static void faulting_store(unsigned h, uintptr_t address, unsigned cause) {
  expected_store_fault[h]=cause;
  __asm__ volatile(".option push\n.option norvc\nsd %0,0(%1)\n.option pop"
                   ::"r"(0x12345678ul),"r"(address):"memory");
}
void benchmark_main(unsigned h) {
  volatile uint64_t *p=lines[h].words;
  for (unsigned i=0;i<8;++i) p[i]=0;
  for (unsigned i=0;i<16;++i) p[0]=i+100;
  uint64_t failed=p[0]!=115;
  const uint64_t rom=*(volatile uint64_t *)(uintptr_t)0x10000;
  faulting_store(h,0x10000,7);
  failed+=expected_store_fault[h]!=0;
  failed+=*(volatile uint64_t *)(uintptr_t)0x10000!=rom;
  faulting_store(h,0x180000000ul,7);
  failed+=expected_store_fault[h]!=0;
  faulting_store(h,(uintptr_t)p+1,6);
  failed+=expected_store_fault[h]!=0 || p[0]!=115 || p[1]!=0;
  /* MPRV is an existing explicit translated-memory capability refusal. */
  if (IRIS_STORE_TEST_MPRV) {
  uint64_t old;
  __asm__ volatile("csrr %0,mstatus":"=r"(old));
  __asm__ volatile("csrw mstatus,%0"::"r"(old|0x21800ul):"memory");
  __asm__ volatile(".option push\n.option norvc\nsd %0,0(%1)\n.option pop"
                   ::"r"(456ul),"r"(p):"memory");
  __asm__ volatile("csrw mstatus,%0"::"r"(old):"memory");
  failed+=p[0]!=456;
  }
  failed+=store_fault_seen[h]!=3;
  rows[h]=(row_t){failed,store_fault_seen[h]};
  barrier();
  if (h==0) {
    unsigned total=0;
    for (unsigned i=0;i<3;++i) {
      total+=rows[i].failed;
      putstr("IRIS_STORE_FAULT ");putuint(i);putstr(" ");
      putuint(rows[i].failed);putstr(" ");putuint(rows[i].faults);putstr("\n");
    }
    finish(total);
  }
  for (;;) __asm__ volatile("wfi");
}
