/* Synthetic scheduler-state guard; excluded from calibration and accuracy. */
#include "runtime.h"
#ifndef IRIS_IRQ_DELAY
#define IRIS_IRQ_DELAY 4
#endif
#ifndef IRIS_IRQ_PHASE
#define IRIS_IRQ_PHASE 0
#endif
#define IRIS_STRINGIFY_INNER(x) #x
#define IRIS_STRINGIFY(x) IRIS_STRINGIFY_INNER(x)
typedef struct __attribute__((aligned(64))){uint64_t before,observed,drained,irq,value;}record_t;
static record_t records[3];
void benchmark_main(unsigned h){
 unsigned long vl;__asm__ volatile("csrw vxrm,zero\nvsetivli %0,8,e32,m1,ta,ma\nvmv.v.i v8,3\nvmv.v.i v9,1":"=r"(vl)::"memory");
 barrier();set_timer(h,mtime()+IRIS_IRQ_DELAY);
 __asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(128ul),"r"(8ul):"memory");
 const uint64_t before=cycles();
 __asm__ volatile(".rept " IRIS_STRINGIFY(IRIS_IRQ_PHASE) "\nnop\n.endr\n.rept 4096\nvadd.vv v8,v8,v9\n.endr":::"memory");
 const uint64_t observed=cycles();__asm__ volatile("csrw vxrm,zero":::"memory");const uint64_t drained=cycles();
 while(!timer_seen[h])__asm__ volatile("nop");
 unsigned long value;__asm__ volatile("vmv.x.s %0,v8":"=r"(value)::"memory");
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8ul):"memory");
 records[h]=(record_t){before,observed,drained,timer_seen[h],value};barrier();
 if(h==0){unsigned failed=vl!=8;for(unsigned i=0;i<3;++i){const record_t*r=&records[i];failed+=r->irq!=1||r->value!=4099||r->drained<=r->observed;putstr("IRIS_SOURCE_TWO_IRQ ");putuint(i);putstr(" ");putuint(r->before);putstr(" ");putuint(r->observed);putstr(" ");putuint(r->drained);putstr(" ");putuint(r->irq);putstr(" ");putuint(r->value);putstr("\n");}finish(failed);}
 for(;;)__asm__ volatile("wfi");
}
