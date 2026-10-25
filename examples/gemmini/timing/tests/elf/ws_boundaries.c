/* Public instrumented protocol diagnostic. No reference compiler/kernel.
 * Six CSR reads per arm bracket submission, final compute drain and readout.
 * Counter values never affect control, command operands, or addresses. */
#define main ws_original_main
#define kernel_entry ws_original_kernel_entry
#define kernel_complete ws_original_kernel_complete
#include "ws_pipeline.c"
#undef main
#undef kernel_entry
#undef kernel_complete

struct arm_result {u64 submit, drain, readout; unsigned errors;};
static struct arm_result results[2];
#define STAMP(name, value) __asm__ volatile(".globl " #name "\n" #name ":\ncsrr %0,mcycle":"=r"(value)::"memory")
__attribute__((noinline)) static void run_arm(unsigned fenced, struct arm_result *result) {
 const u64 one=0x3f800000ul;
 for(unsigned i=0;i<TILES*256;i++)output[i]=0x6d6d6d6d;
 COMMAND(0,6,(one<<32)|64);COMMAND(0,2,(one<<32)|64);
 COMMAND(0,1ul|(1ul<<8)|(16ul<<16)|(one<<32),16);
 COMMAND(2,a,tile(0));COMMAND(2,b,tile(4096));
 COMMAND(0,4ul|(1ul<<16)|(one<<32),1ul<<48);
 __asm__ volatile("fence":::"memory");
 u64 s0,s1,d0,d1,r0,r1;
 STAMP(ws_submit_begin,s0);
 for(unsigned n=0;n<TILES;n++) {
  COMMAND(6,tile(4096),tile(0x80000000u+n*16));
  COMMAND(4,tile(0),tile(0xffffffffu));
  if(fenced)__asm__ volatile("fence":::"memory");
 }
 STAMP(ws_submit_end,s1);
 STAMP(ws_drain_begin,d0);
 __asm__ volatile("fence":::"memory");
 STAMP(ws_drain_end,d1);
 STAMP(ws_readout_begin,r0);
 for(unsigned n=0;n<TILES;n++) {
  __asm__ volatile("fence":::"memory");
  COMMAND(3,output+n*256,tile(0xa0000000u+n*16));
  __asm__ volatile("fence":::"memory");
 }
 __asm__ volatile("fence":::"memory");
 STAMP(ws_readout_end,r1);
 result->submit=s1-s0;result->drain=d1-d0;result->readout=r1-r0;
 unsigned errors=0;
 for(unsigned n=0;n<TILES;n++)for(unsigned i=0;i<16;i++)for(unsigned j=0;j<16;j++) {
  i32 expected=0;for(unsigned k=0;k<16;k++)expected+=(i32)a[i*16+k]*(i32)b[k*16+j];
  if(output[n*256+i*16+j]!=expected)errors++;
 }
 result->errors=errors;
}
int main(void) {
 for(unsigned i=0;i<256;i++){a[i]=(i8)((int)(i*3%7)-3);b[i]=(i8)((int)(i*5%9)-4);}
 run_arm(0,results);run_arm(1,results+1);
 /* All printing occurs after both completed and numerically checked arms. */
 for(unsigned arm=0;arm<2;arm++) {
  text("WS_BOUNDARY arm=");decimal(arm);text(" submit=");decimal(results[arm].submit);
  text(" drain=");decimal(results[arm].drain);text(" readout=");decimal(results[arm].readout);
  text(" checked=");decimal(TILES*256);text(" mismatches=");decimal(results[arm].errors);text("\n");
 }
 return results[0].errors||results[1].errors?1:0;
}
