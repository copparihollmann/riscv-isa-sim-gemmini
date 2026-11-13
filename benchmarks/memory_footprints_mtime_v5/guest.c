#include "runtime.h"
typedef struct {const char *id;unsigned nodes,mask,trial;} case_t;
#include "cases.inc"
typedef struct {uint64_t case_index,pass,hart,start,end,instret,checksum,expected,mtime_before,mtime_after;} record_t;
volatile record_t footprint_records[360];
volatile uint64_t footprint_record_count,footprint_measurements_done=UINT64_MAX;
static unsigned complete,done,failed;
static uintptr_t base(unsigned h){return 0x90000000UL+h*0x02000000UL;}
static unsigned index_of(unsigned i,unsigned n,unsigned trial,unsigned h){i^=i>>3;i=(i*13)&(n-1);i^=i>>5;return(i+17*trial+7*h)&(n-1);}
static void prepare(const case_t*c,unsigned h){for(unsigned i=0;i<c->nodes;++i)*(volatile uintptr_t*)(base(h)+64UL*index_of(i,c->nodes,c->trial,h))=base(h)+64UL*index_of((i+1)&(c->nodes-1),c->nodes,c->trial,h);memory_fence();}
extern uintptr_t footprint_chase(uintptr_t,unsigned);
__asm__(".text\n.option push\n.option norvc\n.balign 4\n.globl footprint_chase\n.type footprint_chase,@function\nfootprint_chase:\n1: ld a0,0(a0)\naddi a1,a1,-1\nbnez a1,1b\nret\n.size footprint_chase,.-footprint_chase\n.option pop\n");
typedef struct __attribute__((aligned(64))) {uint64_t start,end,instret,checksum,mtime_before,mtime_after;} result_t;
static result_t results[3];
static void run(unsigned ci,unsigned pass,unsigned h){
 const case_t*c=&experiments[ci];const unsigned mask=c->mask,n=c->nodes;uintptr_t start=base(h)+64UL*index_of(0,n,c->trial,h);
 if(h==0){complete=0;done=0;}barrier();
 if(mask&(1U<<h)){
  memory_fence();uint64_t time_before=mtime();uint64_t begin=cycles(),ir=retired();
#ifdef IRIS_FOOTPRINT_SKIP_KERNEL
  (void)start;uintptr_t checksum=0;
#else
  uintptr_t checksum=footprint_chase(start,n);
#endif
  memory_fence();uint64_t end_ir=retired(),end=cycles();uint64_t time_after=mtime();results[h]=(result_t){begin,end,end_ir-ir,checksum,time_before,time_after};
  if(__atomic_add_fetch(&complete,1,__ATOMIC_ACQ_REL)==(unsigned)__builtin_popcount(mask)){
   __atomic_store_n(&done,1,__ATOMIC_RELEASE);for(unsigned i=0;i<3;++i)if(!(mask&(1U<<i)))send_ipi(i);
  }
 }else for(;;){__asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory");unsigned x=__atomic_load_n(&done,__ATOMIC_ACQUIRE);if(!x)__asm__ volatile("wfi":::"memory");__asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");if(x)break;}
 barrier();
 if(h==0)for(unsigned i=0;i<3;++i)if(mask&(1U<<i)){
  uintptr_t expected=base(i)+64UL*index_of(0,n,c->trial,i);result_t r=results[i];if(r.checksum!=expected)++failed;
  footprint_records[footprint_record_count++]=(record_t){ci,pass,i,r.start,r.end,r.instret,r.checksum,expected,r.mtime_before,r.mtime_after};
 }
 barrier();
}
void benchmark_main(unsigned h){
 for(unsigned ci=0;ci<105;++ci){if(ci%7==0){prepare(&experiments[ci],h);barrier();}for(unsigned pass=0;pass<2;++pass)run(ci,pass,h);}
 barrier();if(h==0){memory_fence();footprint_measurements_done=0;memory_fence();
  for(unsigned i=0;i<footprint_record_count;++i){record_t r=footprint_records[i];const case_t*c=&experiments[r.case_index];
   putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);putstr(".pass");putuint(r.pass);putstr("\",\"parent_case_id\":\"");putstr(c->id);
   putstr("\",\"suite\":\"memory_footprints\",\"region\":\"chase\",\"trial_id\":");putuint(c->trial);putstr(",\"pass_index\":");putuint(r.pass);putstr(",\"hart\":");putuint(r.hart);
   putstr(",\"footprint_bytes\":");putuint((uint64_t)c->nodes*64);putstr(",\"body_loads\":");putuint(c->nodes);putstr(",\"requested_bytes\":");putuint((uint64_t)c->nodes*8);
   putstr(",\"mtime_before\":");putuint(r.mtime_before);putstr(",\"mtime_after\":");putuint(r.mtime_after);
   putstr(",\"mtime_hz\":500000,\"source_core_cycles_per_mtime_tick\":1000,\"mtime_scope\":\"encloses_CSR_ROI_with_sampling_overhead\",\"mtime_quantization_error_bound_core_cycles\":1000");
   putstr(",\"start_cycle\":");putuint(r.start);putstr(",\"end_cycle\":");putuint(r.end);putstr(",\"instret_delta\":");putuint(r.instret);putstr(",\"checksum\":");putuint(r.checksum);putstr(",\"expected_checksum\":");putuint(r.expected);putstr(",\"pass\":");putstr(r.checksum==r.expected?"true":"false");putstr("}\n");
  }
  putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"cases\":105,\"regions\":360,\"trials\":3}\n");finish(failed?1:0);
 }for(;;)__asm__ volatile("wfi");
}
