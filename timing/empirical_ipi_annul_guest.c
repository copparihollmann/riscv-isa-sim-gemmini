/* Sweep genuine IPI arrival phases against a speculative polling branch. */
#include "runtime.h"
void benchmark_main(unsigned h){
 if(h==0)__asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(8ul),"r"(8ul):"memory");
 for(unsigned round=0;round<128;++round){
  barrier();
  if(h==0)while(ipi_seen[0]==round){}
  if(h==2){for(unsigned i=0;i<(round&15);++i)__asm__ volatile("nop");send_ipi(0);}
  barrier();
 }
 if(h==0){putstr("IRIS_IPI_ANNUL ");putuint(ipi_seen[0]);putstr("\n");finish(ipi_seen[0]!=128);}
 for(;;)__asm__ volatile("wfi");
}
