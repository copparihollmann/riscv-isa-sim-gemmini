#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/devicetree.h>
#include <stdint.h>
#include "iris_uart_profile.h"
#if !defined(__riscv) || __riscv_xlen != 64
#error "This profiling app requires an RV64 Iris board and guest-visible mcycle"
#endif
#ifdef CONFIG_IRIS_BENCH_VME
#ifndef CONFIG_RISCV_IRIS_VME_CONTEXT
#error "Mixed VME app requires the explicit Iris Zephyr context extension"
#endif
#include <zephyr/arch/riscv/iris_vme.h>
#include "vme.h"
#endif

#define WORKERS CONFIG_IRIS_BENCH_WORKERS
BUILD_ASSERT(__builtin_popcount(CONFIG_IRIS_BENCH_HART_MASK) == WORKERS,
             "Worker count must match the selected hart mask");
BUILD_ASSERT((CONFIG_IRIS_BENCH_HART_MASK >> CONFIG_MP_MAX_NUM_CPUS) == 0,
             "Board must enable every selected CPU index");
K_THREAD_STACK_ARRAY_DEFINE(worker_stacks, WORKERS, 4096);
static struct k_thread workers[WORKERS];
static struct k_sem start_gates[WORKERS];
K_SEM_DEFINE(finished,0,WORKERS);
K_MUTEX_DEFINE(shared_lock);
static unsigned locked_rows;
static unsigned operation;
static unsigned worker_cpus[WORKERS];
static uint32_t outputs[WORKERS][64] __aligned(64);
static volatile int8_t matrix_a[16*16],matrix_b[16*16];
#ifdef CONFIG_IRIS_BENCH_VME
static uint8_t ones[32] __aligned(64);
#endif
struct sample { uint64_t start,end,instret,checksum,hart; };
static struct sample samples[WORKERS] __aligned(64);
static inline uint64_t rdcycle(void) { uint64_t x; __asm__ volatile("csrr %0,mcycle":"=r"(x)::"memory"); return x; }
static inline uint64_t rdret(void) { uint64_t x; __asm__ volatile("csrr %0,minstret":"=r"(x)::"memory"); return x; }
static inline unsigned hart(void) { unsigned long x; __asm__ volatile("csrr %0,mhartid":"=r"(x)); return x; }

