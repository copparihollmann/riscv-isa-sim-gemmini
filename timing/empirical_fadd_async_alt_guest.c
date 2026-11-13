/* Both actual compute FP8 formats and BF16, with all five source RMs. */
#include "runtime.h"
static uint16_t outputs[2][16] __attribute__((aligned(64)));
static uint64_t failures[3],producer;
void benchmark_main(unsigned h) {
  for(unsigned format=0;format<3;++format)for(unsigned rm=0;rm<5;++rm){
    barrier();
    if(h<2){
      const unsigned type=format==2?0x108u:format==1?0x100u:0u;
      const unsigned a=format==2?0x3f80u:format==1?0x3cu:0x38u;
      const unsigned b=format==2?0x4000u:0x40u;
      const unsigned want=format==2?0x4040u:format==1?0x42u:0x44u;
      unsigned long vl,flags;
      __asm__ volatile("vsetvl %0,%2,%3\nvmv.v.x v8,%4\nvmv.v.x v16,%5\ncsrw frm,%6\ncsrw fflags,%7\nvfadd.vv v24,v8,v16\ncsrr %1,fflags"
        :"=&r"(vl),"=r"(flags):"r"(4ul),"r"((unsigned long)type),"r"((unsigned long)a),"r"((unsigned long)b),"r"((unsigned long)rm),"r"(4ul):"memory");
      /* Separate operands below keep no compiler knowledge of vector values. */
      if(format==2)__asm__ volatile("vse16.v v24,(%0)"::"r"(outputs[h]):"memory");
      else __asm__ volatile("vse8.v v24,(%0)"::"r"(outputs[h]):"memory");
      memory_fence();failures[h]+=vl!=4||flags!=4;
      for(unsigned j=0;j<4;++j)failures[h]+=(format==2?outputs[h][j]:((uint8_t*)outputs[h])[j])!=want;
    }else producer+=format*5+rm+1;
    barrier();
  }
  if(h==0){unsigned failed=producer!=120;for(unsigned i=0;i<3;++i)failed+=failures[i];putstr("IRIS_FADD_ALT ");putuint(failed);putstr(" ");putuint(producer);putstr("\n");finish(failed!=0);}
  for(;;)__asm__ volatile("wfi");
}
