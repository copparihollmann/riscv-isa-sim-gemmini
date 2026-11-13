/* Directed timing mechanism test, excluded from fitting. Long integer backend
 * crosses a real modeled CLINT deadline; all three harts retain exact values. */
#include "runtime.h"
typedef struct __attribute__((aligned(64))) {uint64_t begin,observed,after,irq,value;} record_t;
static record_t records[3];
void benchmark_main(unsigned h){
 unsigned long vl;__asm__ volatile("csrw vxrm,zero\nvsetivli %0,8,e32,m1,ta,ma\nvmv.v.i v8,3\nvmv.v.i v9,1":"=r"(vl)::"memory");
 barrier();set_timer(h,mtime()+1);
 __asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(128ul),"r"(8ul):"memory");
 const uint64_t begin=cycles();
 __asm__ volatile(".rept 1024\nvadd.vv v8,v8,v9\n.endr":::"memory");
 const uint64_t observed=cycles();
 /* This observable vector-state write must drain the staged numeric owner. */
 __asm__ volatile("csrw vxrm,zero":::"memory");
 const uint64_t after=cycles();
 while(!timer_seen[h])__asm__ volatile("nop");
 unsigned long value;__asm__ volatile("vmv.x.s %0,v8":"=r"(value)::"memory");
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8ul):"memory");
 records[h]=(record_t){begin,observed,after,timer_seen[h],value};
 barrier();
 if(h==0){unsigned failed=0;for(unsigned i=0;i<3;++i){record_t*r=&records[i];failed+=r->irq!=1||r->value!=1027||r->after<=r->observed||vl!=8;putstr("IRIS_ASYNC_TWO_IRQ ");putuint(i);putstr(" ");putuint(r->begin);putstr(" ");putuint(r->observed);putstr(" ");putuint(r->after);putstr(" ");putuint(r->irq);putstr(" ");putuint(r->value);putstr("\n");}finish(failed);}
 for(;;)__asm__ volatile("wfi");
}
