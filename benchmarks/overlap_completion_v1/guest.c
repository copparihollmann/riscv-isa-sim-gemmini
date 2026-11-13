#include "runtime.h"
#include "uart_drain.h"
#include "vme.h"
typedef void(*kernel_t)(void);
typedef struct{uint64_t hart,fp8,edge,count,rotate,trial;kernel_t kernel;}case_t;
#include "cases.inc"
typedef struct __attribute__((aligned(64))){
 uint64_t hart,fp8,edge,count,rotate,trial;
 uint64_t start,issue_end,fence_end,drain_end,instret,checksum,failed,expected;
}record_t;
record_t overlap_records[CASE_COUNT];
uint32_t overlap_words[CASE_COUNT][4][32] __attribute__((aligned(64)));
volatile uint64_t overlap_done=UINT64_MAX,overlap_failed,overlap_finished;
static uint8_t producer[128] __attribute__((aligned(64)));
__attribute__((noreturn,noinline))void abort(void){fail(hart_id(),251,0,overlap_failed);}
static void setup(const case_t*c){
 if(c->hart<2){
  vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);
  VME_VTZERO(0);VME_VTZERO(1);VME_VTZERO(2);VME_VTZERO(3);
  vme_vsettnt_e8w4(c->edge);vme_vsettm(c->edge);vme_vsettk(1);
  uint64_t one=c->fp8?0x38:1;
  __asm__ volatile("vmv.v.x v8,%0\n vmv.v.x v16,%0"::"r"(one):"memory");
 }else{
  size_t vl;__asm__ volatile("vsetvli %0,%1,e8,m4,ta,ma\nvmv.v.i v8,1\nvmv.v.i v16,1":"=&r"(vl):"r"(128UL):"memory");
  __asm__ volatile("vsetvli %0,%1,e8,m4,ta,ma":"=&r"(vl):"r"(c->edge):"memory");if(vl!=c->edge)abort();
 }
 memory_fence();
}
static uint32_t expected_word(const case_t*c,unsigned tile,unsigned col){
 if(c->hart==2)return c->count+1;
 if(col>=c->edge)return 0;
 const unsigned n=c->rotate?c->count/4:tile?0:c->count;
 // Counts16/64 and their quarters are exact powers of two in binary32.
 if(!c->fp8)return n;
 return n==64?0x42800000U:n==16?0x41800000U:n==4?0x40800000U:0;
}
static void drain(unsigned id,const case_t*c){
 if(c->hart<2){
  vme_vsettnt_e32w1(32);
  VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,0));__asm__ volatile("vse32.v v24,(%0)"::"r"(overlap_words[id][0]):"memory");
  VME_VTMV_V_T(24,vme_tss(1,VME_TSS_ROW,0));__asm__ volatile("vse32.v v24,(%0)"::"r"(overlap_words[id][1]):"memory");
  VME_VTMV_V_T(24,vme_tss(2,VME_TSS_ROW,0));__asm__ volatile("vse32.v v24,(%0)"::"r"(overlap_words[id][2]):"memory");
  VME_VTMV_V_T(24,vme_tss(3,VME_TSS_ROW,0));__asm__ volatile("vse32.v v24,(%0)"::"r"(overlap_words[id][3]):"memory");
 }else __asm__ volatile("vse8.v v8,(%0)"::"r"(producer):"memory");
 memory_fence();
}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");
 if(h==2){expect_illegal[2]=1;VME_VTDISCARD();if(expect_illegal[2]||illegal_seen[2]!=1)abort();}
 barrier();
 for(unsigned id=0;id<CASE_COUNT;++id){const case_t*c=&cases[id];
  if(h==c->hart){
   // Warm identical code/operand paths, then restore known numerical inputs.
   setup(c);c->kernel();drain(id,c);setup(c);
   uint64_t i0=retired(),start=cycles();c->kernel();uint64_t issue=cycles();
   memory_fence();uint64_t fenced=cycles();drain(id,c);uint64_t done=cycles(),i1=retired(),sum=0,errors=0;
   if(h<2){for(unsigned t=0;t<4;++t)for(unsigned col=0;col<32;++col){uint32_t v=overlap_words[id][t][col];sum+=v;errors+=v!=expected_word(c,t,col);}}
   else{for(unsigned j=0;j<c->edge;++j){sum+=producer[j];errors+=producer[j]!=c->count+1;((uint8_t*)overlap_words[id])[j]=producer[j];}}
   overlap_records[id]=(record_t){h,c->fp8,c->edge,c->count,c->rotate,c->trial,start,issue,fenced,done,i1-i0,sum,errors,0};
   if(errors)overlap_failed+=errors;memory_fence();overlap_finished=id+1;memory_fence();
  }
  // WFI quiets inactive harts without adding polling to the measured window.
  // A bounded software MSIP wake is sent only after completion/publication.
  if(h==c->hart){for(unsigned p=0;p<3;++p)if(p!=h)send_ipi(p);}
  else while(overlap_finished<=id)__asm__ volatile("wfi");
  barrier();
 }
 if(h==0){if(overlap_failed)abort();memory_fence();overlap_done=0;memory_fence();putstr("P");iris_uart_drain();memory_fence();tohost=1;memory_fence();for(;;)__asm__ volatile("nop");}
 for(;;)__asm__ volatile("wfi");
}
