#include "runtime.h"
typedef struct {const char *id;unsigned nodes,loads,hart,trial;} case_t;
#include "cases.inc"
typedef struct __attribute__((aligned(128))) {
 uint64_t case_index,phase,hart,start,end,instret,checksum,expected;
 uint64_t mtime_before,mtime_after,loads,evict_sum,msip_before,msip_after;
} record_t;
volatile record_t footprint_records[234];
volatile uint64_t footprint_record_count;
volatile uint64_t footprint_measurements_done=UINT64_MAX;
typedef struct __attribute__((aligned(128))) {unsigned value;} token_t;
static token_t parked[3],completion;
static uintptr_t base(unsigned h){return 0x90000000UL+h*0x02000000UL;}
static uintptr_t eviction_base(unsigned h){return base(h)+0x01000000UL;}
static void io_fence(void){__asm__ volatile("fence iorw,iorw":::"memory");}
static unsigned msip(void){unsigned long x;__asm__ volatile("csrr %0,mip":"=r"(x));return(x>>3)&1;}
static void clear_ipi(unsigned h){*(volatile uint32_t*)(IRIS_CLINT+4*h)=0;io_fence();}
static unsigned index_of(unsigned i,unsigned n,unsigned t,unsigned h){i^=i>>3;i=(i*13)&(n-1);i^=i>>5;return(i+17*t+7*h)&(n-1);}
static void prepare(const case_t*c,unsigned h){for(unsigned i=0;i<c->nodes;++i)*(volatile uintptr_t*)(base(h)+64UL*index_of(i,c->nodes,c->trial,h))=base(h)+64UL*index_of((i+1)&(c->nodes-1),c->nodes,c->trial,h);memory_fence();}
extern uintptr_t footprint_chase(uintptr_t,unsigned);
extern uint64_t footprint_evict(uintptr_t,unsigned);
__asm__(".text\n.option push\n.option norvc\n.balign 4\n.globl footprint_chase\n.type footprint_chase,@function\nfootprint_chase:\n1: ld a0,0(a0)\naddi a1,a1,-1\nbnez a1,1b\nret\n.size footprint_chase,.-footprint_chase\n"
".balign 4\n.globl footprint_evict\n.type footprint_evict,@function\nfootprint_evict:\nli a2,0\n1: ld a3,0(a0)\nadd a2,a2,a3\naddi a0,a0,64\naddi a1,a1,-1\nbnez a1,1b\nmv a0,a2\nret\n.size footprint_evict,.-footprint_evict\n.option pop\n");
static void wait_epoch(unsigned epoch,unsigned h){
 clear_ipi(h);
 __atomic_store_n(&parked[h].value,epoch,__ATOMIC_RELEASE);io_fence();
 while(__atomic_load_n(&completion.value,__ATOMIC_ACQUIRE)<epoch)__asm__ volatile("wfi":::"memory");
 /* Completion can become visible before its MMIO wake. Consume that wake
  * before nextepoch's ack, so an old delayed MSIP cannot cause polling. */
 while(!msip())__asm__ volatile("wfi":::"memory");
 clear_ipi(h);
}
static void emit(void){
 unsigned failed=0;
 for(unsigned i=0;i<234;++i){record_t r=footprint_records[i];const case_t*c=&experiments[r.case_index];unsigned ok=r.checksum==r.expected&&r.msip_before==0&&r.msip_after==0;
  if(!ok)++failed;
  putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);putstr(r.phase?".steady":".cold");putstr("\",\"parent_case_id\":\"");putstr(c->id);
  putstr("\",\"suite\":\"pow2_isolated_memory\",\"region\":\"chase\",\"trial_id\":");putuint(c->trial);putstr(",\"pass_index\":");putuint(r.phase);putstr(",\"hart\":");putuint(r.hart);
  putstr(",\"footprint_bytes\":");putuint((uint64_t)c->nodes*64);putstr(",\"body_loads\":");putuint(r.loads);putstr(",\"whole_laps\":");putuint(r.loads/c->nodes);putstr(",\"requested_bytes\":");putuint(r.loads*8);
  putstr(",\"eviction_checksum\":");putuint(r.evict_sum);putstr(",\"eviction_loads\":131072,\"msip_before\":");putuint(r.msip_before);putstr(",\"msip_after\":");putuint(r.msip_after);
  putstr(",\"mtime_before\":");putuint(r.mtime_before);putstr(",\"mtime_after\":");putuint(r.mtime_after);
  putstr(",\"mtime_hz\":500000,\"source_core_cycles_per_mtime_tick\":1000,\"mtime_scope\":\"encloses_CSR_ROI_with_sampling_overhead\",\"mtime_quantization_error_bound_core_cycles\":1000");
  putstr(",\"start_cycle\":");putuint(r.start);putstr(",\"end_cycle\":");putuint(r.end);putstr(",\"instret_delta\":");putuint(r.instret);putstr(",\"checksum\":");putuint(r.checksum);putstr(",\"expected_checksum\":");putuint(r.expected);putstr(",\"pass\":");putstr(ok?"true":"false");putstr("}\n");
 }
 putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"cases\":117,\"regions\":234,\"trials\":3}\n");finish(failed?1:0);
}
void benchmark_main(unsigned h){
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,%0"::"r"(8UL):"memory");clear_ipi(h);
 unsigned eviction_initialized=0;
 for(unsigned ci=0;ci<117;++ci){const case_t*c=&experiments[ci];unsigned epoch=ci+1;
  if(c->hart!=h){wait_epoch(epoch,h);continue;}
  clear_ipi(h);
  for(unsigned peer=0;peer<3;++peer)if(peer!=h)while(__atomic_load_n(&parked[peer].value,__ATOMIC_ACQUIRE)!=epoch){}
  io_fence();
  if(!eviction_initialized){for(unsigned i=0;i<131072;++i)*(volatile uint64_t*)(eviction_base(h)+64UL*i)=0x1001+h;memory_fence();eviction_initialized=1;}
  prepare(c,h);uintptr_t start=base(h)+64UL*index_of(0,c->nodes,c->trial,h);
  if(footprint_chase(start,c->nodes)!=start)fail(h,1,ci,1); /* warm code, independently checked ring */
  uint64_t evict=footprint_evict(eviction_base(h),131072);memory_fence();
  if(evict!=131072UL*(0x1001+h))fail(h,1,ci,2);
  for(unsigned phase=0;phase<2;++phase){
   memory_fence();uint64_t before_ipi=msip(),tb=mtime(),begin=cycles(),ir=retired();
#ifdef IRIS_FOOTPRINT_SKIP_KERNEL
   uintptr_t checksum=0;
#else
   uintptr_t checksum=footprint_chase(start,c->loads);
#endif
   memory_fence();uint64_t end_ir=retired(),end=cycles(),ta=mtime(),after_ipi=msip();
   footprint_records[ci*2+phase]=(record_t){ci,phase,h,begin,end,end_ir-ir,checksum,start,tb,ta,c->loads,evict,before_ipi,after_ipi};
  }
  __atomic_store_n(&completion.value,epoch,__ATOMIC_RELEASE);io_fence();
  for(unsigned peer=0;peer<3;++peer)if(peer!=h){send_ipi(peer);io_fence();}
 }
 if(h==0){footprint_record_count=234;memory_fence();footprint_measurements_done=0;memory_fence();emit();}
 for(;;)__asm__ volatile("wfi");
}
