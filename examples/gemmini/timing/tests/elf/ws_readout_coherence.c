/* Public proposed readout witness; independent raw protocol, no compiler seed.
 * Same completed readout, same ACC data and output addresses, two CPU ownership
 * preparations. No CONFIG_NORM and no synthetic counter/fence instruction.
 * This is a NEW instrumented ELF: historical WS boundary labels do not apply.
 * Physical execution requires separate diagnostic admission. */
#define main ws_original_main
#define kernel_entry ws_original_kernel_entry
#define kernel_complete ws_original_kernel_complete
#include "ws_pipeline.c"
#undef main
#undef kernel_entry
#undef kernel_complete

static volatile u64 preparation_checksum;
struct arm_result {u64 cycles; unsigned errors;};
static struct arm_result results[2];

static void readout(void) {
 for(unsigned n=0;n<TILES;n++) {
  __asm__ volatile("fence":::"memory");
  COMMAND(3,output+n*256,tile(0xa0000000u+n*16));
  __asm__ volatile("fence":::"memory");
 }
}

__attribute__((noinline)) static void run_arm(unsigned dirty, struct arm_result *result) {
 /* Accelerator write invalidates prior CPU copies. CPU reads refill clean
  * lines; only the dirty arm then writes those same lines. Assumes selected
  * coherent cache protocol; retained timing report must verify actual probes. */
 readout();
 u64 checksum=0;
 for(unsigned i=0;i<TILES*256;i++)checksum+=(u64)output[i];
 preparation_checksum=checksum;
 if(dirty)for(unsigned i=0;i<TILES*256;i++)output[i]=0x6d6d6d6d;
 __asm__ volatile("fence":::"memory");
 u64 begin,end;
 __asm__ volatile(".globl ws_coherence_begin\nws_coherence_begin:\ncsrr %0,mcycle":"=r"(begin)::"memory");
 readout();
 __asm__ volatile(".globl ws_coherence_end\nws_coherence_end:\ncsrr %0,mcycle":"=r"(end)::"memory");
 result->cycles=end-begin;
 unsigned errors=0;
 for(unsigned n=0;n<TILES;n++)for(unsigned i=0;i<16;i++)for(unsigned j=0;j<16;j++) {
  i32 expected=0;
  for(unsigned k=0;k<16;k++)expected+=(i32)a[i*16+k]*(i32)b[k*16+j];
  if(output[n*256+i*16+j]!=expected)errors++;
 }
 result->errors=errors;
}

int main(void) {
 const u64 one=0x3f800000ul;
 for(unsigned i=0;i<256;i++){a[i]=(i8)((int)(i*3%7)-3);b[i]=(i8)((int)(i*5%9)-4);}
 COMMAND(0,6,(one<<32)|64);COMMAND(0,2,(one<<32)|64);
 COMMAND(0,1ul|(1ul<<8)|(16ul<<16)|(one<<32),16);
 COMMAND(2,a,tile(0));COMMAND(2,b,tile(4096));
 COMMAND(0,4ul|(1ul<<16)|(one<<32),1ul<<48);
 __asm__ volatile("fence":::"memory");
 for(unsigned n=0;n<TILES;n++) {
  COMMAND(6,tile(4096),tile(0x80000000u+n*16));
  COMMAND(4,tile(0),tile(0xffffffffu));
 }
 __asm__ volatile("fence":::"memory");
 run_arm(1,results);run_arm(0,results+1);
 for(unsigned arm=0;arm<2;arm++) {
  text("WS_COHERENCE dirty=");decimal(1-arm);text(" cycles=");decimal(results[arm].cycles);
  text(" checked=");decimal(TILES*256);text(" mismatches=");decimal(results[arm].errors);text("\n");
 }
 return results[0].errors||results[1].errors?1:0;
}
