#include "packet.h"
#include "vme.h"
uint8_t inputs_a[2][256] __attribute__((aligned(128)));
uint8_t inputs_b[2][256] __attribute__((aligned(128)));
#define SET(S,M) case S*16+M:__asm__ volatile("vsetvli %0,%1,e"#S",m"#M",ta,ma":"=r"(vl):"r"(wanted):"memory");break
static unsigned rvv_config(const group_t*g){unsigned long vl=0,wanted=32*g->lmul*8/g->sew;switch(g->sew*16+g->lmul){SET(8,1);SET(8,2);SET(8,4);SET(8,8);SET(16,1);SET(16,2);SET(16,4);SET(16,8);SET(32,1);SET(32,2);SET(32,4);SET(32,8);}return vl;}
static unsigned setup(const group_t*g,unsigned h){
 __asm__ volatile("csrw vstart,zero\ncsrw vxrm,zero\ncsrw fcsr,zero":::"memory");
 if(!g->kind){unsigned vl=rvv_config(g);
  if(g->sew==8)__asm__ volatile("vle8.v v8,(%0)\nvle8.v v24,(%1)"::"r"(inputs_a[h]),"r"(inputs_b[h]):"memory");
  else if(g->sew==16)__asm__ volatile("vle16.v v8,(%0)\nvle16.v v24,(%1)"::"r"(inputs_a[h]),"r"(inputs_b[h]):"memory");
  else __asm__ volatile("vle32.v v8,(%0)\nvle32.v v24,(%1)"::"r"(inputs_a[h]),"r"(inputs_b[h]):"memory");
  __asm__ volatile("fence rw,rw":::"memory");return vl;
 }
 vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);VME_VTZERO(0);
 unsigned vl=(g->format==2||g->format==4)?vme_vsettnt_e8w4_alt(g->shape):vme_vsettnt_e8w4(g->shape);
 vme_vsettm(g->shape);vme_vsettk(1);
 __asm__ volatile("vle8.v v8,(%0)\nvle8.v v16,(%1)\nfence rw,rw"::"r"(inputs_a[h]),"r"(inputs_b[h]):"memory");return vl;
}
__attribute__((noinline)) unsigned compute_run(unsigned rid){
 const descriptor_t*d=&packet_descriptors[rid];const group_t*g=&packet_groups[d->group];unsigned h=d->hart;
 kernel_fn fn=!g->kind?packet_vadd:g->format==0?packet_mm_int:g->format<=2?packet_mm_e4:packet_mm_e5;
 unsigned blocks=(g->n-1)/16,vl=setup(g,h);fn(blocks); /* pre-execution, never measured */
 vl=setup(g,h); /* full VRF/tile reset follows warm call, including negative */
 packet_measure(&records[rid],fn,blocks);
 volatile uint8_t*out=output_data+d->offset+8;
 if(!g->kind){
  if(g->sew==8)__asm__ volatile("vse8.v v24,(%0)"::"r"(out):"memory");
  else if(g->sew==16)__asm__ volatile("vse16.v v24,(%0)"::"r"(out):"memory");
  else __asm__ volatile("vse32.v v24,(%0)"::"r"(out):"memory");
 }else{
  vme_vsettnt_e32w1(g->shape);vme_vsettm(g->shape);
  for(unsigned row=0;row<g->shape;++row){VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,row));__asm__ volatile("vse32.v v24,(%0)\nfence rw,rw"::"r"(out+row*g->shape*4):"memory");}
 }
 __asm__ volatile("fence rw,rw":::"memory");return vl;
}
