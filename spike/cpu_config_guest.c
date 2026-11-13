#include "runtime.h"
void benchmark_main(unsigned h) {
  uint64_t value;
  if(h<2) {
    expect_illegal[h]=1;
    __asm__ volatile("csrw pmpaddr0,zero" ::: "memory");
    if(expect_illegal[h] || illegal_seen[h]!=1)fail(h,255,__LINE__,illegal_seen[h]);
    expect_illegal[h]=1;
    __asm__ volatile("csrw pmpcfg0,zero" ::: "memory");
    if(expect_illegal[h] || illegal_seen[h]!=2)fail(h,255,__LINE__,illegal_seen[h]);
  } else {
    uint64_t address=0x12345;
    __asm__ volatile("csrw pmpaddr0,%1\n\tcsrr %0,pmpaddr0":"=r"(value):"r"(address):"memory");
    if(value!=address)fail(h,255,__LINE__,value);
    __asm__ volatile("csrw pmpaddr0,zero" ::: "memory");
    __asm__ volatile("csrw pmpaddr7,%1\n\tcsrr %0,pmpaddr7":"=r"(value):"r"(address):"memory");
    if(value!=address)fail(h,255,__LINE__,value);
    __asm__ volatile("csrw pmpaddr7,zero" ::: "memory");
    /* Rocket pads the PMP read map to64 entries; unimplemented slots are RAZ/WI. */
    __asm__ volatile("csrw pmpaddr8,%1\n\tcsrr %0,pmpaddr8":"=r"(value):"r"(UINT64_MAX):"memory");
    if(value)fail(h,255,__LINE__,value);
    __asm__ volatile("csrw pmpcfg2,%1\n\tcsrr %0,pmpcfg2":"=r"(value):"r"(UINT64_MAX):"memory");
    if(value)fail(h,255,__LINE__,value);
  }
  uint64_t sv48=UINT64_C(9)<<60,sv39=UINT64_C(8)<<60;
  __asm__ volatile("csrw satp,zero\n\tcsrw satp,%1\n\tcsrr %0,satp":"=r"(value):"r"(sv48):"memory");
  if(value)fail(h,255,__LINE__,value);
  __asm__ volatile("csrw satp,%1\n\tcsrr %0,satp":"=r"(value):"r"(sv39):"memory");
  if(value!=sv39)fail(h,255,__LINE__,value);
  __asm__ volatile("csrw satp,zero" ::: "memory");
  barrier();
  for(unsigned row=0;row<IRIS_HARTS;++row) {
    if(row==h) {
      putstr("IRIS_CPUCONFIG {\"hart\":");putuint(h);putstr(",\"pmp_entries\":");putuint(h<2?0:8);
      putstr(",\"pmp_illegal_cases\":");putuint(illegal_seen[h]);
      putstr(",\"padded_pmp_read_zero_write_ignored\":");putstr(h==2?"true":"false");
      putstr(",\"sv39\":true,\"sv48_rejected\":true}\n");
    }
    barrier();
  }
  if(!h) {putstr("PASSED heterogeneous CPU configuration\n");finish(0);}
}
