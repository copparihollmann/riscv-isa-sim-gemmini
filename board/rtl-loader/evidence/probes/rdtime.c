#include "probe_runtime.h"
void benchmark_main(unsigned hart){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 expect_illegal[hart]=1;__asm__ volatile(".word 0xc01022f3":::"t0","memory");
 probe_check(hart,1,expect_illegal[hart],0);probe_check(hart,2,illegal_seen[hart],1);
 probe_check(hart,3,iris_rtl_probe_mailbox.hart[hart].cause,2);probe_check(hart,4,iris_rtl_probe_mailbox.hart[hart].tval,0xc01022f3);
 uint64_t before=mtime(),after=mtime();probe_check(hart,5,after>=before,1);
 iris_rtl_probe_mailbox.hart[hart].done=1;barrier();if(!hart)finish(0);for(;;)__asm__ volatile("wfi");
}
