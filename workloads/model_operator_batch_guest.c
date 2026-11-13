#include "runtime.h"
struct memref2 { void *allocated,*aligned; int64_t offset,sizes[2],strides[2]; };
typedef void (*entry_t)(void*,void*,void*);
typedef struct {const char *id;unsigned k,workers,kind,trial;entry_t entry;const uint32_t *golden;uint64_t checksums[3];} case_t;
#include "model_operator_batch_cases.h"
static int8_t input_a[2*MAX_K] __attribute__((aligned(64)));
static int8_t input_b[32*MAX_K] __attribute__((aligned(64)));
static int32_t output[64] __attribute__((aligned(64)));
static unsigned char arena[3][MAX_ARENA] __attribute__((aligned(64)));
static struct {void *p;unsigned freed;} allocations[3][32];
static size_t arena_used[3];static unsigned allocation_count[3];
static struct {uint64_t start,end,instret,checksum,failed;} measured[3];
void *malloc(size_t bytes){unsigned h=hart_id();size_t n=(bytes+15)&~(size_t)15;if(!n)n=16;if(h>=3||n<bytes||n>MAX_ARENA||arena_used[h]>MAX_ARENA-n||allocation_count[h]>=32)finish(10);void*p=&arena[h][arena_used[h]];arena_used[h]+=n;allocations[h][allocation_count[h]++]=(typeof(allocations[0][0])){p,0};return p;}
void free(void *p){if(!p)return;unsigned h=hart_id();for(unsigned i=0;i<allocation_count[h];++i)if(allocations[h][i].p==p&&!allocations[h][i].freed){allocations[h][i].freed=1;return;}finish(11);}
void *memcpy(void*d,const void*s,size_t n){unsigned char*a=d;const unsigned char*b=s;for(size_t i=0;i<n;++i)a[i]=b[i];return d;}
void *memset(void*d,int value,size_t n){unsigned char*a=d;for(size_t i=0;i<n;++i)a[i]=(unsigned char)value;return d;}
void abort(void){finish(12);}
static uint64_t hash_byte(uint64_t h,unsigned b){return(h^(b&255))*UINT64_C(1099511628211);}
static uint64_t word_hash(const uint32_t *p,unsigned n){uint64_t h=UINT64_C(14695981039346656037);for(unsigned i=0;i<n;++i)for(unsigned b=0;b<4;++b)h=hash_byte(h,p[i]>>(8*b));return h;}
static uint32_t w8a8(int32_t x){int64_t q=((int64_t)x+512)>>10;if(q>127)q=127;if(q< -128)q=-128;union{float f;uint32_t u;}v;v.f=(float)q;return v.u;}
static void execute(const case_t *c,unsigned h){
 measured[h].failed=0;
 if(h==2){uint64_t start=cycles(),ir=retired();
  for(unsigned i=0;i<2;++i)for(unsigned q=0;q<c->k;++q)input_a[i*c->k+q]=(int8_t)(17*i+11*q+3+19*c->trial);
  for(unsigned q=0;q<c->k;++q)for(unsigned j=0;j<32;++j)input_b[q*32+j]=(int8_t)(13*q+7*j+5+23*c->trial);
  for(unsigned i=0;i<64;++i)((volatile uint32_t*)output)[i]=c->golden[i]^UINT32_MAX;
  uint64_t hash=UINT64_C(14695981039346656037);for(unsigned i=0;i<2*c->k;++i)hash=hash_byte(hash,(unsigned char)input_a[i]);for(unsigned i=0;i<32*c->k;++i)hash=hash_byte(hash,(unsigned char)input_b[i]);
  for(unsigned i=0;i<64;++i){uint32_t v=((volatile uint32_t*)output)[i];measured[h].failed+=v!=(c->golden[i]^UINT32_MAX);for(unsigned b=0;b<4;++b)hash=hash_byte(hash,v>>(8*b));}
  measured[h].end=cycles();measured[h].instret=retired()-ir;measured[h].start=start;measured[h].checksum=hash;
 }
 barrier();
 if(h<c->workers){arena_used[h]=0;allocation_count[h]=0;unsigned local=2/c->workers,first=local*h;
  struct memref2 a={input_a+first*c->k,input_a+first*c->k,0,{local,c->k},{c->k,1}},b={input_b,input_b,0,{c->k,32},{32,1}},out={output+first*32,output+first*32,0,{local,32},{32,1}};
  uint64_t ir=retired();measured[h].start=cycles();
#ifndef IRIS_MODEL_BATCH_SKIP_KERNEL
  c->entry(&a,&b,&out);
  memory_fence();
#else
  (void)a;(void)b;(void)out;
#endif
  measured[h].end=cycles();measured[h].instret=retired()-ir;
  for(unsigned i=0;i<allocation_count[h];++i)measured[h].failed+=!allocations[h][i].freed;
  for(unsigned i=0;i<local*32;++i)measured[h].failed+=(uint32_t)output[first*32+i]!=c->golden[first*32+i];
  measured[h].checksum=word_hash((const uint32_t*)output+first*32,local*32);
 }
 barrier();
}
static void print_region(const case_t*c,unsigned h){
 putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);putstr("\",\"suite\":\"model_operator_validation\",\"region\":\"");putstr(h==2?"producer":"compiler_kernel");putstr("\",\"hart\":");putuint(h);putstr(",\"trial_id\":");putuint(c->trial);putstr(",\"start_cycle\":");putuint(measured[h].start);putstr(",\"end_cycle\":");putuint(measured[h].end);putstr(",\"instret_delta\":");putuint(measured[h].instret);putstr(",\"checksum\":");putuint(measured[h].checksum);putstr(",\"expected_checksum\":");putuint(c->checksums[h]);putstr(",\"failed_words\":");putuint(measured[h].failed);putstr(",\"pass\":");putstr(!measured[h].failed&&measured[h].checksum==c->checksums[h]?"true":"false");putstr("}\n");
}
void benchmark_main(unsigned h){unsigned failed=0;for(unsigned t=0;t<MODEL_BATCH_CASES;++t){const case_t*c=&cases[t];execute(c,h);if(h==0){for(unsigned q=0;q<c->workers;++q){print_region(c,q);failed+=measured[q].failed;}print_region(c,2);failed+=measured[2].failed;
 putstr("IRIS_WORDS {\"case_id\":\"");putstr(c->id);putstr("\",\"accumulator_u32\":[");for(unsigned i=0;i<64;++i){if(i)putstr(",");putuint((uint32_t)output[i]);}putstr("],\"W8A8_f32_words\":[");for(unsigned i=0;i<64;++i){if(i)putstr(",");putuint(w8a8(output[i]));}putstr("]}\n");}barrier();}
 if(h==0){putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"cases\":");putuint(MODEL_BATCH_CASES);putstr(",\"regions\":");putuint(MODEL_BATCH_REGIONS);putstr(",\"trials\":3}\n");finish(failed?1:0);}for(;;)__asm__ volatile("wfi");}
