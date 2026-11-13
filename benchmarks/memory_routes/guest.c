#include "runtime.h"

enum { K_chase, K_read, K_write };
typedef struct {
  const char *id;
  uintptr_t base;
  unsigned kind, stride, spread, n, mask;
  uint64_t expected[3];
} case_t;
#include "cases.inc"
typedef struct __attribute__((aligned(64))) {
  uint64_t begin, end, instructions, checksum;
} result_t;
static result_t results[3];
static unsigned complete, done, failed;

static uintptr_t address(const case_t *c, unsigned h) {
  return c->base + h*0x8000UL + (c->spread ? 64*(h&1) : 0);
}
static void prepare(const case_t *c, unsigned h) {
  uintptr_t base = address(c,h);
  for(unsigned i=0;i<64;++i)
    *(volatile uint64_t *)(base+i*c->stride) = c->kind==K_chase ? base+((i+13)%64)*c->stride : 0x1000+256*h+i;
  memory_fence();
}
static __attribute__((noinline)) uint64_t kernel(const case_t *c, unsigned h) {
  uintptr_t base=address(c,h);
  uint64_t sum=0;
  if(c->kind==K_chase) {
    uintptr_t next=base;
    for(unsigned i=0;i<c->n;++i)
      __asm__ volatile("ld %0,0(%0)":"+r"(next)::"memory");
    return next;
  }
  if(c->kind==K_read) {
    for(unsigned pass=0;pass<c->n;++pass)
      for(unsigned i=0;i<64;++i) sum+=*(volatile uint64_t *)(base+i*c->stride);
    return sum;
  }
  for(unsigned pass=0;pass<c->n;++pass)
    for(unsigned i=0;i<64;++i) *(volatile uint64_t *)(base+i*c->stride)=(pass+1)*256+h;
  return 0;
}
static void run(const case_t *c,unsigned h) {
  if(h==0) {complete=0;done=0;}
  if(c->mask&(1U<<h)) prepare(c,h);
  barrier();
  if(c->mask&(1U<<h)) {
    memory_fence();
    uint64_t begin=cycles(), instructions=retired();
    uint64_t checksum=kernel(c,h);
    memory_fence();
    uint64_t end_instructions=retired(), end=cycles();
    // Verification reads are outside the measured interval.
    if(c->kind==K_write) {
      uintptr_t base=address(c,h);
      for(unsigned i=0;i<64;++i) checksum+=*(volatile uint64_t *)(base+i*c->stride);
    }
    results[h]=(result_t){begin,end,end_instructions-instructions,checksum};
    unsigned active=__builtin_popcount(c->mask);
    if(__atomic_add_fetch(&complete,1,__ATOMIC_ACQ_REL)==active) {
      __atomic_store_n(&done,1,__ATOMIC_RELEASE);
      for(unsigned i=0;i<3;++i) if(!(c->mask&(1U<<i))) send_ipi(i);
    }
  } else {
    for(;;) {
      __asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory");
      unsigned finished=__atomic_load_n(&done,__ATOMIC_ACQUIRE);
      if(!finished) __asm__ volatile("wfi":::"memory");
      __asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
      if(finished) break;
    }
  }
  barrier();
  if(h==0) for(unsigned i=0;i<3;++i) if(c->mask&(1U<<i)) {
    result_t r=results[i];
    unsigned pass=r.checksum==c->expected[i];
    if(!pass) ++failed;
    putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);
    putstr("\",\"region\":\"kernel\",\"hart\":");putuint(i);
    putstr(",\"start_cycle\":");putuint(r.begin);
    putstr(",\"end_cycle\":");putuint(r.end);
    putstr(",\"instret_delta\":");putuint(r.instructions);
    putstr(",\"checksum\":");putuint(r.checksum);
    putstr(",\"expected_checksum\":");putuint(c->expected[i]);
    putstr(",\"pass\":");putstr(pass?"true":"false");putstr("}\n");
  }
  barrier();
}
void benchmark_main(unsigned h) {
  for(unsigned i=0;i<sizeof(experiments)/sizeof(experiments[0]);++i) run(&experiments[i],h);
  if(h==0) {
    putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr("}\n");
    finish(failed?1:0);
  }
  for(;;) __asm__ volatile("wfi");
}
