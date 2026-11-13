#include <stdint.h>
#include "../benchmarks/runtime.h"
#include "fpcomp_cases.hpp"
static unsigned completed[3];
static unsigned setvl(unsigned vl,unsigned type){unsigned result;__asm__ volatile("vsetvl %0,%1,%2":"=r"(result):"r"(vl),"r"(type));return result;}
static void operation(unsigned code,unsigned vm){
 if(vm){switch(code){
#include "fpcomp_unmasked_switch.h"
 }}else{switch(code){
#include "fpcomp_masked_switch.h"
 }}
}
void benchmark_main(unsigned h){
 barrier();
 for(unsigned test=0;test<sizeof(cmp_cases)/sizeof(cmp_cases[0]);++test){
  const struct CmpCase* c=&cmp_cases[test];if((h==2)!=(c->hart==2))continue;
  uint8_t b[256],out[256],initial[256];for(unsigned i=0;i<256;++i){b[i]=c->b[i];initial[i]=0xa5;}
  if(c->code>=20)for(unsigned i=0;i<c->width/8;++i)b[i]=c->seed>>(8*i);
  setvl(256,0xc3);
  __asm__ volatile("vle8.v v8,(%0)\n vle8.v v16,(%1)\n vle8.v v24,(%2)"::"r"(c->a),"r"(b),"r"(initial):"memory");
  setvl(128,0xc2);__asm__ volatile("vlm.v v0,(%0)"::"r"(c->mask):"memory");
  unsigned type=0xc0|((c->width==64?3:c->width==32?2:1)<<3)|(c->alt?0x100:0)|c->lmul;
  if(setvl(c->vl,type)!=c->vl)fail(h,0,0,0x600000+test);
  unsigned seed=8,rm=test%8;uint64_t scalar=c->scalar;
  __asm__ volatile("fmv.d.x f3,%0\n csrw frm,%1\n csrw fflags,%2"::"r"(scalar),"r"(rm),"r"(seed):"memory");
  uint64_t status;__asm__ volatile("csrr %0,mstatus":"=r"(status));status=(status&~0x6000ULL)|0x2000;
  __asm__ volatile("csrw mstatus,%0"::"r"(status):"memory");operation(c->code,c->vm);
  unsigned flags;__asm__ volatile("csrr %1,mstatus\n csrr %0,fflags":"=r"(flags),"=r"(status));
  unsigned vf=(c->code<18&&(c->code&1))||c->code==18||c->code==19;
  if(flags!=(unsigned)(c->flags|seed)||(status&0x6000)!=(h==2||c->vl||vf?0x6000:0x2000))fail(h,0,0,0x100000+test);
  setvl(256,0xc3);__asm__ volatile("vse8.v v24,(%0)"::"r"(out):"memory");
  for(unsigned i=0;i<256;++i)if(out[i]!=c->out[i])fail(h,0,0,0x200000+test*256+i);
  completed[h]++;
 }
 for(unsigned alt=0;alt<2;++alt)for(unsigned code=0;code<22;++code){
  setvl(1,0xc0|(alt<<8));expect_illegal[h]=1;operation(code,1);
  if(expect_illegal[h]||illegal_seen[h]!=(uint64_t)(alt*22+code+1))fail(h,0,0,0x710000+code);
 }
 barrier();if(!h){if(completed[0]!=4224||completed[1]!=4224||completed[2]!=4224)fail(h,0,0,0x700000);
  putstr("IRIS_FPCOMP {\"hart0_cases\":4224,\"hart1_cases\":4224,\"hart2_cases\":4224,\"illegal_cases\":132}\n");
  putstr("PASSED FPCOMP 8448 oracle cases 12672 all3-hart executions 22 forms H/S/D altfmt ignored all3 source flags signed-zero masks/tails FS\n");finish(0);
 }for(;;)__asm__ volatile("wfi");
}
