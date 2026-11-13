#include <stdint.h>
#include "../benchmarks/runtime.h"
#include "wide_fp8_cases.hpp"
#include "fp8_reduction_cases.hpp"
static unsigned ready,complete[2],flag_seed;
static uint32_t fa[8]={0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000},fb[8]={0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000},fc[8];
static unsigned setvl(unsigned vl,unsigned type){unsigned out;__asm__ volatile("vsetvl %0,%1,%2":"=r"(out):"r"(vl),"r"(type));return out;}
static void wide_op(unsigned code){switch(code){
#include "wide_guest_switch.h"
}}
static void cpu_job(unsigned h){unsigned vl=8;for(unsigned i=0;i<8;i++)fc[i]=0x3f000000;
 __asm__ volatile("vsetvli zero,%0,e32,m1,tu,mu\n vle32.v v8,(%1)\n vle32.v v16,(%2)\n vle32.v v24,(%3)\n vfmacc.vv v24,v16,v8\n vse32.v v24,(%3)"::"r"(vl),"r"(fa),"r"(fb),"r"(fc):"memory");
 for(unsigned i=0;i<8;i++)if(fc[i]!=0x40200000)fail(h,0,0,i);
}
void benchmark_main(unsigned h){
 barrier();
 if(h==2){cpu_job(h);flag_seed=4;__atomic_store_n(&ready,1,__ATOMIC_RELEASE);while(!__atomic_load_n(&complete[0],__ATOMIC_ACQUIRE)||!__atomic_load_n(&complete[1],__ATOMIC_ACQUIRE))cpu_job(h);}
 else{
  while(!__atomic_load_n(&ready,__ATOMIC_ACQUIRE)){}
  uint8_t a8[8],b8[8],mask[32];uint16_t a16[8],dest[8],out[8];
  for(unsigned test=h;test<sizeof(wide_cases)/sizeof(wide_cases[0]);test+=2){const struct WideCase* c=&wide_cases[test];
   for(unsigned i=0;i<8;i++){a8[i]=0;a16[i]=0;b8[i]=0;dest[i]=0xaaaa;}
   a8[c->lane]=c->a;a16[c->lane]=c->a;b8[c->lane]=c->b;dest[c->lane]=c->c;
   for(unsigned i=0;i<32;i++)mask[i]=0;
   mask[0]=1<<c->lane;
   setvl(4,(c->fmt<<8));
   if(c->code>=4&&c->code<=7)__asm__ volatile("vle16.v v8,(%0)"::"r"(a16):"memory");else __asm__ volatile("vle8.v v8,(%0)"::"r"(a8):"memory");
   __asm__ volatile("vle8.v v16,(%0)\n vle16.v v24,(%1)\n vlm.v v0,(%2)"::"r"(b8),"r"(dest),"r"(mask):"memory");
   unsigned rm=c->rm,seed=flag_seed;uint64_t scalar=c->b;__asm__ volatile("csrw frm,%0\n csrw fflags,%1\n fmv.d.x f3,%2"::"r"(rm),"r"(seed),"r"(scalar):"memory");
   wide_op(c->code);unsigned flags;__asm__ volatile("csrr %0,fflags\n vse16.v v24,(%1)":"=r"(flags):"r"(out):"memory");
   if(flags!=(unsigned)(c->flags|seed)||out[c->lane]!=c->out)fail(h,0,0,0x100000+test);
   for(unsigned i=0;i<4;i++)if(i!=c->lane&&out[i]!=0xaaaa)fail(h,0,0,0x200000+test);
  }
  for(unsigned test=h;test<sizeof(reduction_cases)/sizeof(reduction_cases[0]);test+=2){const struct ReductionCase* c=&reduction_cases[test];
   uint8_t old[32],result[32];for(unsigned i=0;i<32;i++)old[i]=0xa5;
   setvl(32,0);__asm__ volatile("vle8.v v24,(%0)"::"r"(old):"memory");
   unsigned width=c->wide?8:0;setvl(1,width);unsigned initial=c->seed;__asm__ volatile("vmv.s.x v16,%0"::"r"(initial):"memory");
   unsigned vmax=c->lmul==7?16:32<<c->lmul,type=(c->fmt<<8)|c->lmul;setvl(vmax,type);
   __asm__ volatile("vle8.v v8,(%0)\n vlm.v v0,(%1)"::"r"(c->data),"r"(c->mask):"memory");setvl(c->vl,type);
   unsigned rm=c->rm,seed=flag_seed;__asm__ volatile("csrw frm,%0\n csrw fflags,%1"::"r"(rm),"r"(seed):"memory");
   if(c->wide){if(c->ordered)__asm__ volatile("vfwredosum.vs v24,v8,v16,v0.t":::"memory");else __asm__ volatile("vfwredusum.vs v24,v8,v16,v0.t":::"memory");}
   else{if(c->ordered)__asm__ volatile("vfredosum.vs v24,v8,v16,v0.t":::"memory");else __asm__ volatile("vfredusum.vs v24,v8,v16,v0.t":::"memory");}
   unsigned flags;__asm__ volatile("csrr %0,fflags":"=r"(flags));setvl(32,0);__asm__ volatile("vse8.v v24,(%0)"::"r"(result):"memory");
   unsigned actual=result[0]|(c->wide?(unsigned)result[1]<<8:0);
   if(flags!=(unsigned)(c->flags|seed)||actual!=c->out)fail(h,0,0,0x300000+test);
   for(unsigned i=c->wide?2:1;i<32;i++)if(result[i]!=0xa5)fail(h,0,0,0x400000+test);
  }
  __atomic_store_n(&complete[h],1,__ATOMIC_RELEASE);
 }
 barrier();if(!h){putstr("PASSED WIDE_REDUCE_FP8 h0/h1 parallel 18 widening +4 reduction forms; h2 concurrent IEEE32 jobs\n");finish(0);}for(;;)__asm__ volatile("wfi");
}
