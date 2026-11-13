#include "probe_runtime.h"
static uint8_t output[3][256] __attribute__((aligned(64)));
static unsigned setvl(unsigned n,unsigned type){unsigned got;__asm__ volatile("vsetvl %0,%1,%2":"=r"(got):"r"(n),"r"(type));return got;}
static void store(unsigned sew,void*p){
 if(sew==0)__asm__ volatile("vse8.v v16,(%0)"::"r"(p):"memory");
 if(sew==1)__asm__ volatile("vse16.v v16,(%0)"::"r"(p):"memory");
 if(sew==2)__asm__ volatile("vse32.v v16,(%0)"::"r"(p):"memory");
 if(sew==3)__asm__ volatile("vse64.v v16,(%0)"::"r"(p):"memory");
 __asm__ volatile("fence rw,rw":::"memory");
}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 // Explicit known initialization of every vector-register bit, including v0.
 probe_check(h,1,setvl(256,0xc3),256);
 __asm__ volatile("vmv.v.i v0,0\n vmv.v.i v8,0\n vmv.v.i v16,0\n vmv.v.i v24,0":::"memory");
 for(unsigned sew=0;sew<4;sew++)for(unsigned lmul=0;lmul<4;lmul++){
  unsigned stage=2+sew*4+lmul,vl=(32u<<lmul)>>sew;
  probe_check(h,stage,setvl(vl,0xc0|(sew<<3)|lmul),vl);
  unsigned a=2,b=3;
  __asm__ volatile("vmv.v.x v8,%0\n vmv.v.x v16,%1\n vadd.vv v24,v8,v16\n vadd.vv v8,v24,v16\n vadd.vv v16,v8,v24"::"r"(a),"r"(b):"memory");
  store(sew,output[h]);unsigned difference=0,bytes=vl<<sew;
  for(unsigned n=0;n<bytes;n++)difference|=output[h][n]^((n&((1u<<sew)-1))?0u:13u);
  probe_check(h,stage,difference,0);
 }
 iris_rtl_probe_mailbox.hart[h].done=1;barrier();if(!h)finish(0);for(;;)__asm__ volatile("wfi");
}
