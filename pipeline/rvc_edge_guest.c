#include "runtime.h"
extern void rvc_edge(uint64_t*);
extern unsigned char rvc_edge_resume[],rvc_reserved_pc[];
extern uint64_t base_trap_dispatch(uint64_t,uint64_t,uint64_t,unsigned);
static volatile uint64_t fetch_seen,fetch_pc,fetch_tval,reserved_seen,reserved_pc,reserved_tval;
static uint64_t output[2];
uint64_t trap_dispatch(uint64_t cause,uint64_t pc,uint64_t value,unsigned h){
  if(h==0&&cause==1){++fetch_seen;fetch_pc=pc;fetch_tval=value;return(uint64_t)rvc_edge_resume;}
  if(h==0&&cause==2){++reserved_seen;reserved_pc=pc;reserved_tval=value;return pc+2;}
  return base_trap_dispatch(cause,pc,value,h);
}
void benchmark_main(unsigned h){
  barrier();if(h)for(;;)__asm__ volatile("wfi");
  *(volatile uint16_t*)0x7003fffeUL=0x0e05; // C.ADDI t3,1.
  __asm__ volatile("fence.i":::"memory");
  rvc_edge(output);
  unsigned bad=fetch_seen!=1||fetch_pc!=0x70040000||fetch_tval!=fetch_pc||output[0]!=42||output[1]!=43||
      reserved_seen!=1||reserved_pc!=(uint64_t)rvc_reserved_pc||reserved_tval!=0x2001;
  putstr("PIPELINE_RVC_EDGE {\"fetch_pc\":");putuint(fetch_pc);putstr(",\"first\":");putuint(output[0]);
  putstr(",\"second\":");putuint(output[1]);putstr(",\"failed\":");putuint(bad);putstr("}\n");finish(bad);
}
