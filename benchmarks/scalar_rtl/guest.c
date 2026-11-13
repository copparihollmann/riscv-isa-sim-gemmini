#include "runtime.h"
typedef struct { uint64_t begin,end,ibegin,iend,checksum,operations,pad0,pad1; } Record;
typedef struct { uint64_t magic,version,failed,done[3],pad0,pad1; Record rows[3][2]; } Mailbox;
extern volatile Mailbox mailbox;
volatile uint64_t tohost __attribute__((section(".tohost"),aligned(64)));
volatile uint64_t fromhost __attribute__((section(".tohost"),aligned(64)));
static unsigned arrivals,generation;
extern void scalar_dep256(volatile Record *),scalar_ind256(volatile Record *);
void barrier(void) {
  unsigned old=__atomic_load_n(&generation,__ATOMIC_ACQUIRE);
  if(__atomic_add_fetch(&arrivals,1,__ATOMIC_ACQ_REL)==3) {
    __atomic_store_n(&arrivals,0,__ATOMIC_RELAXED);
    __atomic_add_fetch(&generation,1,__ATOMIC_RELEASE);
  } else while(__atomic_load_n(&generation,__ATOMIC_ACQUIRE)==old) {}
}
void finish(unsigned status) {
  memory_fence();tohost=((uint64_t)status<<1)|1;memory_fence();
  for(;;)__asm__ volatile("wfi");
}
void fail(unsigned hart,uint64_t cause,uint64_t pc,uint64_t value) {
  mailbox.rows[hart][0].pad0=cause;mailbox.rows[hart][0].pad1=pc;
  mailbox.rows[hart][1].pad0=value;
  __atomic_fetch_or(&mailbox.failed,1UL<<hart,__ATOMIC_SEQ_CST);finish(1);
}
uint64_t trap_dispatch(uint64_t cause,uint64_t pc,uint64_t value,unsigned hart) {
  if(cause==((1ULL<<63)|3)) {*(volatile uint32_t *)(IRIS_CLINT+4*hart)=0;memory_fence();return pc;}
  fail(hart,cause,pc,value);
}
void benchmark_main(unsigned hart) {
  Record warm;
  scalar_dep256(&warm);scalar_ind256(&warm);
  barrier();
  scalar_dep256(&mailbox.rows[hart][0]);
  barrier();
  scalar_ind256(&mailbox.rows[hart][1]);
  if(mailbox.rows[hart][0].checksum!=257 || mailbox.rows[hart][1].checksum!=292)
    __atomic_fetch_or(&mailbox.failed,1UL<<hart,__ATOMIC_SEQ_CST);
  __atomic_store_n(&mailbox.done[hart],1,__ATOMIC_RELEASE);
  if(hart==0) {
    while(!__atomic_load_n(&mailbox.done[1],__ATOMIC_ACQUIRE) || !__atomic_load_n(&mailbox.done[2],__ATOMIC_ACQUIRE)) {}
    finish(mailbox.failed?1:0);
  }
  for(;;)__asm__ volatile("wfi");
}
