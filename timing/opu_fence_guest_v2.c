#include "runtime.h"
#include "uart_drain.h"
#include "vme.h"
#include "kernels.h"
volatile uint64_t opu_fence_done=UINT64_MAX,opu_fence_errors,opu_fence_cases;
uint32_t opu_fence_words[2][2][4][4][32][32] __attribute__((aligned(64)));
uint64_t opu_fence_counters[2][2][4] __attribute__((aligned(64)));
static void prepare(unsigned fp){
 size_t avl=256;
 __asm__ volatile("vsetvli zero,%0,e8,m8,ta,ma\nvmv.v.i v0,0\nvmv.v.i v8,0\nvmv.v.i v16,0\nvmv.v.i v24,0"::"r"(avl):"memory");
 vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);
 VME_VTZERO(0);VME_VTZERO(1);VME_VTZERO(2);VME_VTZERO(3);memory_fence();
 unsigned long av=fp?0x38:2,bv=fp?0x38:3;
 __asm__ volatile("vmv.v.x v8,%0\nvmv.v.x v16,%1"::"r"(av),"r"(bv):"memory");memory_fence();
}
static void read_all(uint32_t dst[4][32][32]){
 vme_vsettnt_e32w1(32);
 for(unsigned t=0;t<4;++t)for(unsigned row=0;row<32;++row){
  VME_VTMV_V_T(24,vme_tss(t,VME_TSS_ROW,row));
  __asm__ volatile("vse32.v v24,(%0)\nfence rw,rw"::"r"(dst[t][row]):"memory");
 }
}
__attribute__((noreturn,noinline))void abort(void){fail(hart_id(),251,0,opu_fence_errors);}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 for(unsigned owner=0;owner<2;++owner){
  if(h==owner)for(unsigned fp=0;fp<2;++fp)for(unsigned f=0;f<4;++f){
   prepare(fp);(void)kernels[fp][f]();prepare(fp);uint64_t before,after;__asm__ volatile("csrr %0,fflags":"=r"(before));
   opu_fence_counters[h][fp][f]=kernels[fp][f]();
   __asm__ volatile("csrr %0,fflags":"=r"(after));if(before!=after)++opu_fence_errors;
   read_all(opu_fence_words[h][fp][f]);
   for(unsigned t=0;t<4;++t)for(unsigned row=0;row<32;++row)for(unsigned col=0;col<32;++col)
    if(opu_fence_words[h][fp][f][t][row][col]!=(fp?0x41800000U:96U))++opu_fence_errors;
   ++opu_fence_cases;
  }
  barrier();
 }
 if(h==0){memory_fence();opu_fence_done=0;memory_fence();if(opu_fence_errors)abort();putstr("OPU_FENCE_PASS\n");iris_uart_drain();tohost=1;memory_fence();for(;;)__asm__ volatile("nop");}
 for(;;)__asm__ volatile("wfi");
}
