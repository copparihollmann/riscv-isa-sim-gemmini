#include "probe_runtime.h"
#include "hpm_switch.h"
void benchmark_main(unsigned hart){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 uint64_t ones=~0ULL,value;
 __asm__ volatile("csrw mcounteren,%1\n csrr %0,mcounteren":"=r"(value):"r"(ones));probe_check(hart,1,value,7);
 __asm__ volatile("csrw scounteren,%1\n csrr %0,scounteren":"=r"(value):"r"(ones));probe_check(hart,2,value,7);
 __asm__ volatile("csrw mcountinhibit,%1\n csrr %0,mcountinhibit":"=r"(value):"r"(ones));probe_check(hart,3,value,5);
 __asm__ volatile("csrw mcountinhibit,zero":::"memory");
 for(unsigned slot=0;slot<29;++slot){
  probe_check(hart,4,read_mhpm(slot),0);write_mhpm(slot,ones);probe_check(hart,5,read_mhpm(slot),0);
  write_event(slot,ones);probe_check(hart,6,read_event(slot),0);probe_check(hart,7,read_hpm(slot),0);
 }
 iris_rtl_probe_mailbox.hart[hart].done=1;barrier();if(!hart)finish(0);for(;;)__asm__ volatile("wfi");
}
