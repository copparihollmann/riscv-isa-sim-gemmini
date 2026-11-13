/* Unknown flag bits remain unknown after async FADD; raised bits become known. */
#include "runtime.h"
static uint64_t result[3];
void benchmark_main(unsigned h) {
  unsigned long vl,flag;
  const unsigned long raised=h==2?16ul:1ul;
  const unsigned long inf=0x7f800000ul,minus_inf=0xff800000ul;
  const unsigned long opaque=0xa0000000ul+h*128ul;
  __asm__ volatile("csrw frm,zero\nvsetivli %0,4,e32,m1,ta,ma\nvmv.v.x v8,%1\nvmv.v.x v16,%2\nld t0,0(%3)\ncsrw fflags,t0"
     :"=&r"(vl):"r"(inf),"r"(minus_inf),"r"(opaque):"t0","memory");
  barrier();
  __asm__ volatile("vfadd.vv v24,v8,v16\nvfadd.vv v24,v24,v24\ncsrr t1,fflags\nsd t1,64(%1)\nand %0,t1,%2"
     :"=r"(flag):"r"(opaque),"r"(raised):"t1","memory");
#ifdef IRIS_FADD_BAD_HART
  if(h==IRIS_FADD_BAD_HART)
    __asm__ volatile("csrr t1,fflags\naddi t2,t1,1":::"t1","t2","memory");
#endif
  result[h]=flag;
  barrier();
  if(h==0){unsigned failed=vl!=4;for(unsigned i=0;i<3;++i){failed+=result[i]!=(i==2?16ul:1ul);putstr("IRIS_FADD_OPAQUE ");putuint(i);putstr(" ");putuint(result[i]);putstr("\n");}finish(failed);}
  for(;;)__asm__ volatile("wfi");
}
