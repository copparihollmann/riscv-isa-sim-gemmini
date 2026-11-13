/* Observer-only source-journal control; no timing-fitting data. */
#include "runtime.h"
typedef struct __attribute__((aligned(64))){uint64_t start,end,vl,failed,checksum;} record_t;
static record_t records[3];
static uint32_t values[3][64] __attribute__((aligned(256)));
__attribute__((noinline)) static void source_fadd_body(void){
 __asm__ volatile(".rept 32\nvfadd.vv v8,v8,v16\n.endr":::"memory");
}
__attribute__((noinline)) static void source_integer_body(void){
 __asm__ volatile(".rept 32\nvadd.vv v8,v8,v16\n.endr":::"memory");
}
void benchmark_main(unsigned h){
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8UL):"memory");
 set_timer(h,UINT64_MAX);*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;memory_fence();
 unsigned long vl;
 if(h<2)__asm__ volatile("csrw fcsr,zero\nvsetvli %0,%1,e32,m8,ta,ma\nvmv.v.i v8,0\nvmv.v.x v16,%2":"=&r"(vl):"r"(64UL),"r"(0x3f800000UL):"memory");
 else __asm__ volatile("vsetivli %0,8,e32,m1,ta,ma\nvmv.v.i v8,3\nvmv.v.i v16,1":"=r"(vl)::"memory");
 barrier();
 uint64_t start=cycles();
 if(h<2)source_fadd_body();else source_integer_body();
 memory_fence();uint64_t end=cycles();
 __asm__ volatile("vse32.v v8,(%0)"::"r"(values[h]):"memory");memory_fence();
 uint64_t failed=vl!=(h<2?64:8),sum=0;unsigned count=h<2?64:8;
 for(unsigned i=0;i<count;++i){uint32_t x=values[h][i];failed+=x!=(h<2?0x42000000u:35u);sum+=x;}
 records[h]=(record_t){start,end,vl,failed,sum};barrier();
 if(h==0){unsigned total=0;for(unsigned j=0;j<3;++j){record_t*r=&records[j];total+=r->failed;
  putstr("IRIS_REGION {\"case_id\":\"source-profile-smoke-h");putuint(j);putstr("\",\"hart\":");putuint(j);
  putstr(",\"start_cycle\":");putuint(r->start);putstr(",\"end_cycle\":");putuint(r->end);
  putstr(",\"vl\":");putuint(r->vl);putstr(",\"checksum\":");putuint(r->checksum);
  putstr(",\"failed\":");putuint(r->failed);putstr(",\"pass\":");putstr(r->failed?"false":"true");putstr("}\n");
 }putstr("IRIS_SOURCE_PROFILE_DONE ");putuint(total);putstr("\n");finish(total);}
 for(;;)__asm__ volatile("wfi");
}
