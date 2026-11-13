#include "runtime.h"
#include "kernel.h"
#ifdef IRIS_COMBINED
extern void merlin_vme_gemm_i8_twin(int32_t *,const int8_t *,const int8_t *,const int32_t *,size_t,size_t,size_t);
#endif
typedef struct { const char *id;unsigned m,n,k,pattern,bias;const uint32_t *golden[3];uint64_t checksum[3]; } case_t;
#include "cases.inc"
static int8_t a[2][MAX_INPUT] __attribute__((aligned(64)));
static int8_t b[2][MAX_INPUT] __attribute__((aligned(64)));
static int32_t c[2][MAX_OUTPUT] __attribute__((aligned(64)));
static int32_t bias[2][MAX_N] __attribute__((aligned(64)));
static uint32_t producer[4] __attribute__((aligned(64)));
static struct {uint64_t start,end,instret,checksum,failed;} results[3] __attribute__((aligned(64)));

static int8_t a_value(unsigned p,unsigned h,unsigned pattern) {
  return pattern==0?127-(int)h:pattern==1?-128+(int)h:pattern==2?-128:(int)((p*17+h*13)%256)-128;
}
static int8_t b_value(unsigned p,unsigned h,unsigned pattern) {
  return pattern==2?-128:pattern<2?127:(int)((p*31+h*7)%256)-128;
}
static int32_t bias_value(unsigned j,unsigned h,unsigned mode) {
  unsigned positive=mode==1 || (mode==3 && !(j&1));
  return !mode?0:positive?INT32_MAX-(int)(j%19)-(int)(h*3):INT32_MIN+(int)(j%19)+(int)(h*3);
}
static uint64_t checksum(const uint32_t *words,unsigned count) {
  uint64_t result=14695981039346656037ULL;
  for(unsigned p=0;p<count;++p)for(unsigned byte=0;byte<4;++byte)
    result=(result^((words[p]>>(8*byte))&255))*1099511628211ULL;
  return result;
}
static void execute(unsigned h,unsigned number,const case_t *test,unsigned variant) {
  if(h<2) {
    for(unsigned p=0;p<test->m*test->k;++p)a[h][p]=a_value(p,h,test->pattern);
    for(unsigned p=0;p<test->n*test->k;++p)b[h][p]=b_value(p,h,test->pattern);
    for(unsigned j=0;j<test->n;++j)bias[h][j]=bias_value(j,h,test->bias);
    // Every invocation must write every result afresh. The corresponding
    // unsigned type may alias int32_t, and avoids an out-of-range signed cast.
    for(unsigned p=0;p<test->m*test->n;++p)
      ((volatile uint32_t *)c[h])[p]=test->golden[h][p]^UINT32_MAX;
  }
  else for(unsigned p=0;p<4;++p)((volatile uint32_t *)producer)[p]=test->golden[h][p]^UINT32_MAX;
  barrier();
  uint64_t start=cycles(),instret=retired();
  if(h<2) {
#ifdef IRIS_TEST_SKIP_KERNEL
    (void)variant; // Deliberate no-op numerical negative; absent in production.
#else
#ifdef IRIS_COMBINED
    if(variant)merlin_vme_gemm_i8_twin(c[h],a[h],b[h],test->bias?bias[h]:0,test->m,test->n,test->k);
    else
#else
    (void)variant;
#endif
    merlin_vme_gemm_i8(c[h],a[h],b[h],test->bias?bias[h]:0,test->m,test->n,test->k);
#endif
  }
  else {
    __asm__ volatile("vsetivli zero,4,e32,m1,ta,ma\n\tvmv.v.x v0,%0\n\tvadd.vi v0,v0,9\n\tvse32.v v0,(%1)\n\tfence rw,rw"
      ::"r"(7UL+number),"r"(producer):"memory");
  }
  memory_fence();uint64_t endret=retired(),end=cycles();
  const uint32_t *values=h<2?(const uint32_t *)c[h]:producer;
  unsigned count=h<2?test->m*test->n:4,failed=0;
  for(unsigned p=0;p<count;++p)failed+=values[p]!=test->golden[h][p];
  results[h].start=start;results[h].end=end;results[h].instret=endret-instret;
  results[h].checksum=checksum(values,count);results[h].failed=failed;
}
static const char *variant_name(unsigned variant) {
#ifdef IRIS_COMBINED
  return variant?"twin":"vme";
#else
  (void)variant;return VARIANT_NAME;
#endif
}
static void print_id(const case_t *test,unsigned variant,unsigned trial,unsigned parent) {
  putstr(test->id);
#ifdef IRIS_COMBINED
  putstr(".variant-");putstr(variant_name(variant));
  if(!parent){putstr(".trial");putuint(trial);}
#else
  (void)variant;(void)trial;(void)parent;
#endif
}
static void print(unsigned h,const case_t *test,unsigned variant,unsigned trial) {
  putstr("IRIS_REGION {\"case_id\":\"");print_id(test,variant,trial,0);
  putstr("\",\"parent_case_id\":\"");print_id(test,variant,trial,1);
  putstr("\",\"suite\":\"compiler_i8_wrap\",\"region\":\"kernel\",\"hart\":");putuint(h);
  putstr(",\"variant\":\"");putstr(variant_name(variant));putstr("\",\"trial_id\":");putuint(trial);
  putstr(",\"start_cycle\":");putuint(results[h].start);
  putstr(",\"end_cycle\":");putuint(results[h].end);putstr(",\"instret_delta\":");putuint(results[h].instret);
  putstr(",\"checksum\":");putuint(results[h].checksum);putstr(",\"expected_checksum\":");putuint(test->checksum[h]);
  putstr(",\"failed_words\":");putuint(results[h].failed);putstr(",\"pass\":");
  putstr(results[h].checksum==test->checksum[h]&&!results[h].failed?"true":"false");putstr("}\n");
}
void benchmark_main(unsigned h) {
  unsigned failed=0,count=sizeof(cases)/sizeof(cases[0]);
#ifdef IRIS_COMBINED
  const unsigned trials=3,variants=2;
#else
  const unsigned trials=1,variants=1;
#endif
  for(unsigned trial=0;trial<trials;++trial)for(unsigned variant=0;variant<variants;++variant)for(unsigned i=0;i<count;++i) {
    execute(h,i,&cases[i],variant);barrier();
    if(!h)for(unsigned hart=0;hart<3;++hart){print(hart,&cases[i],variant,trial);failed+=results[hart].failed;}
    barrier();
  }
  if(!h){putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"regions\":");putuint(count*3*trials*variants);putstr("}\n");finish(failed!=0);}
  for(;;)__asm__ volatile("wfi");
}
