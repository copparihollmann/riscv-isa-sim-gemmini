#include "runtime.h"
struct measurement {uint64_t begin,end,retired,checksum;};
static struct measurement measured[3][3];
static volatile unsigned failed[3];
static inline uint64_t work(void){uint64_t value=0;__asm__ volatile(".rept 64\naddi %0,%0,1\n.endr":"+r"(value)::"memory");return value;}
static void measure(unsigned hart,unsigned region,uint64_t initial){
  __asm__ volatile("csrw mcycle,%0"::"r"(initial):"memory");
  uint64_t prior_retired=retired();measured[hart][region].begin=cycles();
  if(region==2)__asm__ volatile("csrs mcountinhibit,%0"::"r"(1UL):"memory");
  measured[hart][region].checksum=work();
  if(region==2)__asm__ volatile("csrc mcountinhibit,%0"::"r"(1UL):"memory");
  measured[hart][region].end=cycles();measured[hart][region].retired=retired()-prior_retired;
}
void benchmark_main(unsigned hart){
  barrier();
  measure(hart,0,1000000+hart*10000);
  measure(hart,1,UINT64_MAX-24);
  measure(hart,2,2000000+hart*10000);
  expect_illegal[hart]=1;
  __asm__ volatile(".global iris_counter_observe_illegal\niris_counter_observe_illegal:\ncsrw cycle,zero":::"memory");
  failed[hart]=expect_illegal[hart]!=0||illegal_seen[hart]!=1;
  for(unsigned region=0;region<3;++region)failed[hart]+=measured[hart][region].checksum!=64||!measured[hart][region].retired;
  barrier();if(hart)for(;;)__asm__ volatile("wfi");
  unsigned bad=0;
  for(unsigned h=0;h<3;++h){bad+=failed[h];for(unsigned region=0;region<3;++region){
    struct measurement *m=&measured[h][region];
    putstr("IRIS_REGION {\"case_id\":\"observe.counter\",\"region\":\"");putstr(region==0?"offset":region==1?"rollover":"inhibit");
    putstr("\",\"hart\":");putuint(h);putstr(",\"start_cycle\":");putuint(m->begin);putstr(",\"end_cycle\":");putuint(m->end);
    putstr(",\"instret_delta\":");putuint(m->retired);putstr(",\"checksum\":");putuint(m->checksum);putstr(",\"pass\":true}\n");
  }}
  putstr("COUNTER_OBSERVE_DONE ");putuint(bad);putstr("\n");finish(bad);
}
