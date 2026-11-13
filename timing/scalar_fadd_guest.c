#include "runtime.h"
#ifndef SCALAR_FADD_TEST
#define SCALAR_FADD_TEST 0
#endif
static unsigned failed[3];
static uint64_t rows[3][3][4];
#define DEP(kind) for(unsigned i=0;i<32;++i)__asm__ volatile("fadd." #kind " ft0,ft0,ft1":::"ft0")
#define INDEP(kind) __asm__ volatile(".rept 16\nfadd." #kind " ft0,ft4,ft1\nfadd." #kind " ft2,ft4,ft1\nfadd." #kind " ft3,ft4,ft1\nfadd." #kind " ft5,ft4,ft1\n.endr":::"ft0","ft2","ft3","ft5")
void benchmark_main(unsigned h){
 for(unsigned w=0;w<3;++w){unsigned width=w==0?16:w==1?32:64;uint64_t one=width==16?0x3c00:width==32?0x3f800000:0x3ff0000000000000ULL;
  if(width==16)__asm__ volatile("fmv.h.x ft0,zero\nfmv.h.x ft4,zero\nfmv.h.x ft1,%0"::"r"(one):"ft0","ft1","ft4");
  if(width==32)__asm__ volatile("fmv.w.x ft0,zero\nfmv.w.x ft4,zero\nfmv.w.x ft1,%0"::"r"(one):"ft0","ft1","ft4");
  if(width==64)__asm__ volatile("fmv.d.x ft0,zero\nfmv.d.x ft4,zero\nfmv.d.x ft1,%0"::"r"(one):"ft0","ft1","ft4");
  __asm__ volatile("csrw fcsr,zero":::"memory");barrier();uint64_t begin=cycles(),ir=retired();
#if SCALAR_FADD_TEST == 1
  if(width==16){INDEP(h);}if(width==32){INDEP(s);}if(width==64){INDEP(d);}
#else
  if(width==16){DEP(h);}if(width==32){DEP(s);}if(width==64){DEP(d);}
#endif
  uint64_t end=cycles(),ret=retired(),bits;
  if(width==16){__asm__ volatile("fmv.x.h %0,ft0":"=r"(bits));bits&=0xffff;}
  if(width==32){__asm__ volatile("fmv.x.w %0,ft0":"=r"(bits));bits&=0xffffffff;}
  if(width==64)__asm__ volatile("fmv.x.d %0,ft0":"=r"(bits));
#if SCALAR_FADD_TEST == 1
  const uint64_t golden=one;
#else
  const uint64_t golden=width==16?0x5000:width==32?0x42000000:0x4040000000000000ULL;
#endif
  failed[h]+=bits!=golden;rows[h][w][0]=begin;rows[h][w][1]=end;rows[h][w][2]=ret-ir;rows[h][w][3]=bits;
  barrier();
 }
 if(h==0){unsigned n=0;for(unsigned t=0;t<3;++t){n+=failed[t];for(unsigned w=0;w<3;++w){putstr("SCALAR_FADD ");putuint(t);putstr(" ");putuint(w);for(unsigned k=0;k<4;++k){putstr(" ");putuint(rows[t][w][k]);}putstr("\n");}}finish(n);}
 for(;;)__asm__ volatile("wfi");
}
