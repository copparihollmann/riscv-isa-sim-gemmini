#include "runtime.h"
extern uint64_t frontend_sfb32(uint64_t),frontend_sfb16(uint64_t);
extern uint64_t frontend_wrongpath(uint64_t),frontend_jalr_link(void),frontend_jalr_alias(void);
extern unsigned char frontend_jalr_link_pc[],frontend_jalr_alias_pc[];
static uint64_t results[3][7],failed[3];
static uint32_t code[3][16] __attribute__((aligned(64)));
static void patch(unsigned hart,unsigned phase) {
  for(unsigned i=0;i<16;++i)code[hart][i]=0x00000013;
  if(!phase) {
    code[hart][0]=0x00050067; /* jalr zero,0(a0): first target differs from sequential prediction */
    code[hart][1]=0x05800513; /* wrong initial predicted path:88 */
    code[hart][2]=0x04d00513;
    code[hart][4]=0x00d00513; /* actual target:13 */
    code[hart][5]=0x00008067;
  } else {
    code[hart][0]=0x01f00513; /* addi a0,zero,31 */
    code[hart][1]=0x00008067;
    code[hart][4]=0x06100513; /* stale BTB target:97; corrected by source F2 */
    code[hart][5]=0x00008067;
  }
  __asm__ volatile("fence rw,rw; fence.i":::"memory");
}
void benchmark_main(unsigned hart) {
  uint64_t *r=results[hart];
  barrier();
  for(unsigned n=0;n<8;++n) {
    r[0]+=frontend_sfb32(n&1);r[1]+=frontend_sfb16(n&1);
    r[2]+=frontend_wrongpath(0);
    r[3]=frontend_jalr_link();r[4]=frontend_jalr_alias();
  }
  patch(hart,0);
  uint64_t (*fn)(uint64_t)=(void*)code[hart];
  for(unsigned n=0;n<8;++n)r[5]+=fn((uintptr_t)&code[hart][4]);
  patch(hart,1);r[6]=fn(0);
  failed[hart]=r[0]!=52 || r[1]!=52 || r[2]!=296 || r[3]!=(uintptr_t)frontend_jalr_link_pc || r[4]!=(uintptr_t)frontend_jalr_alias_pc || r[5]!=104 || r[6]!=31;
  barrier();
  if(hart)for(;;)__asm__ volatile("wfi");
  unsigned bad=0;
  for(unsigned h=0;h<3;++h) {
    bad+=failed[h];
    putstr("FRONTEND_CASE {\"hart\":");putuint(h);putstr(",\"sfb32\":");putuint(results[h][0]);
    putstr(",\"sfb16\":");putuint(results[h][1]);putstr(",\"wrongpath\":");putuint(results[h][2]);
    putstr(",\"jalr_link\":");putuint(results[h][3]);putstr(",\"jalr_alias\":");putuint(results[h][4]);
    putstr(",\"branch_training\":");putuint(results[h][5]);putstr(",\"patched_non_cfi\":");putuint(results[h][6]);
    putstr(",\"failed\":");putuint(failed[h]);putstr("}\n");
  }
  putstr("FRONTEND_DONE ");putuint(bad);putstr("\n");finish(bad);
}
