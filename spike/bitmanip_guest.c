#include "runtime.h"
#include "encoding.h"

static uint64_t scalar(unsigned operation,uint64_t a,uint64_t b) {
  register uint64_t left __asm__("t0")=a,right __asm__("t1")=b,result __asm__("t2");
#define RUN(ENCODING) __asm__ volatile(".word %3" : "=r"(result) : "r"(left),"r"(right),"i"(ENCODING) : "memory")
  switch(operation) {
    case 0:RUN(MATCH_ANDN|(6<<20)|(5<<15)|(7<<7));break;
    case 1:RUN(MATCH_SH1ADD|(6<<20)|(5<<15)|(7<<7));break;
    case 2:RUN(MATCH_BSET|(6<<20)|(5<<15)|(7<<7));break;
    default:RUN(MATCH_CLZ|(5<<15)|(7<<7));break;
  }
  return result;
}
static uint64_t golden(unsigned operation,uint64_t a,uint64_t b) {
  if(operation==0)return a&~b;
  if(operation==1)return (a<<1)+b;
  if(operation==2)return a|(UINT64_C(1)<<(b&63));
  unsigned count=0;
  for(uint64_t mask=UINT64_C(1)<<63;mask && !(a&mask);mask>>=1)++count;
  return count;
}
void benchmark_main(unsigned h) {
  static const uint64_t left[]={0,UINT64_C(0x8000000000000001),UINT64_C(0x0123456789abcdef)};
  static const uint64_t right[]={0,63,UINT64_C(0xfedcba9876543210)};
  unsigned scalar_cases=0;
  for(unsigned operation=0;operation<4;++operation) {
    if(h==2) {
      uint64_t before=illegal_seen[h];expect_illegal[h]=1;
      (void)scalar(operation,left[operation%3],right[operation%3]);
      if(expect_illegal[h] || illegal_seen[h]!=before+1)fail(h,255,__LINE__,operation);
    } else for(unsigned row=0;row<3;++row) {
      uint64_t value=scalar(operation,left[row],right[row]);
      if(value!=golden(operation,left[row],right[row]))fail(h,255,__LINE__,operation*3+row);
      ++scalar_cases;
    }
  }
  uint64_t a[8],b[8];uint8_t output[64];
  for(unsigned i=0;i<8;++i) {a[i]=left[i%3]^(UINT64_C(0x0101010101010101)*i);b[i]=right[i%3];}
  for(unsigned sew=0;sew<4;++sew) {
    uint64_t vl;uint64_t avl=8;
#define VECTOR(EW) __asm__ volatile("vsetvli %0,%1,e" #EW ",m1,ta,ma\n\tvle" #EW ".v v8,(%2)\n\tvle" #EW ".v v16,(%3)\n\t.word %5\n\tvse" #EW ".v v24,(%4)" \
    :"=&r"(vl):"r"(avl),"r"(a),"r"(b),"r"(output),"i"(MATCH_VANDN_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7)):"memory")
    if(sew==0) {VECTOR(8);} else if(sew==1) {VECTOR(16);} else if(sew==2) {VECTOR(32);} else {VECTOR(64);}
    unsigned expected_vl=sew==3?4:8;
    if(vl!=expected_vl)fail(h,255,__LINE__,vl);
    for(unsigned byte=0;byte<vl*(1u<<sew);++byte)
      if(output[byte] != (((uint8_t *)a)[byte]&~((uint8_t *)b)[byte]))fail(h,255,__LINE__,byte);
  }
  barrier();
  for(unsigned row=0;row<IRIS_HARTS;++row) {
    if(row==h) {
      putstr("IRIS_BITMANIP {\"hart\":");putuint(h);putstr(",\"scalar_cases\":");putuint(scalar_cases);
      putstr(",\"illegal_cases\":");putuint(illegal_seen[h]);putstr(",\"vector_sew_cases\":4}\n");
    }
    barrier();
  }
  if(!h) {putstr("PASSED heterogeneous bitmanip\n");finish(0);}
}
