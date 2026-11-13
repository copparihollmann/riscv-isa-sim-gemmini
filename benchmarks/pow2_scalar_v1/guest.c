#include "runtime.h"
typedef struct { const char *id; unsigned kind,n,hart,trial; uint64_t expected[4]; } case_t;
#include "cases.inc"
typedef struct {
 uint64_t case_index,hart,start,end,instret,values[4],mtime_before,mtime_after;
} record_t;
volatile record_t scalar_records[576];
volatile uint64_t scalar_record_count,scalar_measurements_done=UINT64_MAX;
static volatile unsigned done;
static unsigned failed;
static uint64_t result_values[4] __attribute__((aligned(64)));
static uint64_t result_start,result_end,result_instret,result_time_before,result_time_after;
#define DECL(name) extern uint64_t scalar_pow2_##name(unsigned,uint64_t *);
DECL(integer_dependent) DECL(integer_independent4)
DECL(fp16_dependent) DECL(fp16_independent4)
DECL(fp32_dependent) DECL(fp32_independent4)
DECL(fp64_dependent) DECL(fp64_independent4)
#ifndef IRIS_SKIP_KERNEL
static uint64_t (*const functions[])(unsigned,uint64_t *)={
 scalar_pow2_integer_dependent,scalar_pow2_integer_independent4,
 scalar_pow2_fp16_dependent,scalar_pow2_fp16_independent4,
 scalar_pow2_fp32_dependent,scalar_pow2_fp32_independent4,
 scalar_pow2_fp64_dependent,scalar_pow2_fp64_independent4
};
#endif
static void run(unsigned ci,unsigned h) {
 const case_t *c=&experiments[ci];
 if(h==0) {done=0;for(unsigned i=0;i<4;++i)result_values[i]=0;}
 barrier();
 if(h==c->hart) {
  memory_fence();uint64_t tb=mtime(),b=cycles(),ir=retired();
#ifndef IRIS_SKIP_KERNEL
  functions[c->kind](c->n,result_values);
#endif
  memory_fence();uint64_t ie=retired(),e=cycles(),te=mtime();
  result_start=b;result_end=e;result_instret=ie-ir;result_time_before=tb;result_time_after=te;
  __atomic_store_n(&done,1,__ATOMIC_RELEASE);
  for(unsigned peer=0;peer<3;++peer)if(peer!=h)send_ipi(peer);
 } else for(;;) {
  __asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory");
  unsigned x=__atomic_load_n(&done,__ATOMIC_ACQUIRE);
  if(!x)__asm__ volatile("wfi":::"memory");
  __asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
  if(x)break;
 }
 barrier();
 if(h==0) {
  record_t r={ci,c->hart,result_start,result_end,result_instret,{0,0,0,0},result_time_before,result_time_after};
  unsigned bad=0;
  for(unsigned i=0;i<4;++i){r.values[i]=result_values[i];bad|=r.values[i]!=c->expected[i];}
  failed+=bad;scalar_records[scalar_record_count++]=r;
 }
 barrier();
}
static void emit(unsigned first,unsigned end) {
 for(unsigned i=first;i<end;++i) {
  record_t r=scalar_records[i];const case_t*c=&experiments[r.case_index];unsigned ok=1;
  for(unsigned j=0;j<4;++j)ok&=r.values[j]==c->expected[j];
  putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);
  putstr("\",\"suite\":\"pow2_scalar\",\"region\":\"kernel\",\"hart\":");putuint(r.hart);
  putstr(",\"kind_index\":");putuint(c->kind);putstr(",\"n\":");putuint(c->n);
  putstr(",\"trial_id\":");putuint(c->trial);
  putstr(",\"start_cycle\":");putuint(r.start);putstr(",\"end_cycle\":");putuint(r.end);
  putstr(",\"instret_delta\":");putuint(r.instret);
  putstr(",\"mtime_before\":");putuint(r.mtime_before);putstr(",\"mtime_after\":");putuint(r.mtime_after);
  putstr(",\"values\":[");
  for(unsigned j=0;j<4;++j){if(j)putstr(",");putuint(r.values[j]);}
  putstr("],\"checksum\":");putuint(r.values[0]);putstr(",\"expected_checksum\":");putuint(c->expected[0]);
  putstr(",\"pass\":");putstr(ok?"true":"false");putstr("}\n");
 }
}
void benchmark_main(unsigned h) {
 unsigned printed=0;
 for(unsigned ci=0;ci<576;++ci) {
  run(ci,h);
  if(ci%24==23) {
   barrier();
   if(h==0) {
    emit(printed,scalar_record_count);printed=scalar_record_count;
    putstr("IRIS_SCALAR_GROUP {\"group\":");putuint(ci/24);
    putstr(",\"records\":");putuint(printed);putstr("}\n");
   }
   barrier();
  }
 }
 barrier();
 if(h==0) {
  memory_fence();scalar_measurements_done=0;memory_fence();
  putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);
  putstr(",\"cases\":576,\"regions\":576,\"trials\":3}\n");finish(failed?1:0);
 }
 for(;;)__asm__ volatile("wfi");
}
