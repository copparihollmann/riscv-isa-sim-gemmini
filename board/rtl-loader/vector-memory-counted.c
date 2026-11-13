#include "probe_runtime.h"
#ifndef LOOP_COUNT
#define LOOP_COUNT 16
#endif
#ifndef WORK_MASK
#define WORK_MASK 7
#endif
static unsigned setvl(unsigned vl,unsigned type){unsigned result;__asm__ volatile("vsetvl %0,%1,%2":"=r"(result):"r"(vl),"r"(type));return result;}
static uint8_t a[3][256] __attribute__((aligned(64))),b[3][256] __attribute__((aligned(64))),initial[3][256] __attribute__((aligned(64))),out[3][256] __attribute__((aligned(64))),mask[3][16] __attribute__((aligned(64)));
void benchmark_main(unsigned hart){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 if(WORK_MASK&(1u<<hart))for(unsigned iteration=0;iteration<LOOP_COUNT;++iteration){
  unsigned stage=iteration+1;uint64_t vt,vl,vs;
  probe_check(hart,stage,setvl(256,0xc3),256);
  __asm__ volatile("csrr %0,vtype\n csrr %1,vl\n csrr %2,vstart":"=r"(vt),"=r"(vl),"=r"(vs));
  probe_check(hart,stage,vt,0xc3);probe_check(hart,stage,vl,256);probe_check(hart,stage,vs,0);
  unsigned fill=0xa5;
  __asm__ volatile("vmv.v.i v8,0\n vse8.v v8,(%0)\n vse8.v v8,(%1)\n vmv.v.x v16,%3\n vse8.v v16,(%2)\n fence rw,rw"::"r"(a[hart]),"r"(b[hart]),"r"(initial[hart]),"r"(fill):"memory");
  __asm__ volatile("vle8.v v8,(%0)\n vle8.v v16,(%1)\n vle8.v v24,(%2)"::"r"(a[hart]),"r"(b[hart]),"r"(initial[hart]):"memory");
  setvl(128,0xc2);__asm__ volatile("vlm.v v0,(%0)"::"r"(mask[hart]):"memory");
  probe_check(hart,stage,setvl(1,0x1d8),1);
  __asm__ volatile("csrr %0,vtype\n csrr %1,vstart":"=r"(vt),"=r"(vs));
  probe_check(hart,stage,vt,0x1d8);probe_check(hart,stage,vs,0);
  // No floating-point arithmetic: isolate load/mask/store ordering and queues.
  setvl(256,0xc3);__asm__ volatile("vse8.v v24,(%0)\n fence rw,rw"::"r"(out[hart]):"memory");
  unsigned difference=0;for(unsigned i=0;i<256;++i)difference|=out[hart][i]^0xa5u;probe_check(hart,stage,difference,0);
 }
 iris_rtl_probe_mailbox.hart[hart].done=1;barrier();if(!hart)finish(0);for(;;)__asm__ volatile("wfi");
}
