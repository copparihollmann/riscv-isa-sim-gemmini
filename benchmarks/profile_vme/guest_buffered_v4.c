#include "runtime.h"
#include "uart_drain.h"
#include "vme.h"
enum {K_vme_int=9,K_vme_fp8=10,K_row_read=11,K_row_write=12,K_tile_zero=13};
typedef struct {const char *id;unsigned kind,n,mask,sew,lmul,mode,bytes,protocol,edge,tk,tiles;}case_t;
static const case_t cases[]={
 {"profile.source.VME.uint8",K_vme_int,4,7,8,1,0,0,0,32,1,1},
 {"profile.source.VME.E4M3",K_vme_fp8,4,7,8,1,0,0,0,32,1,1}};
static uint8_t matrix_a[3][32] __attribute__((aligned(64))),matrix_b[3][32] __attribute__((aligned(64)));
static uint64_t output[3][64] __attribute__((aligned(64)));
static uint32_t producer_data[8] __attribute__((aligned(64)));
typedef struct __attribute__((aligned(64))){uint64_t begin,end,instret,checksum;}result_t;
static result_t results[3];
static unsigned failed;
volatile uint64_t profile_measurements_done=UINT64_MAX;
result_t profile_rows[2][3];
uint32_t profile_words[2][3][32];
#define VSTORE(SEW,REG,PTR) __asm__ volatile("vse" #SEW ".v " #REG ",(%0)"::"r"(PTR):"memory")
/* SOURCE_MATRIX_HELPERS */
static __attribute__((noinline)) void matrix_kernel(unsigned h,const case_t*c){
 for(unsigned i=0;i<c->n;++i)matrix_mac(c);
 matrix_drain(h,c);
 memory_fence();
}
static __attribute__((noinline)) void producer_kernel(unsigned h,const case_t*c){
 for(unsigned i=0;i<c->n;++i)__asm__ volatile("vadd.vv v8,v8,v16":::"memory");
 VSTORE(32,v8,output[h]);memory_fence();
}
__attribute__((noreturn,noinline))void abort(void){fail(hart_id(),255,0,0);}
void benchmark_main(unsigned h){
 if(h==2){expect_illegal[2]=1;VME_VTDISCARD();if(expect_illegal[2]||illegal_seen[2]!=1)abort();}
 for(unsigned k=0;k<2;++k){const case_t*c=&cases[k];
  if(h<2)matrix_setup(h,c);else{
   for(unsigned i=0;i<8;++i)producer_data[i]=1;
   unsigned long vl;__asm__ volatile("vsetvli %0,%1,e32,m1,ta,ma\n\tvle32.v v8,(%2)\n\tvle32.v v16,(%2)":"=&r"(vl):"r"(8UL),"r"(producer_data):"memory");if(vl!=8)abort();
  }
  memory_fence();barrier();
  uint64_t begin=cycles(),instructions=retired();
  if(h<2)matrix_kernel(h,c);else producer_kernel(h,c);
  uint64_t count=retired()-instructions,end=cycles(),sum=0;
  const unsigned n=h<2?32:8;const uint32_t expected=h==2?5:k?0x40800000U:4;
  for(unsigned i=0;i<n;++i){uint32_t value=((uint32_t*)output[h])[i];if(value!=expected)__atomic_add_fetch(&failed,1,__ATOMIC_RELAXED);sum+=value;}
  results[h]=(result_t){begin,end,count,sum};
  profile_rows[k][h]=results[h];
  for(unsigned i=0;i<n;++i)profile_words[k][h][i]=((uint32_t*)output[h])[i];
  barrier();
 }
 if(h==0){if(failed)abort();memory_fence();profile_measurements_done=0;memory_fence();putstr("P");iris_uart_drain();memory_fence();tohost=1;memory_fence();for(;;)__asm__ volatile("nop");}
 for(;;)__asm__ volatile("wfi");
}
