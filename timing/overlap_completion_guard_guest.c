#include "runtime.h"
#include "uart_drain.h"
#include "vme.h"
#include "kernels.h"
volatile uint64_t opu_guard_done=UINT64_MAX,opu_guard_errors,opu_guard_cases;
uint32_t opu_guard_words[2][2][3][2][4][32][32] __attribute__((aligned(64)));
uint32_t opu_guard_wrong_words[2][4][32][32] __attribute__((aligned(64)));
static uint32_t row_buffer[3][32] __attribute__((aligned(64)));
static uint8_t a_bytes[3][32] __attribute__((aligned(64))),b_bytes[3][32] __attribute__((aligned(64)));
static uint32_t bits(unsigned n){if(!n)return 0;unsigned k=31-__builtin_clz(n);return((k+127)<<23)|((n-(1U<<k))<<(23-k));}
static void prepare(unsigned h,unsigned fp){
 vme_vsettnt_e32w1(32);vme_vsettm(32);vme_vsettk(1);
 for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r){
  for(unsigned c=0;c<32;++c){unsigned n=512+64*t+r+c;row_buffer[h][c]=fp?bits(n):0x70000000U+n;}
  __asm__ volatile("vle32.v v24,(%0)"::"r"(row_buffer[h]):"memory");
  VME_VTMV_T_V(vme_tss(t,VME_TSS_ROW,r),24);
 }
 vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);
 for(unsigned i=0;i<32;++i){a_bytes[h][i]=fp?(0x38+8*(i%4)):1+i%4;b_bytes[h][i]=fp?(0x38+8*(i%3)):1+i%3;}
 __asm__ volatile("vle8.v v8,(%0)\nfence rw,rw\nvle8.v v16,(%1)\nfence rw,rw"::"r"(a_bytes[h]),"r"(b_bytes[h]):"memory");
}
static void read_all(uint32_t dst[4][32][32]){
 vme_vsettnt_e32w1(32);
 for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r){VME_VTMV_V_T(24,vme_tss(t,VME_TSS_ROW,r));__asm__ volatile("vse32.v v24,(%0)\nfence rw,rw"::"r"(dst[t][r]):"memory");}
}
__attribute__((noreturn,noinline))void abort(void){fail(hart_id(),251,0,opu_guard_errors);}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 for(unsigned owner=0;owner<2;++owner){
  if(h==owner){
   for(unsigned fp=0;fp<2;++fp)for(unsigned shape=0;shape<3;++shape)for(unsigned pattern=0;pattern<2;++pattern){
    unsigned size=8U<<shape;prepare(h,fp);vme_vsettnt_e8w4(size);vme_vsettm(size);vme_vsettk(1);memory_fence();
    uint64_t before,after;__asm__ volatile("csrr %0,fflags":"=r"(before));
    kernels[fp][pattern]();memory_fence();__asm__ volatile("csrr %0,fflags":"=r"(after));
    if(before!=after)++opu_guard_errors;
    read_all(opu_guard_words[h][fp][shape][pattern]);
    for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r)for(unsigned c=0;c<32;++c){
     unsigned init=512+64*t+r+c,prod=fp?(1U<<(r%4))*(1U<<(c%3)):(1+r%4)*(1+c%3);
     unsigned val=init+((r<size&&c<size)?64*prod:0);uint32_t expected=fp?bits(val):0x70000000U+val;
     if(opu_guard_words[h][fp][shape][pattern][t][r][c]!=expected)++opu_guard_errors;
    }
    ++opu_guard_cases;
   }
   prepare(h,0);memory_fence();wrongpath_kernel();memory_fence();read_all(opu_guard_wrong_words[h]);
   for(unsigned t=0;t<4;++t)for(unsigned r=0;r<32;++r)for(unsigned c=0;c<32;++c)if(opu_guard_wrong_words[h][t][r][c]!=0x70000000U+512+64*t+r+c)++opu_guard_errors;
  }
  barrier();
 }
 if(h==0){memory_fence();opu_guard_done=0;memory_fence();if(opu_guard_errors)abort();putstr("OPU_GUARD_PASS\n");iris_uart_drain();tohost=1;memory_fence();for(;;)__asm__ volatile("nop");}
 for(;;)__asm__ volatile("wfi");
}
