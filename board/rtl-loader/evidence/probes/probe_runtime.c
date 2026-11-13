#include "probe_runtime.h"
volatile uint64_t tohost __attribute__((section(".tohost"),aligned(64)));
volatile uint64_t fromhost __attribute__((section(".tohost"),aligned(64)));
volatile uint64_t ipi_seen[3],timer_seen[3],expect_illegal[3],illegal_seen[3];
volatile struct ProbeMailbox iris_rtl_probe_mailbox __attribute__((section(".data"),aligned(64)))={.magic=0x4952495350524f42ULL,.version=1,.kind=PROBE_KIND};
static unsigned arrivals,generation;
void putstr(const char* unused){(void)unused;}
void putuint(uint64_t unused){(void)unused;}
void finish(unsigned status){memory_fence();tohost=((uint64_t)status<<1)|1;memory_fence();for(;;)__asm__ volatile("wfi");}
void fail(unsigned hart,uint64_t cause,uint64_t pc,uint64_t value){iris_rtl_probe_mailbox.failed=1;iris_rtl_probe_mailbox.hart[hart].cause=cause;iris_rtl_probe_mailbox.hart[hart].pc=pc;iris_rtl_probe_mailbox.hart[hart].tval=value;finish(0x100+hart*0x40+iris_rtl_probe_mailbox.hart[hart].stage);}
void probe_check(unsigned hart,unsigned stage,uint64_t actual,uint64_t expected){volatile struct ProbeHart* row=&iris_rtl_probe_mailbox.hart[hart];row->stage=stage;row->actual=actual;row->expected=expected;if(actual!=expected)fail(hart,0,0,actual);row->checks++;}
uint64_t trap_dispatch(uint64_t cause,uint64_t pc,uint64_t value,unsigned hart){
 if(cause==((1ULL<<63)|3)){*(volatile uint32_t*)(IRIS_CLINT+4*hart)=0;memory_fence();ipi_seen[hart]++;return pc;}
 if(cause==2&&expect_illegal[hart]){expect_illegal[hart]=0;illegal_seen[hart]++;iris_rtl_probe_mailbox.hart[hart].cause=cause;iris_rtl_probe_mailbox.hart[hart].pc=pc;iris_rtl_probe_mailbox.hart[hart].tval=value;return pc+4;}
 fail(hart,cause,pc,value);
}
void barrier(void){unsigned before=__atomic_load_n(&generation,__ATOMIC_ACQUIRE);if(__atomic_add_fetch(&arrivals,1,__ATOMIC_ACQ_REL)==3){__atomic_store_n(&arrivals,0,__ATOMIC_RELAXED);__atomic_add_fetch(&generation,1,__ATOMIC_RELEASE);}else while(__atomic_load_n(&generation,__ATOMIC_ACQUIRE)==before){}}
