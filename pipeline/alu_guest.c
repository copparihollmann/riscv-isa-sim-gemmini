#include "runtime.h"
extern void alu_corpus(uint64_t*);
static uint64_t outputs[3][14];
void benchmark_main(unsigned hart) {
  barrier();
  alu_corpus(outputs[hart]);
  barrier();
  if(hart)for(;;)__asm__ volatile("wfi");
  for(unsigned h=0;h<3;++h){
    putstr("PIPELINE_ALU {\"hart\":");putuint(h);putstr(",\"registers\":[");
    for(unsigned r=0;r<14;++r){if(r)putstr(",");putuint(outputs[h][r]);}
    putstr("]}\n");
  }
  finish(0);
}
