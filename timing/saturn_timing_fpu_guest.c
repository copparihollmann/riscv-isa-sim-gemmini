#include "probe_runtime.h"
static uint8_t output[3][256] __attribute__((aligned(64)));
static unsigned setvl(unsigned n,unsigned type){unsigned got;__asm__ volatile("vsetvl %0,%1,%2":"=r"(got):"r"(n),"r"(type));return got;}
static void store(unsigned sew,void*p){
 if(sew==1)__asm__ volatile("vse16.v v24,(%0)"::"r"(p):"memory");
 if(sew==2)__asm__ volatile("vse32.v v24,(%0)"::"r"(p):"memory");
 if(sew==3)__asm__ volatile("vse64.v v24,(%0)"::"r"(p):"memory");
 __asm__ volatile("fence rw,rw":::"memory");
}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();probe_check(h,1,setvl(256,0xc3),256);
 __asm__ volatile("vmv.v.i v0,0\n vmv.v.i v8,0\n vmv.v.i v16,0\n vmv.v.i v24,0":::"memory");
 for(unsigned sew=1;sew<4;sew++)for(unsigned shape=0;shape<3;shape++){
  unsigned lmul=shape?shape+1:0,stage=2+(sew-1)*3+shape,vl=(32u<<lmul)>>sew;
  probe_check(h,stage,setvl(vl,0xc0|(sew<<3)|lmul),vl);
  uint64_t one=sew==1?0x3c00ULL:sew==2?0x3f800000ULL:0x3ff0000000000000ULL;
  __asm__ volatile("vmv.v.x v8,%0\n vmv.v.x v16,%0\n vmv.v.x v24,%0\n vfmacc.vv v24,v8,v16"::"r"(one):"memory");
  // Real scalar FP work competes with hart2's shared vector FPU requests.
  uint64_t scalar_one=0x3ff0000000000000ULL,scalar_out;
  __asm__ volatile("fmv.d.x ft0,%0\n fmv.d.x ft1,%0"::"r"(scalar_one):"ft0","ft1");
  for(unsigned n=0;n<8;n++)__asm__ volatile("fadd.d ft0,ft0,ft1":::"ft0");
  __asm__ volatile("fmv.x.d %0,ft0":"=r"(scalar_out));probe_check(h,stage,scalar_out,0x4022000000000000ULL);
  store(sew,output[h]);unsigned difference=0,bytes=vl<<sew;uint64_t two=sew==1?0x4000ULL:sew==2?0x40000000ULL:0x4000000000000000ULL;
  for(unsigned n=0;n<bytes;n++)difference|=output[h][n]^((two>>(8*(n&((1u<<sew)-1))))&255u);
  probe_check(h,stage,difference,0);
 }
 iris_rtl_probe_mailbox.hart[h].done=1;barrier();if(!h)finish(0);for(;;)__asm__ volatile("wfi");
}
