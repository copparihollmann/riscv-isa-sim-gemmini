/* Supplemental placement acceptance: LR/SC, CLINT IPI, and fenced messages. */
#include "runtime.h"

enum { LRSC, IPI, FENCE_MESSAGES, LRSC_INVALIDATED };
typedef struct __attribute__((aligned(64))) { uint64_t value; } word_t;
typedef struct __attribute__((aligned(64))) { uint64_t start,end,retired,result; } result_t;
static result_t results[3];
static word_t payload[3],ready[3];
static uint64_t shared_counter __attribute__((aligned(64)));
static unsigned interference_phase __attribute__((aligned(64)));
static unsigned done,complete,sub_arrivals,sub_generation,failures;
static const unsigned masks[]={1,2,4,3,5,6,7};
static const char *names[]={"distribution.lrsc","distribution.ipi","distribution.fence_messages","distribution.lrsc_invalidated"};
static unsigned count(unsigned mask) { return (mask&1)+((mask>>1)&1)+((mask>>2)&1); }
static void subgroup_barrier(unsigned participants) {
  unsigned generation=__atomic_load_n(&sub_generation,__ATOMIC_ACQUIRE);
  if(__atomic_add_fetch(&sub_arrivals,1,__ATOMIC_ACQ_REL)==participants) {
    __atomic_store_n(&sub_arrivals,0,__ATOMIC_RELAXED);
    __atomic_add_fetch(&sub_generation,1,__ATOMIC_RELEASE);
  } else while(__atomic_load_n(&sub_generation,__ATOMIC_ACQUIRE)==generation) {}
}
static unsigned next_hart(unsigned h,unsigned mask,int direction) {
  for(unsigned step=1;step<=3;++step) {
    unsigned next=(h+(direction>0?step:3-step))%3;
    if(mask&(1U<<next)) return next;
  }
  return h;
}
static uint64_t work(unsigned h,unsigned kind,unsigned mask) {
  if(kind==LRSC_INVALIDATED) {
    unsigned victim=0;while(!(mask&(1U<<victim))) ++victim;
    unsigned writer=next_hart(victim,mask,1);
    if(h==victim) {
      uint64_t value,status;
      __asm__ volatile("lr.d.aq %0,(%1)":"=r"(value):"r"(&shared_counter):"memory");
      __atomic_store_n(&interference_phase,1,__ATOMIC_RELEASE);
      while(__atomic_load_n(&interference_phase,__ATOMIC_ACQUIRE)!=2) {}
      __asm__ volatile("sc.d.rl %0,%1,(%2)":"=r"(status):"r"(9UL),"r"(&shared_counter):"memory");
      return value==0&&status!=0&&__atomic_load_n(&shared_counter,__ATOMIC_RELAXED)==7;
    }
    if(h==writer) {
      while(__atomic_load_n(&interference_phase,__ATOMIC_ACQUIRE)!=1) {}
      __atomic_store_n(&shared_counter,7,__ATOMIC_RELAXED);
      __atomic_store_n(&interference_phase,2,__ATOMIC_RELEASE);
    } else while(__atomic_load_n(&interference_phase,__ATOMIC_ACQUIRE)!=2) {}
    return __atomic_load_n(&shared_counter,__ATOMIC_RELAXED)==7;
  }
  if(kind==LRSC) {
    for(unsigned i=0;i<64;++i) {
      uint64_t value,status;
      __asm__ volatile("1:\tlr.d.aq %0,(%2)\n\taddi %0,%0,1\n\tsc.d.rl %1,%0,(%2)\n\tbnez %1,1b"
                       :"=&r"(value),"=&r"(status):"r"(&shared_counter):"memory");
    }
    return 64;
  }
  if(kind==IPI) {
    uint64_t initial=ipi_seen[h];
    for(unsigned i=0;i<8;++i) {
      uint64_t before=ipi_seen[h];subgroup_barrier(count(mask));
      send_ipi(next_hart(h,mask,1));
      while(ipi_seen[h]==before) {}
      subgroup_barrier(count(mask));
    }
    return ipi_seen[h]-initial;
  }
  uint64_t sum=0;unsigned predecessor=next_hart(h,mask,-1);
  for(unsigned iteration=1;iteration<=16;++iteration) {
    __atomic_store_n(&payload[h].value,iteration,__ATOMIC_RELAXED);
    __asm__ volatile("fence w,w":::"memory");
    __atomic_store_n(&ready[h].value,iteration,__ATOMIC_RELAXED);
    while(__atomic_load_n(&ready[predecessor].value,__ATOMIC_RELAXED)!=iteration) {}
    __asm__ volatile("fence r,r":::"memory");
    sum+=__atomic_load_n(&payload[predecessor].value,__ATOMIC_RELAXED);
    subgroup_barrier(count(mask));
  }
  return sum;
}
static void identifier(unsigned kind,unsigned mask) { putstr(names[kind]);putstr(".mask");putuint(mask); }
static void run(unsigned kind,unsigned mask) {
  unsigned h=hart_id();
  if(h==0) {
    done=complete=sub_arrivals=sub_generation=interference_phase=0;shared_counter=0;
    for(unsigned i=0;i<3;++i) {payload[i].value=ready[i].value=0;}
  }
  barrier();
  if(mask&(1U<<h)) {
    memory_fence();uint64_t start=cycles(),before=retired();
    uint64_t value=work(h,kind,mask);
    memory_fence();uint64_t after=retired(),end=cycles();
    results[h]=(result_t){start,end,after-before,value};
    if(__atomic_add_fetch(&complete,1,__ATOMIC_ACQ_REL)==count(mask)) {
      __atomic_store_n(&done,1,__ATOMIC_RELEASE);
      for(unsigned i=0;i<3;++i) if(!(mask&(1U<<i))) send_ipi(i);
    }
  } else for(;;) {
    __asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory");
    unsigned finished=__atomic_load_n(&done,__ATOMIC_ACQUIRE);
    if(!finished) __asm__ volatile("wfi":::"memory");
    __asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
    if(finished) break;
  }
  barrier();
  if(h==0) {
    uint64_t golden=kind==LRSC?64:kind==IPI?8:kind==LRSC_INVALIDATED?1:136;
    if(kind==LRSC||kind==LRSC_INVALIDATED) {
      uint64_t expected=kind==LRSC?64*count(mask):7;unsigned pass=shared_counter==expected;if(!pass) ++failures;
      putstr("IRIS_SYNC_ASSERT {\"case_id\":\"");identifier(kind,mask);
      putstr("\",\"name\":\"shared_counter\",\"actual\":");putuint(shared_counter);
      putstr(",\"expected\":");putuint(expected);putstr(",\"pass\":");putstr(pass?"true":"false");putstr("}\n");
    }
    for(unsigned i=0;i<3;++i) if(mask&(1U<<i)) {
      result_t r=results[i];unsigned pass=r.result==golden;if(!pass) ++failures;
      putstr("IRIS_REGION {\"case_id\":\"");identifier(kind,mask);
      putstr("\",\"region\":\"kernel\",\"hart\":");putuint(i);
      putstr(",\"start_cycle\":");putuint(r.start);putstr(",\"end_cycle\":");putuint(r.end);
      putstr(",\"instret_delta\":");putuint(r.retired);putstr(",\"checksum\":");putuint(r.result);
      putstr(",\"expected_checksum\":");putuint(golden);putstr(",\"pass\":");putstr(pass?"true":"false");putstr("}\n");
    }
  }
  barrier();
}
void benchmark_main(unsigned h) {
  for(unsigned kind=0;kind<3;++kind) for(unsigned i=0;i<7;++i) run(kind,masks[i]);
  for(unsigned i=3;i<7;++i) run(LRSC_INVALIDATED,masks[i]);
  if(h==0) {putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failures);putstr("}\n");finish(failures?1:0);}
  for(;;) __asm__ volatile("wfi");
}
