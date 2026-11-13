#include "runtime.h"

typedef struct { const char *id,*parent; unsigned lmul,avl,drain,trial; uint64_t expected; } case_t;
#include "cases.inc"
static uint8_t input[4][256] __attribute__((aligned(64)));
static uint8_t output[4][256] __attribute__((aligned(64)));
static volatile uint64_t request __attribute__((aligned(64)));
static volatile uint64_t complete __attribute__((aligned(64)));
static struct { uint64_t start,end,instret,checksum,vl; } result __attribute__((aligned(64)));

static unsigned setvl(unsigned avl,unsigned lmul) {
  unsigned long vl=0;
  switch(lmul) {
#define VSET(M) case M: __asm__ volatile("vsetvli %0,%1,e8,m" #M ",ta,ma":"=r"(vl):"r"((unsigned long)avl):"memory"); break
    VSET(1);VSET(2);VSET(4);VSET(8);
  }
  return vl;
}
static uint64_t checksum(unsigned vl) {
  uint64_t value=14695981039346656037ULL;
  for(unsigned group=0;group<4;++group)for(unsigned i=0;i<vl;++i)
    value=(value^output[group][i])*1099511628211ULL;
  return value;
}
static void transport(const case_t *c) {
  uint64_t begin=cycles(),ret=retired();
  unsigned vl=setvl(c->avl,c->lmul);
  /* The unfenced load batch intentionally matches the four independent
   * LMUL8 groups used by Zephyr's first lazy vector restore. No breadcrumb,
   * scalar memory access or function call is inserted between these loads. */
  unsigned drain=c->drain;
#define LOADS(FENCE) __asm__ volatile("vle8.v v0,(%0)\n\t" FENCE "vle8.v v8,(%1)\n\t" FENCE "vle8.v v16,(%2)\n\t" FENCE "vle8.v v24,(%3)\n\t" FENCE ::"r"(input[0]),"r"(input[1]),"r"(input[2]),"r"(input[3]):"memory")
  if(drain) { LOADS("fence rw,rw\n\t"); } else { LOADS(""); }
#define STORES(FENCE) __asm__ volatile("vse8.v v0,(%0)\n\t" FENCE "vse8.v v8,(%1)\n\t" FENCE "vse8.v v16,(%2)\n\t" FENCE "vse8.v v24,(%3)\n\t" FENCE ::"r"(output[0]),"r"(output[1]),"r"(output[2]),"r"(output[3]):"memory")
  if(drain) { STORES("fence rw,rw\n\t"); } else { STORES(""); }
  /* Both modes share one final visibility fence before the host checks data. */
  memory_fence();
  uint64_t lastret=retired(),end=cycles();
  result.start=begin;result.end=end;result.instret=lastret-ret;
  result.vl=vl;result.checksum=checksum(vl);
}
static void print_region(const case_t *c) {
  putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);
  putstr("\",\"parent_case_id\":\"");putstr(c->parent);
  putstr("\",\"suite\":\"rvv_context_transport\",\"region\":\"kernel\",\"hart\":2,\"lmul\":");putuint(c->lmul);
  putstr(",\"avl\":");putuint(c->avl);putstr(",\"vl\":");putuint(result.vl);
  putstr(",\"drain\":");putuint(c->drain);putstr(",\"trial_id\":");putuint(c->trial);
  putstr(",\"start_cycle\":");putuint(result.start);putstr(",\"end_cycle\":");putuint(result.end);
  putstr(",\"instret_delta\":");putuint(result.instret);putstr(",\"checksum\":");putuint(result.checksum);
  putstr(",\"expected_checksum\":");putuint(c->expected);putstr(",\"pass\":");
  putstr(result.checksum==c->expected&&result.vl==c->avl?"true":"false");putstr("}\n");
}
void benchmark_main(unsigned hart) {
  if(hart==0)for(unsigned group=0;group<4;++group)for(unsigned i=0;i<256;++i)
    input[group][i]=(uint8_t)(i*17+group*61+13);
  barrier();
  if(hart==1)for(;;)__asm__ volatile("wfi");
  if(hart==2) {
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
      while(__atomic_load_n(&request,__ATOMIC_ACQUIRE)!=i+1){}
      transport(&cases[i]);
      __atomic_store_n(&complete,i+1,__ATOMIC_RELEASE);
    }
    for(;;)__asm__ volatile("wfi");
  }
  unsigned failed=0;
  for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);++i) {
    const case_t *c=&cases[i];
    putstr("IRIS_PROBE_BEGIN {\"case_id\":\"");putstr(c->id);putstr("\",\"hart\":2}\n");
    uint64_t deadline=mtime()+250000;
    __atomic_store_n(&request,i+1,__ATOMIC_RELEASE);
    unsigned polls=0;
    while(__atomic_load_n(&complete,__ATOMIC_ACQUIRE)!=i+1) {
      if((++polls&1023)==0&&mtime()>deadline) {
        putstr("IRIS_PROBE_TIMEOUT {\"case_id\":\"");putstr(c->id);
        putstr("\",\"hart\":2,\"deadline_mtime\":");putuint(deadline);putstr("}\n");finish(1);
      }
    }
    print_region(c);
    if(result.checksum!=c->expected||result.vl!=c->avl)++failed;
  }
  putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"regions\":");
  putuint(sizeof(cases)/sizeof(cases[0]));putstr("}\n");finish(failed!=0);
}