static uint64_t gemm(unsigned worker) {
  uint64_t sum=0;
  /* Volatile inputs keep the compiler from replacing this with constants. */
  for(unsigned row=worker;row<16;row+=WORKERS) {
    for(unsigned col=0;col<16;++col) {
      int32_t acc=0;
      for(unsigned k=0;k<16;++k) acc+=(int32_t)matrix_a[row*16+k]*matrix_b[k*16+col];
      sum+=acc;
    }
    k_mutex_lock(&shared_lock,K_FOREVER); ++locked_rows; k_mutex_unlock(&shared_lock);
    k_yield();
  }
  return sum;
}
static uint64_t conv2d(unsigned worker) {
  uint64_t sum=0;
  volatile int8_t input[8*8],weights[9];
  for(unsigned i=0;i<64;++i) input[i]=1;
  for(unsigned i=0;i<9;++i) weights[i]=1;
  for(unsigned row=worker;row<6;row+=WORKERS) {
    for(unsigned col=0;col<6;++col) {
      int32_t acc=0;
      for(unsigned r=0;r<3;++r) for(unsigned c=0;c<3;++c) acc+=input[(row+r)*8+col+c]*weights[r*3+c];
      sum+=acc;
    }
    k_mutex_lock(&shared_lock,K_FOREVER); ++locked_rows; k_mutex_unlock(&shared_lock);
    k_sleep(K_MSEC(1));
  }
  return sum;
}
#ifdef CONFIG_IRIS_BENCH_VME
static uint64_t vme_context(unsigned worker) {
  vme_vsettnt_e8w4(32); vme_vsettm(32); vme_vsettk(1); VME_VTZERO(0);
  __asm__ volatile("vle8.v v8,(%0)\n\tvle8.v v16,(%0)"::"r"(ones):"memory");
  for(unsigned i=0;i<32;++i) { VME_MM_U_U(0,8,16); k_yield(); }
  vme_vsettnt_e32w1(32); VME_VTMV_V_T(24,vme_tss(0,VME_TSS_ROW,0));
  __asm__ volatile("vse32.v v24,(%0)\n\tfence rw,rw"::"r"(outputs[worker]):"memory");
  uint64_t sum=0; for(unsigned i=0;i<32;++i) sum+=outputs[worker][i]; return sum;
}
static uint64_t vector_copy_context(unsigned worker) {
  uint64_t sum=0;
  for(unsigned iteration=0;iteration<32;++iteration) {
    __asm__ volatile("vsetvli zero,%1,e8,m1,ta,ma\n\tvle8.v v8,(%0)"::"r"(ones),"r"((uintptr_t)32):"memory");
    k_yield();
    __asm__ volatile("vse8.v v8,(%0)\n\tfence rw,rw"::"r"(outputs[worker]):"memory");
    for(unsigned i=0;i<32;++i) sum+=((uint8_t *)outputs[worker])[i];
  }
  return sum;
}
#endif
static void worker(void *a,void *b,void *c) {
  unsigned index=(uintptr_t)a; (void)b; (void)c;
  for(;;) {
    k_sem_take(&start_gates[index],K_FOREVER);
    unsigned actual=hart();
    if(actual != worker_cpus[index] || actual>2) {
      printk("IRIS_FATAL {\"reason\":\"CPU index to hart mapping mismatch\",\"hart\":%u,\"cpu\":%u}\n",actual,worker_cpus[index]);
      k_panic();
    }
#ifdef CONFIG_IRIS_BENCH_VME
    if(operation==2 && actual<2) {
      int err=iris_vme_enable();
      if(err) {printk("IRIS_FATAL {\"reason\":\"VME ownership setup failed\",\"hart\":%u,\"errno\":%d}\n",actual,err);k_panic();}
    }
#endif
    uint64_t begin=rdcycle(),ret=rdret(),sum;
    if(operation==0) sum=gemm(index);
    else if(operation==1) sum=conv2d(index);
#ifdef CONFIG_IRIS_BENCH_VME
    else sum=actual<2?vme_context(index):vector_copy_context(index);
#else
    else { k_panic(); sum=0; }
#endif
    uint64_t lastret=rdret(),end=rdcycle();
    samples[index]=(struct sample){begin,end,lastret-ret,sum,actual};
    k_sem_give(&finished);
  }
}
int main(void) {
  iris_uart_profile_report();
  (void)outputs;
  for(unsigned i=0;i<256;++i) matrix_a[i]=matrix_b[i]=1;
#ifdef CONFIG_IRIS_BENCH_VME
  for(unsigned i=0;i<32;++i) ones[i]=1;
#endif
  for(unsigned i=0;i<WORKERS;++i) {
    unsigned cpu=0,ordinal=0;
    for(;cpu<3;++cpu) if(CONFIG_IRIS_BENCH_HART_MASK & (1u<<cpu)) {
      if(ordinal++==i) break;
    }
    worker_cpus[i]=cpu;
    k_sem_init(&start_gates[i],0,1);
    k_tid_t thread=k_thread_create(&workers[i],worker_stacks[i],K_THREAD_STACK_SIZEOF(worker_stacks[i]),worker,(void *)(uintptr_t)i,NULL,NULL,5,0,K_FOREVER);
    int err=k_thread_cpu_pin(thread,cpu);
    if(err) { printk("IRIS_FATAL {\"reason\":\"CPU pin failed\",\"errno\":%d}\n",err); k_panic(); }
    k_thread_start(thread);
  }
  unsigned cases=2;
#ifdef CONFIG_IRIS_BENCH_VME
  cases=3;
#endif
  unsigned failed=0;
  for(operation=0;operation<cases;++operation) {
    locked_rows=0;
    for(unsigned i=0;i<WORKERS;++i) k_sem_give(&start_gates[i]);
    for(unsigned i=0;i<WORKERS;++i) k_sem_take(&finished,K_FOREVER);
    uint64_t total=0;
    const char *name=operation==0?"zephyr.gemm16":operation==1?"zephyr.conv2d8":"zephyr.vme.yield";
    for(unsigned i=0;i<WORKERS;++i) {
      struct sample s=samples[i]; total+=s.checksum;
      const char *role=operation<2?"scalar.compute":s.hart<2?"vme.compute":"vector.copy";
      printk("IRIS_REGION {\"case_id\":\"%s\",\"region\":\"kernel\",\"hart\":%llu,\"role\":\"%s\",\"hart_mask\":%u,\"start_cycle\":%llu,\"end_cycle\":%llu,\"instret_delta\":%llu,\"checksum\":%llu}\n",name,(unsigned long long)s.hart,role,CONFIG_IRIS_BENCH_HART_MASK,(unsigned long long)s.start,(unsigned long long)s.end,(unsigned long long)s.instret,(unsigned long long)s.checksum);
    }
    uint64_t expected=operation==0?4096:operation==1?324:1024*WORKERS;
    if(total!=expected || (operation<2 && locked_rows!=(operation==0?16:6))) ++failed;
  }
  printk("IRIS_BATCH_DONE {\"failed\":%u}\n",failed);
  if(failed) k_panic();
#ifdef CONFIG_IRIS_BENCH_EXIT_ON_COMPLETION
  /* The real UART's watermark can report FIFO empty. The final frame may
   * still be shifting; one 1-ms tick exceeds a 115200-baud character. */
#if DT_NODE_HAS_COMPAT(DT_CHOSEN(zephyr_console), sifive_uart0)
  uintptr_t uart=DT_REG_ADDR(DT_CHOSEN(zephyr_console));
  uint32_t txctrl=sys_read32(uart+8);
  sys_write32((txctrl & ~(0x1ffu<<16)) | (1u<<16),uart+8);
  while(!(sys_read32(uart+0x14)&1)) k_yield();
  k_sleep(K_MSEC(1));
#endif
  __asm__ volatile("fence rw,rw" ::: "memory");
  sys_reboot(SYS_REBOOT_COLD);
#endif
  return 0;
}
