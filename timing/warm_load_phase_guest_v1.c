#include "runtime.h"
typedef struct __attribute__((aligned(64))){uintptr_t value;uint64_t pad[7];}slot_t;
static slot_t slots[3];
static uint64_t result[3][3];
extern uintptr_t warm_load_chain(uintptr_t);
__asm__(".text\n.option push\n.option norvc\n.balign 64\n.globl warm_load_chain\n.type warm_load_chain,@function\nwarm_load_chain:\n.rept 16\nld a0,0(a0)\n.endr\nret\n.size warm_load_chain,.-warm_load_chain\n.option pop\n");
void benchmark_main(unsigned h){uintptr_t address=(uintptr_t)&slots[h].value;slots[h].value=address;memory_fence();barrier();for(unsigned w=0;w<2;++w){if(warm_load_chain(address)!=address)fail(h,2,address,0);}memory_fence();barrier();uint64_t b=cycles();uintptr_t got=warm_load_chain(address);uint64_t e=cycles();result[h][0]=b;result[h][1]=e;result[h][2]=got;barrier();if(h==0){for(unsigned t=0;t<3;++t){if(result[t][2]!=(uintptr_t)&slots[t].value)fail(t,3,(uintptr_t)&slots[t].value,result[t][2]);putstr("WARM_LOAD_PHASE ");putuint(t);for(unsigned k=0;k<3;++k){putstr(" ");putuint(result[t][k]);}putstr("\n");}finish(0);}for(;;)__asm__ volatile("wfi");}
