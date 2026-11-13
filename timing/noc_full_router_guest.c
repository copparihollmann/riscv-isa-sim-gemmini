#include "probe_runtime.h"
// Physical NoC endpoints: TCM0 is at node0, scratchpad at node1, L2 at node2.
// Hart2/node5 reaches node0 through node6, exercising peer-local return input1.
static inline void ordered(void){__asm__ volatile("fence rw,rw":::"memory");}
void benchmark_main(unsigned hart){
 barrier();
 if(hart==2){
  for(unsigned round=0;round<4;++round){
   volatile uint64_t* tcm=(volatile uint64_t*)(0x70001000ULL+8*round);
   volatile uint64_t* scratch=(volatile uint64_t*)(0x580001000ULL+8*round);
   uint64_t x=0x1234567800000000ULL+round*0x10203ULL;
   *tcm=x;ordered();probe_check(hart,round+1,*tcm,x);ordered();
   *scratch=x^0x00ff00ff00ff00ffULL;ordered();probe_check(hart,round+1,*scratch,x^0x00ff00ff00ff00ffULL);ordered();
   //16 addresses with the same L1 index force dirty replacement traffic on C.
   for(unsigned line=0;line<16;++line){
    volatile uint64_t* p=(volatile uint64_t*)(0x80800000ULL+4096*line);
    uint64_t value=0x8765432100000000ULL+(uint64_t)round*0x10000+line;
    *p=value;ordered();probe_check(hart,round+1,*p,value);ordered();
   }
  }
 }
 iris_rtl_probe_mailbox.hart[hart].done=1;barrier();if(!hart)finish(0);for(;;)__asm__ volatile("wfi");
}
