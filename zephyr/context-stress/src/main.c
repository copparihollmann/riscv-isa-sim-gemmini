#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/devicetree.h>
#include <stdint.h>
#include <stddef.h>

#define THREADS 6
#define ROUNDS 12
struct context {
  uint64_t f[32];
  uint8_t v[1024];
  uint64_t vstart,vl,vtype,vcsr,vlenb,fcsr;
} __aligned(64);
BUILD_ASSERT(offsetof(struct context,v)==256);
BUILD_ASSERT(offsetof(struct context,vstart)==1280);
BUILD_ASSERT(offsetof(struct context,fcsr)==1320);
extern void context_load(const struct context *);
extern void context_store(struct context *);
static struct context expected[THREADS],observed[THREADS];
static struct k_thread workers[THREADS];
K_THREAD_STACK_ARRAY_DEFINE(stacks,THREADS,8192);
static struct k_sem enter[THREADS],resume[THREADS];
K_SEM_DEFINE(finished,0,THREADS);
static struct { uint64_t checksum,checks,irq_ticks,start,end;unsigned hart; } results[THREADS];
static unsigned hart(void) { unsigned long x;__asm__ volatile("csrr %0,mhartid":"=r"(x));return x; }
static uint64_t cycles(void) { uint64_t x;__asm__ volatile("csrr %0,mcycle":"=r"(x)::"memory");return x; }
static uint64_t hash(uint64_t state,const void *pointer,size_t bytes) {
  const uint8_t *p=pointer;for(size_t i=0;i<bytes;++i) state=(state^p[i])*1099511628211ULL;return state;
}
static void fill(struct context *state,unsigned id,unsigned round) {
  static const uint64_t types[THREADS]={0xc0,0xc9,0xd0,0xd9,0xc2,0xd1};
  static const uint64_t lengths[THREADS]={17,15,7,5,31,13};
  for(unsigned i=0;i<32;++i) state->f[i]=0x3ff0000000000000ULL|((uint64_t)(id+1)<<40)|((uint64_t)(round+1)<<24)|((uint64_t)i<<12);
  for(unsigned i=0;i<1024;++i) state->v[i]=(uint8_t)(id*37+round*13+i*7);
  state->vstart=id%3;state->vl=lengths[id];state->vtype=types[id];
  state->vcsr=((id%4)<<1)|(id&1);state->vlenb=32;state->fcsr=((id%5)<<5)|((id*3+round)&31);
}
static void fail(unsigned id,unsigned round,unsigned field) {
  printk("IRIS_CONTEXT_FATAL {\"thread\":%u,\"hart\":%u,\"round\":%u,\"field\":%u}\n",id,hart(),round,field);
  k_panic();
}
static void ieee(unsigned id,unsigned round) {
  uint64_t d;uint32_t s;unsigned long h;
  __asm__ volatile("fmv.d.x ft0,%1\n\tfmv.d.x ft1,%2\n\tfadd.d ft2,ft0,ft1\n\tfmv.x.d %0,ft2"
    :"=r"(d):"r"(0x3ff0000000000000ULL),"r"(0x4000000000000000ULL):"ft0","ft1","ft2");
  __asm__ volatile("fmv.w.x ft0,%1\n\tfmv.w.x ft1,%2\n\tfadd.s ft2,ft0,ft1\n\tfmv.x.w %0,ft2"
    :"=r"(s):"r"(0x3f800000UL),"r"(0x40000000UL):"ft0","ft1","ft2");
  __asm__ volatile(".option push\n\t.option arch,+zfh\n\tfmv.h.x ft0,%1\n\tfmv.h.x ft1,%2\n\tfadd.h ft2,ft0,ft1\n\tfmv.x.h %0,ft2\n\t.option pop"
    :"=r"(h):"r"(0x3c00UL),"r"(0x4000UL):"ft0","ft1","ft2");
  if(d!=0x4008000000000000ULL || s!=0x40400000U || (h&0xffff)!=0x4200) fail(id,round,99);
}
static void worker(void *a,void *b,void *c) {
  unsigned id=(uintptr_t)a,other=id^1;(void)b;(void)c;
  if(hart()!=id/2) fail(id,0,100);
  uint64_t sum=14695981039346656037ULL,ticks=0;
  results[id].start=cycles();results[id].hart=hart();
  for(unsigned round=0;round<ROUNDS;++round) {
    k_sem_take(&enter[id],K_FOREVER);
    fill(&expected[id],id,round);
    context_load(&expected[id]);
    if(!(id&1)) k_sem_give(&enter[other]);else k_sem_give(&resume[other]);
    int64_t before=k_uptime_get();k_busy_wait(2000);ticks+=(uint64_t)(k_uptime_get()-before);
    k_sem_take(&resume[id],K_FOREVER);
    context_store(&observed[id]);
    const uint8_t *want=(const uint8_t *)&expected[id],*got=(const uint8_t *)&observed[id];
    for(unsigned i=0;i<1328;++i) if(want[i]!=got[i]) fail(id,round,i);
    sum=hash(sum,&observed[id],1328);ieee(id,round);
    if(!(id&1)) k_sem_give(&resume[other]);else k_sem_give(&enter[other]);
  }
  results[id].checksum=sum;results[id].checks=ROUNDS;results[id].irq_ticks=ticks;results[id].end=cycles();
  k_sem_give(&finished);
}
int main(void) {
  for(unsigned id=0;id<THREADS;++id) {
    k_sem_init(&enter[id],!(id&1),1);k_sem_init(&resume[id],0,1);
    k_tid_t t=k_thread_create(&workers[id],stacks[id],K_THREAD_STACK_SIZEOF(stacks[id]),worker,(void *)(uintptr_t)id,NULL,NULL,5,K_FP_REGS,K_FOREVER);
    if(k_thread_cpu_pin(t,id/2)) fail(id,0,101);k_thread_start(t);
  }
  for(unsigned id=0;id<THREADS;++id) k_sem_take(&finished,K_FOREVER);
  for(unsigned id=0;id<THREADS;++id) {
    printk("IRIS_CONTEXT {\"thread\":%u,\"hart\":%u,\"rounds\":%llu,\"checksum\":%llu,\"timer_ticks\":%llu,\"start_cycle\":%llu,\"end_cycle\":%llu}\n",id,results[id].hart,results[id].checks,results[id].checksum,results[id].irq_ticks,results[id].start,results[id].end);
    if(!results[id].irq_ticks) fail(id,ROUNDS,102);
  }
  printk("PASSED six competing RVV/IEEE contexts\n");
  uintptr_t uart=DT_REG_ADDR(DT_CHOSEN(zephyr_console));
  sys_write32((sys_read32(uart+8)&~(0x1ffu<<16))|(1u<<16),uart+8);
  while(!(sys_read32(uart+0x14)&1)) k_yield();k_sleep(K_MSEC(1));
  __asm__ volatile("fence rw,rw":::"memory");sys_reboot(SYS_REBOOT_COLD);return 0;
}
