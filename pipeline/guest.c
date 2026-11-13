#include "runtime.h"
struct metrics {uint64_t cycles,instret,first,second;};
extern void independent(struct metrics*);
extern void dependent(struct metrics*);
extern void unused_field(struct metrics*);
extern void waw_zero(struct metrics*);
static struct metrics values[3][4];
void benchmark_main(unsigned h){
  barrier();
  independent(&values[h][0]);
  dependent(&values[h][1]);
  unused_field(&values[h][2]);
  waw_zero(&values[h][3]);
  barrier();
  if(h)for(;;)__asm__ volatile("wfi");
  unsigned bad=0;
  for(unsigned hart=0;hart<3;++hart)for(unsigned kind=0;kind<4;++kind){
    struct metrics *r=&values[hart][kind];
    if(r->first!=(kind==1?512:kind==3?11:256)||r->second!=(kind==1?0:kind==2?0x90000:kind==3?16:768)||r->instret<512||!r->cycles)++bad;
    putstr("PIPELINE_CASE {\"hart\":");putuint(hart);putstr(",\"kind\":");putuint(kind);
    putstr(",\"cycles\":");putuint(r->cycles);putstr(",\"instret\":");putuint(r->instret);
    putstr(",\"first\":");putuint(r->first);putstr(",\"second\":");putuint(r->second);putstr("}\n");
  }
  putstr("PIPELINE_DONE ");putuint(bad);putstr("\n");finish(bad);
}
