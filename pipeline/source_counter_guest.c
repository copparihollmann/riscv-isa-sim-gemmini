#include "runtime.h"
typedef struct {uint64_t c0,c1,t0,t1,pending0,pending1,failed;} Row;
static Row rows[3];
void benchmark_main(unsigned h) {
  barrier();
  __asm__ volatile("csrc mstatus,%0; csrw mie,zero"::"r"(8UL):"memory");
  set_timer(h,mtime()+7);
  __asm__ volatile("csrw mie,%0"::"r"(128UL):"memory");
  rows[h].c0=cycles();rows[h].t0=mtime();
  __asm__ volatile("wfi":::"memory");
  rows[h].c1=cycles();rows[h].t1=mtime();
  set_timer(h,UINT64_MAX);
  __asm__ volatile("csrw mie,%0"::"r"(8UL):"memory");
  send_ipi(h);
  rows[h].pending0=cycles();
  __asm__ volatile("wfi":::"memory");
  rows[h].pending1=cycles();
  *(volatile uint32_t*)(IRIS_CLINT+h*4)=0;
  __asm__ volatile("csrw mie,zero":::"memory");
  rows[h].failed=rows[h].t1-rows[h].t0<4 || rows[h].c1-rows[h].c0>300 || rows[h].pending1-rows[h].pending0>100;
  barrier();
  if(h)for(;;)__asm__ volatile("wfi");
  unsigned bad=0;
  for(unsigned hart=0;hart<3;++hart) {
    Row *r=&rows[hart];bad+=r->failed;
    putstr("SOURCE_WFI {\"hart\":");putuint(hart);putstr(",\"c0\":");putuint(r->c0);putstr(",\"c1\":");putuint(r->c1);
    putstr(",\"t0\":");putuint(r->t0);putstr(",\"t1\":");putuint(r->t1);putstr(",\"pending0\":");putuint(r->pending0);putstr(",\"pending1\":");putuint(r->pending1);
    putstr(",\"failed\":");putuint(r->failed);putstr("}\n");
  }
  putstr("SOURCE_WFI_DONE ");putuint(bad);putstr("\n");finish(bad);
}
