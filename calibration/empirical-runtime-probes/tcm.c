#include "runtime.h"
static volatile struct { uint64_t begin,end,instructions,sum; } rows[3];
static volatile unsigned failed;
void benchmark_main(unsigned h){
  barrier();
  if(h<2){
    volatile uint64_t*p=(volatile uint64_t*)(0x70000000ul+h*0x20000ul);
    memory_fence();uint64_t begin=cycles(),ib=retired();
    for(unsigned i=0;i<32;++i)p[i]=h+i;
    uint64_t sum=0;for(unsigned i=0;i<32;++i)sum+=p[i];
    memory_fence();uint64_t ie=retired(),end=cycles();
    rows[h].begin=begin;rows[h].end=end;rows[h].instructions=ie-ib;rows[h].sum=sum;
    if(sum!=496+32*h)__atomic_fetch_add(&failed,1,__ATOMIC_SEQ_CST);
  }
  barrier();
  if(h==0){
    for(unsigned i=0;i<2;++i){
      putstr("IRIS_REGION {\"case_id\":\"empirical.tcm.mechanics\",\"hart\":");putuint(i);
      putstr(",\"start_cycle\":");putuint(rows[i].begin);putstr(",\"end_cycle\":");putuint(rows[i].end);
      putstr(",\"instret_delta\":");putuint(rows[i].instructions);putstr(",\"checksum\":");putuint(rows[i].sum);
      putstr(",\"pass\":");putstr(rows[i].sum==496+32*i?"true":"false");putstr("}\n");
    }
    putstr("IRIS_TCM_DONE {\"failed\":");putuint(failed);putstr("}\n");finish(failed?1:0);
  }
  for(;;)__asm__ volatile("wfi");
}
