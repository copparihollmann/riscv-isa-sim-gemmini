#include "runtime.h"
#include "vme.h"

typedef uint64_t (*kernel_t)(unsigned, unsigned);
typedef struct __attribute__((aligned(64))) { uint64_t start,end,instret,checksum,expected; } result_t;
static result_t results[IRIS_HARTS] __attribute__((aligned(64)));
static uint32_t dram[IRIS_HARTS][262144] __attribute__((aligned(64)));
static uint32_t vector_output[IRIS_HARTS][64] __attribute__((aligned(64)));
static uint8_t ones[32] __attribute__((aligned(64)));
static unsigned complete, done;
static uint64_t atomic_counter __attribute__((aligned(64)));
static unsigned failed;

static uint64_t empty(unsigned h,unsigned n) { (void)n; return h; }
static uint64_t dependent(unsigned h,unsigned n) {
  uint64_t x=h+1;
  for(unsigned i=0;i<n;++i) __asm__ volatile("addi %0,%0,3":"+r"(x));
  return x;
}
static uint64_t branches(unsigned h,unsigned n) {
  uint64_t x=h;
  for(unsigned i=0;i<n;++i) {
    __asm__ volatile("andi t0,%1,1\n\tbeqz t0,1f\n\taddi %0,%0,3\n\tj 2f\n1:\taddi %0,%0,1\n2:":"+r"(x):"r"(i):"t0");
  }
  return x;
}
static uint64_t stream(unsigned h,unsigned bytes) {
  volatile uint32_t *p=dram[h]; uint64_t sum=0; unsigned words=bytes/4;
  for(unsigned i=0;i<words;++i) p[i]=i+h;
  memory_fence();
  for(unsigned pass=0;pass<4;++pass) for(unsigned i=0;i<words;++i) sum+=p[i];
  return sum;
}
static uint64_t pointer_chase(unsigned h,unsigned bytes) {
  volatile uint32_t *p=dram[h]; unsigned words=bytes/4;
  for(unsigned i=0;i<words;i+=16) p[i]=(i+16)%words;
  memory_fence(); unsigned at=0;
  for(unsigned i=0;i<4096;++i) at=p[at];
  return at;
}
static uint64_t local_tcm(unsigned h,unsigned bytes) {
  volatile uint32_t *p=(volatile uint32_t *)(0x70000000UL+h*0x20000UL);
  uint64_t sum=0; for(unsigned i=0;i<bytes/4;++i) p[i]=i+1;
  memory_fence(); for(unsigned i=0;i<bytes/4;++i) sum+=p[i]; return sum;
}
static uint64_t scratchpad(unsigned h,unsigned bytes) {
  volatile uint32_t *p=(volatile uint32_t *)(0x580000000UL+h*0x8000UL);
  uint64_t sum=0; for(unsigned i=0;i<bytes/4;++i) p[i]=i+1;
  memory_fence(); for(unsigned i=0;i<bytes/4;++i) sum+=p[i]; return sum;
}
static uint64_t atomics(unsigned h,unsigned n) {
  (void)h;
  for(unsigned i=0;i<n;++i) __atomic_fetch_add(&atomic_counter,1,__ATOMIC_SEQ_CST);
  return n;
}
static uint64_t lrsc(unsigned h,unsigned n) {
  (void)h;
  for(unsigned i=0;i<n;++i) {
    unsigned long value, failed_sc;
    __asm__ volatile("1:\tlr.d.aq %0,(%2)\n\taddi %0,%0,1\n\tsc.d.rl %1,%0,(%2)\n\tbnez %1,1b"
                     :"=&r"(value),"=&r"(failed_sc):"r"(&atomic_counter):"memory");
  }
  return n;
}
static uint64_t sync_barrier(unsigned h,unsigned n) {
  (void)h; for(unsigned i=0;i<n;++i) barrier(); return n;
}
static uint64_t ipi(unsigned h,unsigned n) {
  uint64_t before=ipi_seen[h];
  for(unsigned i=0;i<n;++i) {
    uint64_t previous=ipi_seen[h]; barrier();
    send_ipi((h+1)%IRIS_HARTS);
    while(ipi_seen[h]==previous) {}
    barrier();
  }
  return ipi_seen[h]-before;
}
static uint64_t timer(unsigned h,unsigned n) {
  uint64_t before=timer_seen[h];
  /* RTL mtimecmp has no reset value. Establish a quiet timer before MTIE. */
  set_timer(h,UINT64_MAX);
  __asm__ volatile("csrs mie,%0"::"r"(128UL));
  for(unsigned i=0;i<n;++i) {
    set_timer(h,mtime()+8);
    for(;;) {
      __asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory");
      unsigned seen=timer_seen[h]!=before+i;
      if(!seen) __asm__ volatile("wfi":::"memory");
      __asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");
      if(seen) break;
    }
  }
  __asm__ volatile("csrc mie,%0"::"r"(128UL));
  return timer_seen[h]-before;
}
#define VECTOR_KERNEL(NAME,SEW,LMUL) \
static uint64_t NAME(unsigned h,unsigned n) { \
  unsigned long vl, avl=(unsigned long)-1; \
  __asm__ volatile("vsetvli %0,%1,e" #SEW ",m" #LMUL ",ta,ma\n\tvmv.v.i v8,3\n\tvmv.v.i v16,1":"=r"(vl):"r"(avl):"memory"); \
  for(unsigned i=0;i<n;++i) __asm__ volatile("vadd.vv v8,v8,v16":::"memory"); \
  __asm__ volatile("vse" #SEW ".v v8,(%0)"::"r"(vector_output[h]):"memory"); \
  memory_fence(); uint64_t sum=0; \
  if(SEW==8) for(unsigned i=0;i<vl;++i) sum+=((uint8_t *)vector_output[h])[i]; \
  else for(unsigned i=0;i<vl;++i) sum+=vector_output[h][i]; \
  return sum; \
}
VECTOR_KERNEL(vec_e8_m1,8,1)
VECTOR_KERNEL(vec_e8_m2,8,2)
VECTOR_KERNEL(vec_e32_m1,32,1)
VECTOR_KERNEL(vec_e32_m2,32,2)

static uint64_t vme_mm(unsigned h,unsigned n) {
  vme_vsettnt_e8w4(32); vme_vsettm(32); vme_vsettk(4); VME_VTZERO(0);
  __asm__ volatile("vle8.v v8,(%0)\n\tvle8.v v10,(%0)\n\tvle8.v v12,(%0)\n\tvle8.v v14,(%0)\n\tvle8.v v16,(%0)\n\tvle8.v v18,(%0)\n\tvle8.v v20,(%0)\n\tvle8.v v22,(%0)"::"r"(ones):"memory");
  for(unsigned i=0;i<n;++i) VME_MM_U_U(0,8,16);
  vme_vsettnt_e32w1(32); VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,0));
  __asm__ volatile("vse32.v v24,(%0)"::"r"(vector_output[h]):"memory");
  memory_fence(); uint64_t sum=0; for(unsigned i=0;i<32;++i) sum+=vector_output[h][i]; return sum;
}
static uint64_t refuse_vme(unsigned h,unsigned n) {
  (void)n; uint64_t before=illegal_seen[h]; expect_illegal[h]=1;
  VME_VTDISCARD(); memory_fence();
  if(expect_illegal[h]) { expect_illegal[h]=0; return 0; }
  return illegal_seen[h]-before;
}

