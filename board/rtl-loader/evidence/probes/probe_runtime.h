#include "../../../benchmarks/runtime.h"
struct ProbeHart {uint64_t stage,actual,expected,cause,pc,tval,checks,done;};
struct ProbeMailbox {uint64_t magic,version,kind,failed;struct ProbeHart hart[3];};
extern volatile struct ProbeMailbox iris_rtl_probe_mailbox;
void probe_check(unsigned hart,unsigned stage,uint64_t actual,uint64_t expected);
