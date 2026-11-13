#include "runtime.h"
#ifndef IRIS_ACTIVE_HART
#define IRIS_ACTIVE_HART 0
#endif
#ifndef IRIS_BAD
#define IRIS_BAD 0
#endif
static uint64_t output[2][32] __attribute__((aligned(128)));
static uint64_t field(unsigned sew,unsigned index){if(sew==16)return((uint16_t*)output)[index];if(sew==32)return((uint32_t*)output)[index];return((uint64_t*)output)[index];}
#define F0 "vfadd.vv v8,v8,v16\n"
#define F1 "vfadd.vv v8,v8,v16\nvfadd.vv v24,v24,v16\n"
#define F2 "vfadd.vv v8,v8,v16\nvfadd.vv v24,v8,v16\n"
#if IRIS_BAD==8
static __attribute__((noinline)) void irq_loop(void){__asm__ volatile("li t0,256\n1:.rept 16\n"F0".endr\naddi t0,t0,-1\nbnez t0,1b":::"t0","memory");}
#endif
void benchmark_main(unsigned h){
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");set_timer(h,UINT64_MAX);*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;memory_fence();
 if(h!=IRIS_ACTIVE_HART)for(;;)__asm__ volatile("wfi");
 unsigned failed=0,cases=0,totalwords=0;
 for(unsigned kind=0;kind<3;++kind)for(unsigned mag=0;mag<4;++mag)for(unsigned mode=0;mode<3;++mode){
  unsigned sew=16u<<kind,lmul=1u<<mag,wanted=256/sew*lmul;unsigned long vl;
  uint64_t one=kind==0?0x3c00:kind==1?0x3f800000:0x3ff0000000000000ULL;
  unsigned long type=0xc0|((kind+1)<<3)|mag;
  __asm__ volatile("csrw frm,zero\ncsrw fflags,%4\nvsetvl %0,%1,%2\nvmv.v.x v8,%3\nvmv.v.x v16,%3\nvmv.v.x v24,%3"
     :"=&r"(vl):"r"(wanted),"r"(type),"r"(one),"r"(31UL):"memory");
#if IRIS_BAD
  if(kind||mag||mode)break;
  if(IRIS_BAD==1){__asm__ volatile("vmv.v.x v8,%0\nvmv.v.x v16,%1"::"r"(0x7c00UL),"r"(0xfc00UL):"memory");}
  if(IRIS_BAD==2){__asm__ volatile("vle16.v v8,(%0)"::"r"(0xa0000000UL):"memory");}
  if(IRIS_BAD==3){__asm__ volatile("vmclr.m v0\nvfadd.vv v8,v8,v16,v0.t":::"memory");}
  if(IRIS_BAD==4){__asm__ volatile("vsetivli zero,4,e16,m1,ta,ma":::"memory");}
  if(IRIS_BAD==5){__asm__ volatile("csrwi frm,3":::"memory");}
  if(IRIS_BAD==6){__asm__ volatile("csrc mstatus,%0\ncsrs mstatus,%1"::"r"(0x6000UL),"r"(0x4000UL):"memory");}
  if(IRIS_BAD==7){__asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");}
#if IRIS_BAD==8
  __asm__ volatile("vsetvli zero,%0,e32,m8,ta,ma\nvmv.v.x v8,%1\nvmv.v.x v16,%1"::"r"(64UL),"r"(0x3f800000UL):"memory");irq_loop();memory_fence();
  __asm__ volatile("vmv.v.x v8,%0\nvmv.v.x v16,%0"::"r"(0x3f800000UL):"memory");
  set_timer(h,*(volatile uint64_t*)(IRIS_CLINT+0xbff8)+2);__asm__ volatile("csrw mie,%0"::"r"(128UL):"memory");irq_loop();
#endif
#endif
  if(mode==0)__asm__ volatile(".rept 64\n"F0".endr":::"memory");
  else if(mode==1)__asm__ volatile(".rept 64\n"F1".endr":::"memory");
  else __asm__ volatile(".rept 64\n"F2".endr":::"memory");
  unsigned streams=mode?2:1;
  if(sew==16)__asm__ volatile("vse16.v v8,(%0)\nvse16.v v24,(%1)"::"r"(output),"r"((char*)output+32*lmul):"memory");
  if(sew==32)__asm__ volatile("vse32.v v8,(%0)\nvse32.v v24,(%1)"::"r"(output),"r"((char*)output+32*lmul):"memory");
  if(sew==64)__asm__ volatile("vse64.v v8,(%0)\nvse64.v v24,(%1)"::"r"(output),"r"((char*)output+32*lmul):"memory");
  memory_fence();unsigned long flags;__asm__ volatile("csrr %0,fflags":"=r"(flags));unsigned bad=vl!=wanted||flags!=31;
  const uint64_t sixtyfive=kind==0?0x5410:kind==1?0x42820000:0x4050400000000000ULL;
  const uint64_t sixtysix=kind==0?0x5420:kind==1?0x42840000:0x4050800000000000ULL;
  for(unsigned stream=0;stream<streams;++stream)for(unsigned i=0;i<wanted;++i)bad+=field(sew,stream*wanted+i)!=((stream&&mode==2)?sixtysix:sixtyfive);
  failed+=bad;++cases;totalwords+=streams*wanted;
  putstr("IRIS_FADD_EG ");putuint(h);putstr(" ");putuint(sew);putstr(" ");putuint(lmul);putstr(" ");putuint(mode);putstr(" ");putuint(streams*wanted);putstr(" ");putuint(bad);putstr("\n");
 }
 // First encounter is taken; the legacy BHT initially predicts fallthrough.
 unsigned long vl;__asm__ volatile("csrw frm,zero\ncsrw fflags,zero\nvsetivli %0,8,e32,m1,ta,ma\nvmv.v.x v8,%1\nvmv.v.x v16,%1\n.balign 4\nli t0,1\nbnez t0,1f\nvfadd.vv v8,v1,v1\n1:vfadd.vv v8,v8,v16\nvse32.v v8,(%2)":"=&r"(vl):"r"(0x3f800000UL),"r"(output):"t0","memory");memory_fence();for(unsigned i=0;i<8;++i)failed+=((uint32_t*)output)[i]!=0x40000000;
 putstr("IRIS_FADD_EG_DONE ");putuint(h);putstr(" ");putuint(cases);putstr(" ");putuint(totalwords+8);putstr(" ");putuint(failed);putstr("\n");finish(failed);
}