static void run(const char *id,kernel_t fn,unsigned argument,unsigned mask,uint64_t expected,unsigned by_hart) {
  unsigned h=hart_id();
  if(h==0) { complete=0; done=0; atomic_counter=0; }
  barrier();
  if(mask&(1U<<h)) {
    memory_fence(); uint64_t start=cycles(), begin_ret=retired();
    uint64_t checksum=fn(h,argument);
    memory_fence(); uint64_t end_ret=retired(), end=cycles();
    results[h]=(result_t){start,end,end_ret-begin_ret,checksum,expected+(uint64_t)by_hart*h};
    unsigned active=0; for(unsigned i=0;i<IRIS_HARTS;++i) active+=(mask>>i)&1;
    if(__atomic_add_fetch(&complete,1,__ATOMIC_ACQ_REL)==active) {
      __atomic_store_n(&done,1,__ATOMIC_RELEASE);
      for(unsigned i=0;i<IRIS_HARTS;++i) if(!(mask&(1U<<i))) send_ipi(i);
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
  if(h==0) {
    if((fn==atomics || fn==lrsc) && atomic_counter!=(uint64_t)argument*IRIS_HARTS) ++failed;
    for(unsigned i=0;i<IRIS_HARTS;++i) if(mask&(1U<<i)) {
      result_t r=results[i]; unsigned pass=r.checksum==r.expected; if(!pass) ++failed;
      putstr("IRIS_REGION {\"case_id\":\""); putstr(id);
      putstr("\",\"region\":\"kernel\",\"hart\":"); putuint(i);
      putstr(",\"start_cycle\":"); putuint(r.start);
      putstr(",\"end_cycle\":"); putuint(r.end);
      putstr(",\"instret_delta\":"); putuint(r.instret);
      putstr(",\"checksum\":"); putuint(r.checksum);
      putstr(",\"expected_checksum\":"); putuint(r.expected);
      putstr(",\"pass\":"); putstr(pass?"true":"false"); putstr("}\n");
    }
  }
  barrier();
}

void benchmark_main(unsigned h) {
  if(h==0) for(unsigned i=0;i<32;++i) ones[i]=1;
  barrier();
  const unsigned all=(1U<<IRIS_HARTS)-1, compute=all&3;
  (void)compute;
  run("baseline.empty",empty,0,all,0,1);
  run("scalar.dep.256",dependent,256,all,769,1);
  run("scalar.dep.1024",dependent,1024,all,3073,1);
  run("scalar.branch.256",branches,256,all,512,1);
#ifndef IRIS_SMOKE
  run("memory.dram.4k.h1",stream,4096,1,2095104,0);
  run("memory.dram.4k.compute",stream,4096,compute,2095104,4096);
  run("memory.dram.1m.h1",stream,1048576,1,137438429184ULL,0);
  run("memory.pointer.4k",pointer_chase,4096,compute,0,0);
  run("memory.pointer.1m",pointer_chase,1048576,compute,65536,0);
  run("memory.tcm.4k",local_tcm,4096,compute,524800,0);
  run("memory.scratchpad.4k",scratchpad,4096,all,524800,0);
  run("multicore.atomic.256",atomics,256,all,256,0);
  run("multicore.lrsc.256",lrsc,256,all,256,0);
  run("multicore.barrier.16",sync_barrier,16,all,16,0);
  run("interrupt.ipi.8",ipi,8,all,8,0);
  run("interrupt.timer.2",timer,2,all,2,0);
  run("vector.e8.m1.64",vec_e8_m1,64,compute,2144,0);
  run("vector.e8.m1.256",vec_e8_m1,256,compute,96,0);
  run("vector.e8.m2.64",vec_e8_m2,64,compute,4288,0);
  run("vector.e32.m1.64",vec_e32_m1,64,compute,536,0);
  run("vector.e32.m2.64",vec_e32_m2,64,compute,1072,0);
  run("vme.int8.mm.16.h1",vme_mm,16,1,2048,0);
  run("vme.int8.mm.64.compute",vme_mm,64,compute,8192,0);
  if(IRIS_HARTS==3) run("functional.hart2.vme_refusal",refuse_vme,0,4,1,0);
#endif
  barrier();
  if(h==0) { putstr("IRIS_BATCH_DONE {\"failed\":"); putuint(failed); putstr("}\n"); finish(failed?1:0); }
  for(;;) __asm__ volatile("wfi");
}
