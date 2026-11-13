#include "probe_runtime.h"
static volatile uint64_t shared[3] __attribute__((aligned(64)));
static uint64_t value(unsigned hart,unsigned round,unsigned line){return 0x1234000000000000ULL+((uint64_t)hart<<32)+((uint64_t)round<<16)+line;}
static void ordered(void){__asm__ volatile("fence rw,rw":::"memory");}
void benchmark_main(unsigned hart){
  barrier();
  for(unsigned round=0;round<4;++round){
    //16 same-index lines force dirty release traffic from every real core.
    for(unsigned line=0;line<16;++line){
      volatile uint64_t* p=(volatile uint64_t*)(0x84200000ULL+0x10000ULL*hart+4096*line);
      *p=value(hart,round,line);ordered();probe_check(hart,round+1,*p,value(hart,round,line));ordered();
    }
    volatile uint64_t* tcm=(volatile uint64_t*)(0x70000000ULL+(hart&1)*0x20000ULL+0x4000+0x2000*hart+8*round);
    *tcm=value(hart,round,16);ordered();probe_check(hart,round+1,*tcm,value(hart,round,16));ordered();
    volatile uint64_t* scratch=(volatile uint64_t*)(0x580000000ULL+0x1000*hart+8*round);
    *scratch=value(hart,round,17);ordered();probe_check(hart,round+1,*scratch,value(hart,round,17));ordered();
    // All three owners write different words on one coherent cache line.
    // Barriers separate publication and consumption; expected values are
    // computed independently rather than read from another observed output.
    shared[hart]=value(hart,round,18);ordered();barrier();
    for(unsigned owner=0;owner<3;++owner)probe_check(hart,round+1,shared[owner],value(owner,round,18));
    barrier();
  }
  iris_rtl_probe_mailbox.hart[hart].done=1;barrier();
  if(!hart)finish(0);
  for(;;)__asm__ volatile("wfi");
}
