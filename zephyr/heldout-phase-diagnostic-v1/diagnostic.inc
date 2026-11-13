#include <zephyr/drivers/htif.h>
#ifndef IRIS_DIAG_TIMEOUT_MS
#define IRIS_DIAG_TIMEOUT_MS 5000
#endif
static volatile uint64_t diag_mailbox[3] __aligned(64);
static uint32_t diag_sequence[3];
static atomic_t diag_complete;
static struct k_thread diag_thread;
K_THREAD_STACK_DEFINE(diag_stack,4096);
K_SEM_DEFINE(diag_joined,0,1);
static void diag_mark(unsigned channel,unsigned stage,unsigned job){
  uint64_t value=((uint64_t)++diag_sequence[channel]<<32)|((uint64_t)hart()<<28)|((uint64_t)(phase&15)<<24)|((uint64_t)(job&255)<<16)|stage;
  __atomic_store_n(&diag_mailbox[channel],value,__ATOMIC_RELEASE);
}
static uint64_t diag_time(void){return sys_read64(DT_REG_ADDR_BY_NAME(DT_NODELABEL(mtimer),mtime));}
static void diag_watchdog(void*a,void*b,void*c){
  (void)a;(void)b;(void)c;uint64_t prior[3]={0},last=diag_time();
  printk("IRIS_DIAG_WATCHDOG {\"hart\":%u,\"no_progress_ms\":%u}\n",hart(),IRIS_DIAG_TIMEOUT_MS);
  for(;;){if(atomic_get(&diag_complete))break;k_sleep(K_MSEC(25));unsigned changed=0;uint64_t now[3];for(unsigned i=0;i<3;++i){now[i]=__atomic_load_n(&diag_mailbox[i],__ATOMIC_ACQUIRE);changed|=now[i]!=prior[i];prior[i]=now[i];}uint64_t t=diag_time();if(changed)last=t;
#ifdef IRIS_DIAG_FORCE_STALL
    if(((now[0]>>24)&15)!=1){last=t;continue;}
#endif
    if(t-last>(uint64_t)IRIS_DIAG_TIMEOUT_MS*(CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC/1000)){
      printk("IRIS_DIAG_TIMEOUT {\"watchdog_hart\":%u,\"main\":%llu,\"worker\":%llu,\"producer\":%llu,\"diagnostic_not_normal_completion\":true}\n",hart(),(unsigned long long)now[0],(unsigned long long)now[1],(unsigned long long)now[2]);
      uintptr_t uart=DT_REG_ADDR(DT_CHOSEN(zephyr_console));sys_write32((sys_read32(uart+8)&~(0x1ffu<<16))|(1u<<16),uart+8);while(!(sys_read32(uart+0x14)&1)){}uint64_t edges=65536ULL+11ULL*((sys_read32(uart+0x18)&65535)+1),ticks=(edges+999)/1000+1,begin=diag_time();while(diag_time()-begin<ticks){}__asm__ volatile("fence rw,rw":::"memory");tohost=3;__asm__ volatile("fence rw,rw":::"memory");for(;;)__asm__ volatile("wfi");
    }
  }k_sem_give(&diag_joined);
}
