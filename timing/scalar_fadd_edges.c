#include "runtime.h"
#ifndef SCALAR_EDGE_TEST
#define SCALAR_EDGE_TEST 0
#endif
#ifndef SCALAR_EDGE_HART
#define SCALAR_EDGE_HART 0
#endif
static unsigned errors[3];
static uint64_t values[3][3];
static void load(unsigned width,uint64_t a,uint64_t b,uint64_t c,uint64_t d){
 if(width==16)__asm__ volatile("fmv.h.x ft1,%0\nfmv.h.x ft2,%1\nfmv.h.x ft4,%2\nfmv.h.x ft5,%3"::"r"(a),"r"(b),"r"(c),"r"(d):"ft1","ft2","ft4","ft5");
 if(width==32)__asm__ volatile("fmv.w.x ft1,%0\nfmv.w.x ft2,%1\nfmv.w.x ft4,%2\nfmv.w.x ft5,%3"::"r"(a),"r"(b),"r"(c),"r"(d):"ft1","ft2","ft4","ft5");
 if(width==64)__asm__ volatile("fmv.d.x ft1,%0\nfmv.d.x ft2,%1\nfmv.d.x ft4,%2\nfmv.d.x ft5,%3"::"r"(a),"r"(b),"r"(c),"r"(d):"ft1","ft2","ft4","ft5");
}
static uint64_t bits(unsigned width,unsigned second){uint64_t v=0;
 if(width==16){if(second)__asm__ volatile("fmv.x.h %0,ft3":"=r"(v));else __asm__ volatile("fmv.x.h %0,ft0":"=r"(v));return v&65535;}
 if(width==32){if(second)__asm__ volatile("fmv.x.w %0,ft3":"=r"(v));else __asm__ volatile("fmv.x.w %0,ft0":"=r"(v));return v&0xffffffff;}
 if(second)__asm__ volatile("fmv.x.d %0,ft3":"=r"(v));else __asm__ volatile("fmv.x.d %0,ft0":"=r"(v));return v;}
void benchmark_main(unsigned h){
#if SCALAR_EDGE_TEST == 0
 for(unsigned w=0;w<3;++w){unsigned width=w==0?16:w==1?32:64;uint64_t one=w==0?0x3c00:w==1?0x3f800000:0x3ff0000000000000ULL,inf=w==0?0x7c00:w==1?0x7f800000:0x7ff0000000000000ULL,sign=w==0?0x8000:w==1?0x80000000:0x8000000000000000ULL,tiny=w==0?0xc00:w==1?0x33000000:0x3c90000000000000ULL,nan=w==0?0x7e00:w==1?0x7fc00000:0x7ff8000000000000ULL;
  load(width,inf,inf|sign,one,tiny);__asm__ volatile("csrw fcsr,zero":::"memory");barrier();
  if(width==16)__asm__ volatile("fadd.h ft0,ft1,ft2\nfadd.h ft3,ft4,ft5":::"ft0","ft3");
  if(width==32)__asm__ volatile("fadd.s ft0,ft1,ft2\nfadd.s ft3,ft4,ft5":::"ft0","ft3");
  if(width==64)__asm__ volatile("fadd.d ft0,ft1,ft2\nfadd.d ft3,ft4,ft5":::"ft0","ft3");
  uint64_t flags;__asm__ volatile("csrr %0,fflags":"=r"(flags));errors[h]+=flags!=17||bits(width,0)!=nan||bits(width,1)!=one;values[h][w]=flags;barrier();}
#elif SCALAR_EDGE_TEST == 1
 load(32,0x3f800000,0,0,0);barrier();if(h!=SCALAR_EDGE_HART)for(;;)__asm__ volatile("wfi");__asm__ volatile("fadd.s ft0,ft6,ft1":::"ft0");(void)bits(32,0);errors[h]=1;
#elif SCALAR_EDGE_TEST == 2
 load(64,0x3ff0000000000000ULL,0,0,0);__asm__ volatile("fmv.d.x ft0,zero":::"ft0");barrier();set_timer(h,mtime()+2);__asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(128UL),"r"(8UL):"memory");
 for(unsigned i=0;i<1024;++i)__asm__ volatile("fadd.d ft0,ft0,ft1":::"ft0");
 uint64_t got=bits(64,0);while(!timer_seen[h])__asm__ volatile("nop");__asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");errors[h]=got!=0x4090000000000000ULL||timer_seen[h]!=1;values[h][0]=timer_seen[h];values[h][1]=got;values[h][2]=cycles();
#elif SCALAR_EDGE_TEST == 3
 load(32,0x3f800000,0,0,0);__asm__ volatile("fmv.w.x ft0,zero":::"ft0");barrier();
 __asm__ volatile("li t0,0\nbeq t0,zero,1f\nfadd.s ft0,ft6,ft7\nfadd.s ft0,ft1,ft1\n1:":::"t0","ft0");errors[h]=bits(32,0)!=0;values[h][0]=bits(32,0);
#elif SCALAR_EDGE_TEST == 4
 for(unsigned w=0;w<3;++w){unsigned width=w==0?16:w==1?32:64;uint64_t one=w==0?0x3c00:w==1?0x3f800000:0x3ff0000000000000ULL,tie=w==0?0x1000:w==1?0x33800000:0x3ca0000000000000ULL;
  load(width,one,tie,0,0);for(unsigned rm=0;rm<5;++rm){__asm__ volatile("csrw fcsr,%0"::"r"((uint64_t)rm<<5):"memory");
   if(width==16){__asm__ volatile("fadd.h ft0,ft1,ft2":::"ft0");}
   if(width==32){__asm__ volatile("fadd.s ft0,ft1,ft2":::"ft0");}
   if(width==64){__asm__ volatile("fadd.d ft0,ft1,ft2":::"ft0");}
   uint64_t f;__asm__ volatile("csrr %0,fflags":"=r"(f));errors[h]+=bits(width,0)!=(one+(rm>=3))||f!=1;values[h][w]+=f;}}
#endif
 barrier();if(h==0){unsigned failed=0;for(unsigned i=0;i<3;++i){failed+=errors[i];putstr("SCALAR_EDGE ");putuint(i);putstr(" ");putuint(errors[i]);for(unsigned j=0;j<3;++j){putstr(" ");putuint(values[i][j]);}putstr("\n");}finish(failed);}for(;;)__asm__ volatile("wfi");
}
