#include "runtime.h"
#include "operator_case.h"
#include "kernel.c"
struct memref2 {void *allocated,*aligned;int64_t offset,sizes[2],strides[2];};
extern void _mlir_ciface_forward(void*,void*,void*);
static int8_t input_a[CASE_M*CASE_K] __attribute__((aligned(16)));
static int8_t input_b[CASE_K*CASE_N] __attribute__((aligned(16)));
static int32_t output[CASE_M*CASE_N] __attribute__((aligned(16)));
static unsigned char arena[IRIS_HARTS][CASE_ARENA_BYTES] __attribute__((aligned(16)));
struct allocation {void*p;size_t n;unsigned freed;};
static struct allocation allocations[IRIS_HARTS][32];
static size_t arena_used[IRIS_HARTS];
static unsigned allocation_count[IRIS_HARTS],error_count;
static uint64_t begin_cycles[IRIS_HARTS],end_cycles[IRIS_HARTS],instructions[IRIS_HARTS],producer_hash;
void *malloc(size_t bytes){unsigned h=hart_id();size_t n=(bytes+15)&~(size_t)15;if(!n)n=16;if(n<bytes||h>=IRIS_HARTS||arena_used[h]>CASE_ARENA_BYTES-n||n>CASE_ARENA_BYTES||allocation_count[h]>=32)finish(10);void*p=&arena[h][arena_used[h]];arena_used[h]+=n;allocations[h][allocation_count[h]++]=(struct allocation){p,n,0};return p;}
void free(void *p){if(!p)return;unsigned h=hart_id();for(unsigned i=0;i<allocation_count[h];++i)if(allocations[h][i].p==p&&!allocations[h][i].freed){allocations[h][i].freed=1;return;}finish(11);}
void *memcpy(void *d,const void*s,size_t n){unsigned char*a=d;const unsigned char*b=s;for(size_t i=0;i<n;++i)a[i]=b[i];return d;}
void *memset(void *d,int v,size_t n){unsigned char*a=d;for(size_t i=0;i<n;++i)a[i]=(unsigned char)v;return d;}
void abort(void){finish(12);}
static uint64_t hash_byte(uint64_t h,unsigned char b){return(h^b)*UINT64_C(1099511628211);}
void benchmark_main(unsigned h){
 if(h==2){uint64_t hash=UINT64_C(14695981039346656037);for(unsigned i=0;i<CASE_M;++i)for(unsigned q=0;q<CASE_K;++q){int8_t v=(int8_t)(i*17+q*11+3);input_a[i*CASE_K+q]=v;hash=hash_byte(hash,(unsigned char)v);}for(unsigned q=0;q<CASE_K;++q)for(unsigned j=0;j<CASE_N;++j){int8_t v=(int8_t)(q*13+j*7+5);input_b[q*CASE_N+j]=v;hash=hash_byte(hash,(unsigned char)v);}for(unsigned i=0;i<CASE_M*CASE_N;++i)((volatile uint32_t*)output)[i]=~case_golden[i];producer_hash=hash;}
 barrier();
 if(h<CASE_WORKERS){unsigned first=CASE_M*h/CASE_WORKERS;struct memref2 a={input_a+first*CASE_K,input_a+first*CASE_K,0,{CASE_LOCAL_M,CASE_K},{CASE_K,1}},b={input_b,input_b,0,{CASE_K,CASE_N},{CASE_N,1}},c={output+first*CASE_N,output+first*CASE_N,0,{CASE_LOCAL_M,CASE_N},{CASE_N,1}};uint64_t ir=retired();begin_cycles[h]=cycles();
#ifndef IRIS_WORKLOAD_SKIP_KERNEL
  _mlir_ciface_forward(&a,&b,&c);
#endif
  end_cycles[h]=cycles();instructions[h]=retired()-ir;
 }
 barrier();
 if(h==0){for(unsigned i=0;i<CASE_M*CASE_N;++i)error_count+=(uint32_t)output[i]!=case_golden[i];putstr("ACC_I32 ");putuint(CASE_M*CASE_N);for(unsigned i=0;i<CASE_M*CASE_N;++i){putstr(" ");putuint((uint32_t)output[i]);}putstr("\nOUT ");putuint(CASE_M*CASE_N);for(unsigned i=0;i<CASE_M*CASE_N;++i){int64_t q=((int64_t)output[i]+512)>>10;if(q>127)q=127;if(q< -128)q=-128;union{float f;uint32_t u;}v;v.f=(float)q;putstr(" ");putuint(v.u);}putstr("\nPRODUCER 2 ");putuint(producer_hash);putstr("\n");for(unsigned t=0;t<CASE_WORKERS;++t){putstr("REGION ");putuint(t);putstr(" ");putuint(begin_cycles[t]);putstr(" ");putuint(end_cycles[t]);putstr(" ");putuint(instructions[t]);putstr(" ");putuint(arena_used[t]);putstr("\n");}putstr("ERRORS ");putuint(error_count);putstr("\nDONE\n");finish(error_count?1:0);}
 for(;;)__asm__ volatile("wfi");
}
