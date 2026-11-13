#include "runtime.h"
#include "uart_drain.h"
#include "vme.h"
extern void wrongpath_kernel(void);
uint32_t idle_reaccept_words[4][32][32] __attribute__((aligned(64)));
volatile uint64_t idle_reaccept_done=UINT64_MAX;
__attribute__((noreturn,noinline))void abort(void){fail(hart_id(),251,0,0);}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 if(h==0){
  vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);
  VME_VTZERO(0);VME_VTZERO(1);VME_VTZERO(2);VME_VTZERO(3);
  __asm__ volatile("vmv.v.i v8,1\nvmv.v.i v16,1\nfence rw,rw":::"memory");
  wrongpath_kernel();
  __asm__ volatile(".rept 64\naddi zero,zero,0\n.endr":::"memory");
  VME_MM_U_U(3,8,16);memory_fence();
  vme_vsettnt_e32w1(32);
  for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r){VME_VTMV_V_T(24,vme_tss(t,VME_TSS_ROW,r));__asm__ volatile("vse32.v v24,(%0)\nfence rw,rw"::"r"(idle_reaccept_words[t][r]):"memory");}
  for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r)for(unsigned c=0;c<32;++c)if(idle_reaccept_words[t][r][c]!=(t==3))abort();
  memory_fence();idle_reaccept_done=0;memory_fence();putstr("IDLE_REACCEPT_PASS\n");iris_uart_drain();tohost=1;memory_fence();for(;;)__asm__ volatile("nop");
 }
 for(;;)__asm__ volatile("wfi");
}
