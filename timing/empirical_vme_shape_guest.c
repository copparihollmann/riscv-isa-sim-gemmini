/* Source-geometry witness, excluded from timing fitting. */
#include "runtime.h"
#include "vme.h"
typedef struct{uint64_t begin,end,failed;}result_t;
static result_t records[3][5];static uint32_t row_data[3][32] __attribute__((aligned(64)));
static const unsigned shapes[5][2]={{16,16},{32,32},{17,3},{0,16},{3,0}};
void benchmark_main(unsigned h){
 __asm__ volatile("csrw mie,zero\ncsrw vstart,zero\ncsrw vxrm,zero\ncsrw frm,zero":::"memory");barrier();
 if(h<2){for(unsigned c=0;c<5;++c){
  vme_vsettnt_e8w4(32);vme_vsettm(32);vme_vsettk(1);VME_VTZERO(0);
  __asm__ volatile("vmv.v.i v8,1\nvmv.v.i v16,5":::"memory");VME_MM_U_U(0,8,16);memory_fence();
  vme_vsettnt_e8w4(shapes[c][1]);vme_vsettm(shapes[c][0]);
  const uint64_t begin=cycles();VME_VTZERO(0);memory_fence();const uint64_t end=cycles();uint64_t failed=0;
  vme_vsettnt_e32w1(32);
  for(unsigned r=0;r<32;++r){VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,r));memory_fence();__asm__ volatile("vse32.v v24,(%0)"::"r"(row_data[h]):"memory");
   for(unsigned n=0;n<32;++n){const uint32_t expected=(r<shapes[c][0]&&n<shapes[c][1])?0:5;failed+=row_data[h][n]!=expected;}}
  records[h][c]=(result_t){begin,end,failed};
 }}
 barrier();if(h==0){unsigned failed=0;for(unsigned i=0;i<2;++i)for(unsigned c=0;c<5;++c){const result_t*r=&records[i][c];failed+=r->failed;putstr("IRIS_VZERO_SHAPE ");putuint(i);putstr(" ");putuint(c);putstr(" ");putuint(shapes[c][0]);putstr(" ");putuint(shapes[c][1]);putstr(" ");putuint(r->begin);putstr(" ");putuint(r->end);putstr(" ");putuint(r->failed);putstr("\n");}finish(failed);}
 for(;;)__asm__ volatile("wfi");
}
