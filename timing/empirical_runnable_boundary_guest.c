/* One runnable hart with two parked peers must not lose its next CPU edge. */
#include "runtime.h"
void benchmark_main(unsigned h){
 barrier();if(h!=2)for(;;)__asm__ volatile("wfi");
 uint64_t sum=0;
 for(unsigned i=0;i<512;++i){uint64_t id;__asm__ volatile("csrr %0,mhartid":"=r"(id));sum+=id+i;}
 putstr("IRIS_RUNNABLE_BOUNDARY ");putuint(sum);putstr("\n");finish(sum!=131840);
}
