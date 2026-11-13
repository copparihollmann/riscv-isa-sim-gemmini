/* True vector RAW chain with independently exact FP32 sums on all harts. */
#include "runtime.h"
static uint32_t words[3][8] __attribute__((aligned(64)));
static uint64_t failed[3];
void benchmark_main(unsigned h) {
  unsigned long vl;
  __asm__ volatile("csrw frm,zero\ncsrw fflags,zero\nvsetivli %0,8,e32,m1,ta,ma\nvmv.v.x v8,%1\nvmv.v.x v16,%1"
      :"=&r"(vl):"r"(0x3f800000ul):"memory");
  barrier();
  for(unsigned j=0;j<16;++j)__asm__ volatile("vfadd.vv v8,v8,v16":::"memory");
  __asm__ volatile("vse32.v v8,(%0)"::"r"(words[h]):"memory");
  memory_fence();failed[h]=vl!=8;for(unsigned j=0;j<8;++j)failed[h]+=words[h][j]!=0x41880000u;
  barrier();if(h==0){unsigned total=0;for(unsigned i=0;i<3;++i){total+=failed[i];putstr("IRIS_FADD_CHAIN ");putuint(i);putstr(" ");putuint(failed[i]);putstr("\n");}finish(total);}
  for(;;)__asm__ volatile("wfi");
}
