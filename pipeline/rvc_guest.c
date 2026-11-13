#include "runtime.h"
extern void rvc_corpus(uint64_t*);
static uint64_t outputs[3][17];
void benchmark_main(unsigned hart) {
  barrier();rvc_corpus(outputs[hart]);barrier();
  if(hart)for(;;)__asm__ volatile("wfi");
  for(unsigned h=0;h<3;++h){
    putstr("PIPELINE_RVC {\"hart\":");putuint(h);putstr(",\"registers\":[");
    for(unsigned r=0;r<17;++r){if(r)putstr(",");putuint(outputs[h][r]);}
    putstr("]}\n");
  }
  finish(0);
}
