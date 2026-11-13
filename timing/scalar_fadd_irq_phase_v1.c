#include "runtime.h"
static uint64_t results[3][9][3];
static unsigned failed;
#define NOPS(N) __asm__ volatile(".rept " #N "\nnop\n.endr":::"memory")
static void shift(unsigned n){switch(n){case 0:break;case 1:NOPS(1);break;case 2:NOPS(2);break;case 3:NOPS(3);break;case 4:NOPS(4);break;case 5:NOPS(5);break;case 6:NOPS(6);break;case 7:NOPS(7);break;case 8:NOPS(8);break;}}
void benchmark_main(unsigned h){
 for(unsigned phase=0;phase<9;++phase){
  __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero\ncsrw fcsr,zero\nfmv.d.x ft0,zero\nfmv.d.x ft1,%1"::"r"(8UL),"r"(0x3ff0000000000000ULL):"ft0","ft1","memory");timer_seen[h]=0;barrier();set_timer(h,mtime()+2);
  __asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(128UL),"r"(8UL):"memory");shift(phase);
  for(unsigned i=0;i<1024;++i)__asm__ volatile("fadd.d ft0,ft0,ft1":::"ft0");
  uint64_t value;__asm__ volatile("fmv.x.d %0,ft0":"=r"(value));while(!timer_seen[h])__asm__ volatile("nop");__asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");results[h][phase][0]=timer_seen[h];results[h][phase][1]=value;results[h][phase][2]=phase;
  if(value!=0x4090000000000000ULL||timer_seen[h]!=1){__atomic_add_fetch(&failed,1,__ATOMIC_RELAXED);}
  barrier();
 }
 if(h==0){for(unsigned t=0;t<3;++t)for(unsigned p=0;p<9;++p){putstr("IRIS_SCALAR_FADD_IRQ_PHASE ");putuint(t);for(unsigned k=0;k<3;++k){putstr(" ");putuint(results[t][p][k]);}putstr("\n");}finish(failed?1:0);}for(;;)__asm__ volatile("wfi");
}
