/* Package check: unchanged RVV work must see a changed modeled service cost.
 * This is independent of calibration and is never a fitting benchmark.
 */
#include "runtime.h"

typedef struct __attribute__((aligned(64))) {
  uint64_t start, end, instret, checksum, vl, failed;
} record_t;
static record_t records[IRIS_HARTS];
static uint32_t values[IRIS_HARTS][8] __attribute__((aligned(64)));

void benchmark_main(unsigned h) {
  __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");
  set_timer(h,UINT64_MAX);*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;memory_fence();
  unsigned long vl;
  __asm__ volatile("vsetivli %0,8,e32,m1,ta,ma\n\tvmv.v.i v8,3\n\tvmv.v.i v9,1"
                   : "=r"(vl) :: "memory");
  __asm__ volatile("csrc mstatus,%0"::"r"(0x6000UL):"memory");
  barrier();
  uint64_t start = cycles(), first = retired();
  for (unsigned i = 0; i < 32; ++i)
    __asm__ volatile("vadd.vv v8,v8,v9" ::: "memory");
  uint64_t last = retired(), end = cycles();
  __asm__ volatile("vse32.v v8,(%0)" :: "r"(values[h]) : "memory");
  memory_fence();
  uint64_t checksum = 0, failed = vl != 8;
  for (unsigned i = 0; i < 8; ++i) {
    checksum += values[h][i];
    failed += values[h][i] != 35;
  }
  records[h] = (record_t){start, end, last - first, checksum, vl, failed};
  barrier();
  if (h == 0) {
    unsigned total = 0;
    for (unsigned hart = 0; hart < IRIS_HARTS; ++hart) {
      record_t *r = &records[hart];
      putstr("IRIS_TIME_SENSITIVITY {\"hart\":"); putuint(hart);
      putstr(",\"start_cycle\":"); putuint(r->start);
      putstr(",\"end_cycle\":"); putuint(r->end);
      putstr(",\"instret_delta\":"); putuint(r->instret);
      putstr(",\"checksum\":"); putuint(r->checksum);
      putstr(",\"vl\":"); putuint(r->vl);
      putstr(",\"failed\":"); putuint(r->failed); putstr("}\n");
      total += r->failed;
    }
    putstr("IRIS_TIME_DONE {\"failed\":"); putuint(total); putstr("}\n");
    finish(total != 0);
  }
  for (;;) __asm__ volatile("wfi");
}
