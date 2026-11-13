/* Executed-ELF feature/functional witness; never a calibration benchmark. */
#include "runtime.h"
typedef struct __attribute__((aligned(64))) {uint32_t word[16];} line_t;
static volatile line_t source[3],destination[3];
typedef struct __attribute__((aligned(64))) {uint64_t load_start,load_end,store_start,store_end,failed;} record_t;
static record_t records[3];
void benchmark_main(unsigned h){
 for(unsigned i=0;i<8;++i)source[h].word[i]=100+h+i;
 memory_fence();barrier();
 unsigned long vl;__asm__ volatile("vsetivli %0,8,e32,m1,ta,ma":"=r"(vl)::"memory");
 uint64_t a,b,c,d;
 __asm__ volatile("csrr %0,mcycle\nvle32.v v8,(%2)\nvle32.v v9,(%2)\ncsrr %1,mcycle":"=&r"(a),"=&r"(b):"r"(source[h].word):"memory");
 __asm__ volatile("vadd.vv v8,v8,v9":::"memory");
 __asm__ volatile("csrr %0,mcycle\nvse32.v v8,(%2)\nvse32.v v8,(%2)\ncsrr %1,mcycle":"=&r"(c),"=&r"(d):"r"(destination[h].word):"memory");
 memory_fence();unsigned failed=vl!=8;
 for(unsigned i=0;i<8;++i)failed+=destination[h].word[i]!=2*(100+h+i);
 records[h]=(record_t){a,b,c,d,failed};barrier();
 if(h==0){unsigned total=0;for(unsigned i=0;i<3;++i){record_t*r=&records[i];putstr("IRIS_VECTOR_BYPASS ");putuint(i);putstr(" ");putuint(r->load_start);putstr(" ");putuint(r->load_end);putstr(" ");putuint(r->store_start);putstr(" ");putuint(r->store_end);putstr(" ");putuint(r->failed);putstr("\n");total+=r->failed;}finish(total);}
 for(;;)__asm__ volatile("wfi");
}
