#include <stdint.h>
#include "../benchmarks/runtime.h"
#include "shared_fma_cases.hpp"
static unsigned ready,done,workers[2];
static const uint32_t a_compute[8]={0x7f7fffff,0x7f7fffff,0x7f7fffff,0x7f7fffff,0x7f7fffff,0x7f7fffff,0x7f7fffff,0x7f7fffff};
static const uint32_t b_compute[8]={0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000};
static unsigned width(unsigned kind){return kind==3?64:kind==2?32:16;}
static unsigned type(unsigned kind,unsigned lmul){return 0xc0|((kind>=2?kind:1)<<3)|(kind==1?0x100:0)|lmul;}
static unsigned setvl(unsigned vl,unsigned t){unsigned result;__asm__ volatile("vsetvl %0,%1,%2":"=r"(result):"r"(vl),"r"(t));return result;}
static void pack(uint8_t* p,unsigned index,unsigned bits,uint64_t value){for(unsigned byte=0;byte<bits/8;byte++)p[index*bits/8+byte]=value>>(byte*8);}
static uint64_t unpack(uint8_t* p,unsigned index,unsigned bits){uint64_t value=0;for(unsigned byte=0;byte<bits/8;byte++)value|=(uint64_t)p[index*bits/8+byte]<<(byte*8);return value;}
static void load8(const uint8_t* p,unsigned bits){if(bits==16)__asm__ volatile("vle16.v v8,(%0)"::"r"(p):"memory");else if(bits==32)__asm__ volatile("vle32.v v8,(%0)"::"r"(p):"memory");else __asm__ volatile("vle64.v v8,(%0)"::"r"(p):"memory");}
static void load16(const uint8_t* p,unsigned bits){if(bits==16)__asm__ volatile("vle16.v v16,(%0)"::"r"(p):"memory");else if(bits==32)__asm__ volatile("vle32.v v16,(%0)"::"r"(p):"memory");else __asm__ volatile("vle64.v v16,(%0)"::"r"(p):"memory");}
static void load24(const uint8_t* p,unsigned bits){if(bits==16)__asm__ volatile("vle16.v v24,(%0)"::"r"(p):"memory");else if(bits==32)__asm__ volatile("vle32.v v24,(%0)"::"r"(p):"memory");else __asm__ volatile("vle64.v v24,(%0)"::"r"(p):"memory");}
static void store24(uint8_t* p,unsigned bits){if(bits==16)__asm__ volatile("vse16.v v24,(%0)"::"r"(p):"memory");else if(bits==32)__asm__ volatile("vse32.v v24,(%0)"::"r"(p):"memory");else __asm__ volatile("vse64.v v24,(%0)"::"r"(p):"memory");}
static void operation(unsigned code){switch(code){
#include "shared_guest_switch.h"
}}

