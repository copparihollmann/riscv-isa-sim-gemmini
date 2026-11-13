#include "runtime.h"
#ifndef IRIS_ACTIVE_HART
#define IRIS_ACTIVE_HART 0
#endif
#ifndef IRIS_BAD
#define IRIS_BAD 0
#endif
static uint64_t output[64] __attribute__((aligned(128)));
static uint64_t field(unsigned sew,unsigned i){return sew==8?((uint8_t*)output)[i]:sew==16?((uint16_t*)output)[i]:sew==32?((uint32_t*)output)[i]:output[i];}
#define V0 "vadd.vv v8,v8,v16\n"
#define V1 V0 "vadd.vv v24,v24,v16\n"
#define V2 V0 "vadd.vv v24,v8,v16\n"
#define V3 "vadd.vv v8,v24,v16\n"
#if IRIS_BAD==7
static __attribute__((noinline)) void irq_loop(void){__asm__ volatile("li t0,256\n1:.rept 16\n"V0".endr\naddi t0,t0,-1\nbnez t0,1b":::"t0","memory");}
#endif
void benchmark_main(unsigned h){
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");set_timer(h,UINT64_MAX);*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;memory_fence();if(h!=IRIS_ACTIVE_HART)for(;;)__asm__ volatile("wfi");unsigned failed=0,cases=0,totalwords=0;
 for(unsigned kind=0;kind<4;++kind)for(unsigned mag=0;mag<4;++mag)for(unsigned mode=0;mode<4;++mode){
  unsigned sew=8u<<kind,lmul=1u<<mag,wanted=256/sew*lmul;unsigned long vl;unsigned long type=0xc0|(kind<<3)|mag;
  __asm__ volatile("csrw fflags,%3\ncsrw vxsat,%4\nvsetvl %0,%1,%2\nvmv.v.i v8,1\nvmv.v.i v16,1\nvmv.v.i v24,1":"=&r"(vl):"r"(wanted),"r"(type),"r"(31UL),"r"(1UL):"memory");
#if IRIS_BAD
  if(kind||mag||mode)break;
  if(IRIS_BAD==1)__asm__ volatile("vle8.v v8,(%0)"::"r"(0xa0000000UL):"memory");
  if(IRIS_BAD==2)__asm__ volatile("vmclr.m v0\nvadd.vv v8,v8,v16,v0.t":::"memory");
  if(IRIS_BAD==3)__asm__ volatile("vsetivli zero,4,e8,m1,ta,ma":::"memory");
  if(IRIS_BAD==4)__asm__ volatile("csrwi vstart,1":::"memory");
  if(IRIS_BAD==5)__asm__ volatile("csrc mstatus,%0\ncsrs mstatus,%1"::"r"(0x600UL),"r"(0x400UL):"memory");
  if(IRIS_BAD==6)__asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
#if IRIS_BAD==7
  __asm__ volatile("vsetvli zero,%0,e32,m8,ta,ma\nvmv.v.i v8,1\nvmv.v.i v16,1"::"r"(64UL):"memory");memory_fence();set_timer(h,*(volatile uint64_t*)(IRIS_CLINT+0xbff8)+2);__asm__ volatile("csrw mie,%0"::"r"(128UL):"memory");irq_loop();
#endif
#endif
  if(mode==0)__asm__ volatile(".rept 64\n"V0".endr":::"memory");else if(mode==1)__asm__ volatile(".rept 64\n"V1".endr":::"memory");else if(mode==2)__asm__ volatile(".rept 64\n"V2".endr":::"memory");else __asm__ volatile(".rept 64\n"V3".endr":::"memory");
  unsigned streams=(mode==1||mode==2)?2:1;
  if(sew==8)__asm__ volatile("vse8.v v8,(%0)\nvse8.v v24,(%1)"::"r"(output),"r"((char*)output+32*lmul):"memory");
  if(sew==16)__asm__ volatile("vse16.v v8,(%0)\nvse16.v v24,(%1)"::"r"(output),"r"((char*)output+32*lmul):"memory");
  if(sew==32)__asm__ volatile("vse32.v v8,(%0)\nvse32.v v24,(%1)"::"r"(output),"r"((char*)output+32*lmul):"memory");
  if(sew==64)__asm__ volatile("vse64.v v8,(%0)\nvse64.v v24,(%1)"::"r"(output),"r"((char*)output+32*lmul):"memory");
  memory_fence();unsigned long flags,sat;__asm__ volatile("csrr %0,fflags\ncsrr %1,vxsat":"=r"(flags),"=r"(sat));unsigned bad=vl!=wanted||flags!=31||sat!=1;
  for(unsigned stream=0;stream<streams;++stream)for(unsigned i=0;i<wanted;++i)bad+=field(sew,stream*wanted+i)!=(mode==3?2:(stream&&mode==2?66:65));failed+=bad;totalwords+=streams*wanted;++cases;
  putstr("IRIS_VADD_EG ");putuint(h);putstr(" ");putuint(sew);putstr(" ");putuint(lmul);putstr(" ");putuint(mode);putstr(" ");putuint(streams*wanted);putstr(" ");putuint(bad);putstr("\n");
 }
 unsigned long vl;__asm__ volatile("vsetivli %0,8,e32,m1,ta,ma\nvmv.v.i v8,1\nvmv.v.i v16,1\nvsetivli zero,4,e32,m1,ta,ma\n.balign 64\nli t0,1\nbnez t0,1f\nvadd.vv v8,v1,v1\n1:vsetivli zero,8,e32,m1,ta,ma\nvadd.vv v8,v8,v16\nvse32.v v8,(%1)":"=&r"(vl):"r"(output):"t0","memory");memory_fence();for(unsigned i=0;i<8;++i)failed+=((uint32_t*)output)[i]!=2;
 putstr("IRIS_VADD_EG_DONE ");putuint(h);putstr(" ");putuint(cases);putstr(" ");putuint(totalwords+8);putstr(" ");putuint(failed);putstr("\n");finish(failed);
}
