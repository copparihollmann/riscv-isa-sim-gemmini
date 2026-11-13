#include "runtime.h"
#include "csr_case_switch.h"

void benchmark_main(unsigned hart) {
  barrier();
  uint64_t value,checks=0;
  const uint64_t ones=UINT64_MAX;
#define CHECK(actual,expected) do { ++checks; if ((actual)!=(expected)) fail(hart,255,__LINE__,(actual)); } while(0)
  __asm__ volatile("csrw mcounteren,%1\n csrr %0,mcounteren":"=r"(value):"r"(ones):"memory");CHECK(value,7);
  __asm__ volatile("csrw scounteren,%1\n csrr %0,scounteren":"=r"(value):"r"(ones):"memory");CHECK(value,7);
  __asm__ volatile("csrw mcountinhibit,%1\n csrr %0,mcountinhibit":"=r"(value):"r"(ones):"memory");CHECK(value,5);
  __asm__ volatile("csrw mcountinhibit,zero":::"memory");
  for(unsigned slot=0;slot<29;++slot) {
    CHECK(read_mhpm(slot),0);write_mhpm(slot,ones);CHECK(read_mhpm(slot),0);
    write_event(slot,ones);CHECK(read_event(slot),0);CHECK(read_hpm(slot),0);
  }
  const uint64_t prior=illegal_seen[hart];
  expect_illegal[hart]=1;
  __asm__ volatile(".word 0xc01022f3":::"t0","memory");
  CHECK(expect_illegal[hart],0);CHECK(illegal_seen[hart]-prior,1);
  const uint64_t before=mtime();while(mtime()==before) {}
  CHECK(mtime()>before,1);
  barrier();
  for(unsigned row=0;row<IRIS_HARTS;++row) {
    if(row==hart) {
      putstr("IRIS_CSRCONFIG {\"hart\":");putuint(hart);
      putstr(",\"checks\":");putuint(checks);
      putstr(",\"hardware_hpm_counters\":0,\"padded_slots\":29,\"mcounteren\":7,\"scounteren\":7,\"mcountinhibit\":5,\"rdtime_illegal\":true,\"mtime_advances\":true}\n");
    }
    barrier();
  }
  if(!hart) {putstr("PASSED source-configured CSR capabilities on all3 harts\n");finish(0);}
  for(;;)__asm__ volatile("wfi");
}