static void compute_job(unsigned h){
 uint32_t output[8];unsigned vl=8,flags,zero=0;
 __asm__ volatile("vsetvli zero,%0,e32,m1,tu,mu\n vle32.v v8,(%1)\n vle32.v v16,(%2)\n csrw frm,%3\n csrw fflags,%3\n vfmul.vv v24,v8,v16\n vse32.v v24,(%4)"::"r"(vl),"r"(a_compute),"r"(b_compute),"r"(zero),"r"(output):"memory");
 __asm__ volatile("csrr %0,fflags":"=r"(flags));
 // Dedicated compute FP lanes expose NV only: overflow and NX are dropped.
 if(flags)fail(h,0,0,0x500000|flags);
 for(unsigned i=0;i<8;i++)if(output[i]!=0x7f800000)fail(h,0,0,0x510000+i);
}
void benchmark_main(unsigned h){
 barrier();
 if(h<2){
  __atomic_fetch_add(&ready,1,__ATOMIC_RELEASE);
  do{compute_job(h);workers[h]++;}while(!__atomic_load_n(&done,__ATOMIC_ACQUIRE));
 }else{
  while(__atomic_load_n(&ready,__ATOMIC_ACQUIRE)!=2){}
  uint8_t a[16],b[16],cbuf[32],result[32],mask[8],data[512];
  for(unsigned test=0;test<sizeof(shared_cases)/sizeof(shared_cases[0]);test++){
   const struct SharedCase* c=&shared_cases[test];
   unsigned wide=c->code>=23,wi=c->code>=27&&c->code<=30,out=wide?(c->kind==2?3:2):c->kind,at=wi?out:c->kind;
   for(unsigned i=0;i<16;i++)a[i]=b[i]=0;
   for(unsigned i=0;i<32;i++)cbuf[i]=0xa5;
   for(unsigned i=0;i<8;i++)mask[i]=0;
   mask[0]=c->active;pack(a,0,width(at),c->a);pack(b,0,width(c->kind),c->b);pack(cbuf,0,width(out),c->c);
   setvl(1,type(at,0));load8(a,width(at));setvl(1,type(c->kind,0));load16(b,width(c->kind));
   setvl(1,type(out,0));load24(cbuf,width(out));
   setvl(1,type(c->kind,c->lmul));__asm__ volatile("vlm.v v0,(%0)"::"r"(mask):"memory");
   setvl(c->vl,type(c->kind,c->lmul));unsigned rm=c->rm,seed=8;
   // Alternate correct boxing and raw low bits: source VF extraction ignores boxing.
   uint64_t scalar=c->b;if(width(c->kind)<64 && test%2)scalar|=~0ULL<<width(c->kind);
   __asm__ volatile("csrw frm,%0\n csrw fflags,%1\n fmv.d.x f3,%2"::"r"(rm),"r"(seed),"r"(scalar):"memory");
   operation(c->code);unsigned flags;__asm__ volatile("csrr %0,fflags":"=r"(flags));
   setvl(1,type(out,0));store24(result,width(out));
   if(flags!=(unsigned)(c->flags|seed)||unpack(result,0,width(out))!=c->out)fail(h,0,0,0x100000+test);
  }
  for(unsigned test=0;test<sizeof(shared_reductions)/sizeof(shared_reductions[0]);test++){
   const struct SharedReduction* c=&shared_reductions[test];unsigned out=c->wide?(c->kind==2?3:2):c->kind;
   for(unsigned i=0;i<32;i++)cbuf[i]=0xa5;
   setvl(32,0);__asm__ volatile("vle8.v v24,(%0)"::"r"(cbuf):"memory");
   pack(b,0,width(out),c->seed);setvl(1,type(out,0));load16(b,width(out));
   unsigned vmax=(256/width(c->kind))*(c->lmul==7?1:1<<c->lmul)/(c->lmul==7?2:1);
   for(unsigned i=0;i<vmax;i++)pack(data,i,width(c->kind),c->data[i]);
   setvl(vmax,type(c->kind,c->lmul));load8(data,width(c->kind));
   __asm__ volatile("vlm.v v0,(%0)"::"r"(c->mask):"memory");setvl(c->vl,type(c->kind,c->lmul));
   unsigned rm=c->rm,seed=8;__asm__ volatile("csrw frm,%0\n csrw fflags,%1"::"r"(rm),"r"(seed):"memory");
   if(c->wide){if(c->ordered)__asm__ volatile("vfwredosum.vs v24,v8,v16,v0.t":::"memory");else __asm__ volatile("vfwredusum.vs v24,v8,v16,v0.t":::"memory");}
   else{if(c->ordered)__asm__ volatile("vfredosum.vs v24,v8,v16,v0.t":::"memory");else __asm__ volatile("vfredusum.vs v24,v8,v16,v0.t":::"memory");}
   unsigned flags;__asm__ volatile("csrr %0,fflags":"=r"(flags));setvl(32,0);__asm__ volatile("vse8.v v24,(%0)"::"r"(result):"memory");
   if(flags!=(unsigned)(c->flags|seed)||unpack(result,0,width(out))!=c->out)fail(h,0,0,0x300000+test);
   for(unsigned i=width(out)/8;i<32;i++)if(result[i]!=0xa5)fail(h,0,0,0x400000+test);
  }
  __atomic_store_n(&done,1,__ATOMIC_RELEASE);
 }
 barrier();if(!h){
  if(!workers[0]||!workers[1])fail(h,0,0,0x520000);
  putstr("PASSED SHARED_FPU h2 21000 operations 1200 reductions 45 forms FP16/FP32/FP64; h0/h1 concurrent source flags\n");finish(0);
 }for(;;)__asm__ volatile("wfi");
}
