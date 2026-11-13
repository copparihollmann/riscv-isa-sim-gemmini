#include <stdint.h>
#include "../benchmarks/runtime.h"
#include "native_guest_cases.h"
static uint8_t inputs[3][256] __attribute__((aligned(64)));
static uint8_t actual[2][256] __attribute__((aligned(64)));
static uint64_t signatures[2];
static unsigned epoch,done[2];
static uint32_t fp_a[8]={0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000};
static uint32_t fp_b[8]={0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000,0x40000000};
static uint32_t fp_c[8] __attribute__((aligned(64)));
static void native_op(unsigned code){switch(code){
#include "native_guest_switch.h"
}}
static unsigned setvl(unsigned vl,unsigned type){unsigned out;__asm__ volatile("vsetvl %0,%1,%2":"=r"(out):"r"(vl),"r"(type));return out;}
static uint64_t mix(uint64_t sum,unsigned byte){return (sum^byte)*1099511628211ULL;}
static void scalar_vector_job(unsigned h){
 for(unsigned i=0;i<8;i++)fp_c[i]=0x3f000000;
 unsigned vl=8;__asm__ volatile("vsetvli zero,%0,e32,m1,tu,mu\n vle32.v v8,(%1)\n vle32.v v16,(%2)\n vle32.v v24,(%3)\n vfmacc.vv v24,v16,v8\n vse32.v v24,(%3)"::"r"(vl),"r"(fp_a),"r"(fp_b),"r"(fp_c):"memory");
 uint64_t sum=0;for(unsigned i=0;i<8;i++){if(fp_c[i]!=0x40200000)fail(h,0,0,i);sum+=fp_c[i];}
 if(sum!=8ULL*0x40200000)fail(h,0,0,sum);
}
void benchmark_main(unsigned h){
 barrier();
 for(unsigned test=0;test<NATIVE_GUEST_COUNT;test++){
  const struct NativeGuest* g=&native_guests[test];
  if(h==2){
   for(unsigned i=0;i<256;i++){inputs[0][i]=g->a[i];inputs[1][i]=g->b[i];inputs[2][i]=g->c[i];}
   __atomic_store_n(&epoch,test+1,__ATOMIC_RELEASE);
   scalar_vector_job(h);
   while(__atomic_load_n(&done[0],__ATOMIC_ACQUIRE)!=test+1||__atomic_load_n(&done[1],__ATOMIC_ACQUIRE)!=test+1)scalar_vector_job(h);
   for(unsigned peer=0;peer<2;peer++){
    uint64_t expected=1469598103934665603ULL;
    for(unsigned lm=0;lm<5;lm++)for(unsigned mask=0;mask<2;mask++){
     unsigned vmax=lm?32<<(lm-1):16,vl=vmax-3;
     for(unsigned i=0;i<vmax;i++)expected=mix(expected,i<vl&&(!mask||((i&1)==peer))?g->out[i]:g->c[i]);
    }
    if(signatures[peer]!=expected)fail(h,0,0,test);
   }
  }else{
   while(__atomic_load_n(&epoch,__ATOMIC_ACQUIRE)!=test+1){}
   uint64_t signature=1469598103934665603ULL;
   for(unsigned lm=0;lm<5;lm++)for(unsigned mask=0;mask<2;mask++){
    unsigned vmax=lm?32<<(lm-1):16,vl=vmax-3,type=(g->fmt<<8)|(lm?lm-1:7);
    setvl(vmax,type);
    __asm__ volatile("vle8.v v8,(%0)\n vle8.v v16,(%1)\n vle8.v v24,(%2)"::"r"(inputs[0]),"r"(inputs[1]),"r"(inputs[2]):"memory");
    uint8_t bits[32];for(unsigned j=0;j<32;j++)bits[j]=mask?(h?0xaa:0x55):0xff;
    __asm__ volatile("vlm.v v0,(%0)"::"r"(bits):"memory");
    setvl(vl,type);
    unsigned rm=g->rm;uint64_t scalar=g->b[0];
    __asm__ volatile("csrw frm,%0\n csrw fflags,zero\n fmv.d.x f3,%1"::"r"(rm),"r"(scalar):"memory");
    if(mask){
      // Masked variants of the same 23 encodings are selected by raw opcode
      // vm clearing in a separate generated switch.
      switch(g->code){
#include "native_guest_masked_switch.h"
      }
    }else native_op(g->code);
    unsigned flags;__asm__ volatile("csrr %0,fflags":"=r"(flags));
    unsigned want_flags=0;for(unsigned i=0;i<vl;i++)if(!mask||((i&1)==h))want_flags|=g->flags[i];
    if(flags!=want_flags)fail(h,0,0,0x100000+test*32+flags);
    setvl(vmax,type);__asm__ volatile("vse8.v v24,(%0)"::"r"(actual[h]):"memory");
    for(unsigned i=0;i<vmax;i++){
     unsigned want=i<vl&&(!mask||((i&1)==h))?g->out[i]:g->c[i];
     if(actual[h][i]!=want)fail(h,0,0,test*256+i);
     signature=mix(signature,actual[h][i]);
    }
   }
   signatures[h]=signature;__atomic_store_n(&done[h],test+1,__ATOMIC_RELEASE);
  }
  barrier();
 }
 barrier();if(h==0){putstr("PASSED NATIVE_FP8 h0/h1 parallel arithmetic, h2 IEEE32 producer/consumer; 23 forms 2 formats 5 rm 5 LMUL masks/tails\n");finish(0);}
 for(;;)__asm__ volatile("wfi");
}
