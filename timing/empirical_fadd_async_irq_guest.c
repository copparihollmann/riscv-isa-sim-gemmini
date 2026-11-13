/* Real CLINT interrupt during staged FADD, followed by shared scalar-FPU use. */
#include "runtime.h"
typedef struct __attribute__((aligned(64))) {uint64_t flags,value,irq,failed;} record_t;
static record_t result[3];
void benchmark_main(unsigned h) {
  unsigned long vl,flags,value;
  const unsigned long a=0x3f800000ul,b=0x40000000ul;
  __asm__ volatile("csrw frm,zero\ncsrw fflags,zero\nvsetivli %0,4,e32,m1,ta,ma\nvmv.v.x v8,%1\nvmv.v.x v16,%2\nfmv.w.x f2,%1\nfmv.w.x f3,%2"
      :"=&r"(vl):"r"(a),"r"(b):"f2","f3","memory");
  barrier();set_timer(h,mtime()+2);
  __asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(128ul),"r"(8ul):"memory");
  __asm__ volatile("vfadd.vv v24,v8,v16\nfadd.s f4,f2,f3\nfmv.x.w %0,f4\ncsrr %1,fflags":"=r"(value),"=r"(flags)::"f4","memory");
  while(!timer_seen[h])__asm__ volatile("nop");
  __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8ul):"memory");
  result[h]=(record_t){flags,value,timer_seen[h],vl!=4||flags!=0||value!=0x40400000ul||timer_seen[h]!=1};
  barrier();if(h==0){unsigned failed=0;for(unsigned i=0;i<3;++i){record_t*r=&result[i];failed+=r->failed;putstr("IRIS_FADD_IRQ ");putuint(i);putstr(" ");putuint(r->flags);putstr(" ");putuint(r->value);putstr(" ");putuint(r->irq);putstr(" ");putuint(r->failed);putstr("\n");}finish(failed);}
  for(;;)__asm__ volatile("wfi");
}
