/* Precise interrupt coverage using real guest MSIP transactions, never host injection. */
#include "runtime.h"
static uint64_t words[8] __attribute__((aligned(64)));
static volatile uint64_t ready,done;
extern uint64_t pending_ipi_load(uint64_t*,uint64_t);
__asm__(".text\n.option push\n.option norvc\n.balign 64\n.globl pending_ipi_load\n.type pending_ipi_load,@function\npending_ipi_load:\nslli t0,a1,3\nadd t0,t0,a0\nld a0,0(t0)\nret\n.size pending_ipi_load,.-pending_ipi_load\n.option pop\n");
void benchmark_main(unsigned h){
 if(h==0)for(unsigned i=0;i<8;++i)words[i]=40+i;
 memory_fence();barrier();uint64_t bad=0,got=0,count=0;
 if(h==0){ready=1;memory_fence();do{got=pending_ipi_load(words,3);bad+=got!=43;++count;}while(ipi_seen[0]<64);done=1;memory_fence();}
 if(h==2){while(!ready){}for(unsigned i=1;i<=64;++i){send_ipi(0);while(ipi_seen[0]<i){}}while(!done){}}
 barrier();if(h==0){putstr("PENDING_IPI ");putuint(bad);putstr(" ");putuint(got);putstr(" ");putuint(ipi_seen[0]);putstr(" ");putuint(count);putstr("\n");finish(bad||ipi_seen[0]!=64);}
 for(;;)__asm__ volatile("wfi");
}
