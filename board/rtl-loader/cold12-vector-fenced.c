#include "probe_runtime.h"
static unsigned setvl(unsigned vl,unsigned type){unsigned result;__asm__ volatile("vsetvl %0,%1,%2":"=r"(result):"r"(vl),"r"(type));return result;}
static void pack(uint8_t* p,unsigned index,unsigned width,uint64_t value){for(unsigned i=0;i<width/8;++i)p[index*width/8+i]=value>>(8*i);}
static uint64_t unpack(const uint8_t* p,unsigned width){uint64_t value=0;for(unsigned i=0;i<width/8;++i)value|=(uint64_t)p[i]<<(8*i);return value;}
static void run(unsigned hart,unsigned stage,unsigned width,unsigned alt,unsigned op,uint64_t a0,uint64_t b0,uint64_t tail,unsigned masked,uint64_t expected,unsigned expected_flags){
 uint8_t a[256] __attribute__((aligned(64))),b[256] __attribute__((aligned(64))),initial[256] __attribute__((aligned(64))),out[256] __attribute__((aligned(64))),mask[16];
 // Functional-reference variant: initialize identical bytes with ordinary RVV
 // stores rather than768 serialized scalar stores per case. No timing claim.
 unsigned fill=op==3&&expected?0xa4:0xa5;
 setvl(256,0xc3);
 __asm__ volatile("vmv.v.i v8,0\n vse8.v v8,(%0)\n vse8.v v8,(%1)\n vmv.v.x v16,%3\n vse8.v v16,(%2)"::"r"(a),"r"(b),"r"(initial),"r"(fill):"memory");
 __asm__ volatile("fence rw,rw":::"memory");
 for(unsigned i=0;i<16;++i)mask[i]=0;
 pack(a,0,width,a0);pack(b,0,width,b0);if(tail)pack(a,(hart==2?256:128)/width-1,width,tail);
 setvl(256,0xc3);__asm__ volatile("vle8.v v8,(%0)\n vle8.v v16,(%1)\n vle8.v v24,(%2)"::"r"(a),"r"(b),"r"(initial):"memory");
 setvl(128,0xc2);__asm__ volatile("vlm.v v0,(%0)"::"r"(mask):"memory");
 unsigned type=0xc0|((width==64?3:width==32?2:1)<<3)|(alt<<8);probe_check(hart,stage,setvl(1,type),1);
 __asm__ volatile("csrw fflags,zero":::"memory");
 if(op==0)__asm__ volatile("vfmax.vv v24,v8,v16":::"memory");
 else if(op==1)__asm__ volatile("vfmin.vv v24,v8,v16":::"memory");
 else if(op==2){if(masked)__asm__ volatile("vfsgnj.vv v24,v8,v16,v0.t":::"memory");else __asm__ volatile("vfsgnj.vv v24,v8,v16":::"memory");}
 else if(op==3)__asm__ volatile("vmfeq.vv v24,v8,v16":::"memory");
 else __asm__ volatile("vfredmin.vs v24,v8,v16,v0.t":::"memory");
 // Force the VRF result through an ordered store before observing fflags.
 setvl(256,0xc3);__asm__ volatile("vse8.v v24,(%0)\n fence rw,rw"::"r"(out):"memory");
 unsigned flags;__asm__ volatile("csrr %0,fflags":"=r"(flags));probe_check(hart,stage,flags,expected_flags);
 probe_check(hart,stage,op==3?(out[0]&1):unpack(out,width),expected);
 if(masked&&op==2)for(unsigned i=0;i<256;++i)probe_check(hart,stage,out[i],0xa5);
}
void benchmark_main(unsigned hart){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 run(hart,12,64,1,2,0,0,0x7fc00000,1,0xa5a5a5a5a5a5a5a5ULL,16);
 iris_rtl_probe_mailbox.hart[hart].done=1;barrier();if(!hart)finish(0);for(;;)__asm__ volatile("wfi");
}
