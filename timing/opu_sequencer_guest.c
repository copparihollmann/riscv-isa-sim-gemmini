#include "probe_runtime.h"
#include "vme.h"
static uint32_t result[2][32] __attribute__((aligned(64)));
static volatile uint64_t producer[3] __attribute__((aligned(64)));
static void zeros(void){vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);VME_VTZERO(0);VME_VTZERO(1);VME_VTZERO(2);VME_VTZERO(3);}
static void readrow(unsigned h,unsigned tile,unsigned row,unsigned stage,uint32_t expected,unsigned active){
 vme_vsettnt_e32w1(32);size_t tss=vme_tss(tile,VME_TSS_ROW,row);VME_VTMV_V_T(24,tss);
 __asm__ volatile("vse32.v v24,(%0)\n fence rw,rw"::"r"(result[h]):"memory");
 for(unsigned c=0;c<32;c++)probe_check(h,stage,result[h][c],c<active?expected:0);
}
static void mm4(unsigned fp,unsigned fa){
 if(fp){if(fa){VME_MM_E5_E4(0,8,16);VME_MM_E5_E4(1,8,16);VME_MM_E5_E4(2,8,16);VME_MM_E5_E4(3,8,16);}else{VME_MM_E4_E4(0,8,16);VME_MM_E4_E4(1,8,16);VME_MM_E4_E4(2,8,16);VME_MM_E4_E4(3,8,16);}}
 else{VME_MM_U_U(0,8,16);VME_MM_U_U(1,8,16);VME_MM_U_U(2,8,16);VME_MM_U_U(3,8,16);}
}
void benchmark_main(unsigned h){
 __asm__ volatile("csrw fcsr,zero":::"memory");barrier();
 if(h<2){
  zeros();vme_vsettnt_e8w4(31);vme_vsettm(17);vme_vsettk(2);unsigned a=h+1,b=3;
  __asm__ volatile("vmv.v.x v8,%0\n vmv.v.x v10,%0\n vmv.v.x v16,%1\n vmv.v.x v18,%1"::"r"(a),"r"(b):"memory");mm4(0,0);
  for(unsigned tile=0;tile<4;tile++){readrow(h,tile,0,1,6*(h+1),31);readrow(h,tile,16,2,6*(h+1),31);readrow(h,tile,17,3,0,32);}
  for(unsigned fmt=0;fmt<4;fmt++){
   zeros();if(fmt&2)vme_vsettnt_e8w4_alt(31);else vme_vsettnt_e8w4(31);vme_vsettm(17);vme_vsettk(2);
   a=(fmt&1)?0x3c:0x38;b=(fmt&2)?0x3c:0x38;
   __asm__ volatile("vmv.v.x v8,%0\n vmv.v.x v10,%0\n vmv.v.x v16,%1\n vmv.v.x v18,%1"::"r"(a),"r"(b):"memory");mm4(1,fmt&1);
   for(unsigned tile=0;tile<4;tile++){readrow(h,tile,0,4+fmt,0x40000000,31);readrow(h,tile,16,8+fmt,0x40000000,31);}
  }
  // Both supported move-in patterns, followed by implemented row readout.
  zeros();vme_vsettnt_e32w1(32);vme_vsettm(32);unsigned fill=7+h;__asm__ volatile("vmv.v.x v24,%0"::"r"(fill):"memory");VME_VTMV_T_V(vme_tss(0,VME_TSS_ROW,19),24);
  readrow(h,0,19,12,fill,32);
  vme_vsettnt_e32w1(32);__asm__ volatile("vmv.v.x v24,%0"::"r"(fill):"memory");VME_VTMV_T_V(vme_tss(1,VME_TSS_COL,21),24);
  // Check column write through a row read: only c21 is nonzero.
  VME_VTMV_V_T(24,vme_tss(1,VME_TSS_ROW,18));__asm__ volatile("vse32.v v24,(%0)\n fence rw,rw"::"r"(result[h]):"memory");
  for(unsigned c=0;c<32;c++)probe_check(h,13,result[h][c],c==21?fill:0);
  VME_VTDISCARD();
 }else{
  uint64_t sum=0;for(unsigned i=0;i<128;i++){producer[i%3]=i+1;sum+=producer[i%3];}probe_check(h,14,sum,8256);
  // Hart2 has ordinary RVV; OPU itself must be refused by its real decoder.
  expect_illegal[h]=1;VME_VTZERO(0);probe_check(h,15,illegal_seen[h],1);
 }
 iris_rtl_probe_mailbox.hart[h].done=1;barrier();if(!h)finish(0);for(;;)__asm__ volatile("wfi");
}
