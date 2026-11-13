#include <zephyr/kernel.h>
#include "iris_uart_profile.h"
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/devicetree.h>
#include <stdint.h>
#include "task_setup.h"
#include "pipeline_config.h"

#define JOBS 3
static int8_t left[2][PIPE_WORKERS][PIPE_MAX_ROWS*PIPE_K] __aligned(16);
static int8_t right[2][PIPE_K*PIPE_N] __aligned(16);
static int32_t outputs[JOBS][PIPE_M*PIPE_N] __aligned(16);
static uint8_t workspace[PIPE_WORKERS][PIPE_WORKSPACE] __aligned(16);
static unsigned generation[2];
static struct k_thread workers[PIPE_WORKERS],producer;
K_THREAD_STACK_ARRAY_DEFINE(stacks,PIPE_WORKERS,8192);
K_THREAD_STACK_DEFINE(producer_stack,8192);
static struct k_sem work[PIPE_WORKERS];
K_SEM_DEFINE(started,0,PIPE_WORKERS);
K_SEM_DEFINE(completed,0,PIPE_WORKERS);
K_SEM_DEFINE(finished,0,PIPE_WORKERS+1);
static atomic_t active;
static struct {uint64_t begin,end,instret;unsigned hart;} samples[JOBS][PIPE_WORKERS];
static unsigned producer_overlap[JOBS];
static uint64_t producer_vector_checksum;
static unsigned hart(void){unsigned long x;__asm__ volatile("csrr %0,mhartid":"=r"(x));return x;}
static uint64_t cycles(void){uint64_t x;__asm__ volatile("csrr %0,mcycle":"=r"(x)::"memory");return x;}
static uint64_t retired(void){uint64_t x;__asm__ volatile("csrr %0,minstret":"=r"(x)::"memory");return x;}
static void fail(unsigned id,unsigned job,unsigned reason){printk("IRIS_COMPILER_FATAL {\"hart\":%u,\"worker\":%u,\"job\":%u,\"reason\":%u}\n",hart(),id,job,reason);k_panic();}
static void compute(void *arg,void *b,void *c){
  unsigned id=(uintptr_t)arg;(void)b;(void)c;
  if(hart()!=id||merlin_target_compute_task_setup())fail(id,0,1);
  for(unsigned job=0;job<JOBS;++job){
    k_sem_take(&work[id],K_FOREVER);unsigned buffer=job&1;
    if(generation[buffer]!=job+1)fail(id,job,2);
    atomic_or(&active,1u<<id);k_sem_give(&started);
    uint64_t r=retired();samples[job][id].begin=cycles();samples[job][id].hart=hart();
    int rc=pipeline_compute(id,outputs[job]+(PIPE_M*id/PIPE_WORKERS)*PIPE_N,left[buffer][id],right[buffer],workspace[id],sizeof(workspace[id]));
    samples[job][id].end=cycles();samples[job][id].instret=retired()-r;
    if(rc)fail(id,job,3);atomic_and(&active,~(1u<<id));k_sem_give(&completed);
  }
  k_sem_give(&finished);
}
static void prepare(unsigned job){
  unsigned buffer=job&1;
  for(unsigned k=0;k<PIPE_K;++k)for(unsigned j=0;j<PIPE_N;++j)right[buffer][k*PIPE_N+j]=(int8_t)(k*13+j*7+5+job*9);
  for(unsigned id=0;id<PIPE_WORKERS;++id){
    unsigned first=PIPE_M*id/PIPE_WORKERS,rows=PIPE_M*(id+1)/PIPE_WORKERS-first;
    for(unsigned i=0;i<rows;++i)for(unsigned k=0;k<PIPE_K;++k){
      unsigned pos=first+i;
#if PIPE_CONV
      unsigned oy=pos/8,ox=pos%8,fy=k/24,fx=(k/8)%3,channel=k%8;
      unsigned index=((oy+fy)*10+ox+fx)*8+channel;
      left[buffer][id][i*PIPE_K+k]=(int8_t)(index*17+3+job*5);
#else
      left[buffer][id][i*PIPE_K+k]=(int8_t)(pos*17+k*11+3+job*5);
#endif
    }
  }
  generation[buffer]=job+1;
}
static void produce(void *a,void *b,void *c){
  (void)a;(void)b;(void)c;
  if(hart()!=2||merlin_target_cpu_producer_setup())fail(2,0,4);
  prepare(0);uint64_t sum=14695981039346656037ULL;
  for(unsigned job=0;job<JOBS;++job){
    for(unsigned id=0;id<PIPE_WORKERS;++id)k_sem_give(&work[id]);
    for(unsigned id=0;id<PIPE_WORKERS;++id)k_sem_take(&started,K_FOREVER);
    producer_overlap[job]=(unsigned)atomic_get(&active);
    /* Fill the alternate input buffer while a compute worker is active. */
    if(job+1<JOBS)prepare(job+1);
    uint32_t in[8],out[8];for(unsigned n=0;n<8;++n)in[n]=job*8+n;
    __asm__ volatile("vsetivli zero,8,e32,m1,ta,ma\n\tvle32.v v0,(%0)\n\tvadd.vi v0,v0,7\n\tvse32.v v0,(%1)"::"r"(in),"r"(out):"v0","memory");
    for(unsigned n=0;n<8;++n){if(out[n]!=in[n]+7)fail(2,job,5);for(unsigned byte=0;byte<4;++byte)sum=(sum^((out[n]>>(byte*8))&255))*1099511628211ULL;}
    for(unsigned id=0;id<PIPE_WORKERS;++id)k_sem_take(&completed,K_FOREVER);
    /* Consume the completed output before reusing either input buffer. */
    for(unsigned i=0;i<PIPE_M*PIPE_N;++i)if(outputs[job][i]<-PIPE_K*16384||outputs[job][i]>PIPE_K*16384)fail(2,job,6);
  }
  if(!(producer_overlap[0]|producer_overlap[1]))fail(2,JOBS,7);
  producer_vector_checksum=sum;k_sem_give(&finished);
}
int main(void){
  iris_uart_profile_report();
  for(unsigned id=0;id<PIPE_WORKERS;++id){k_sem_init(&work[id],0,1);k_tid_t t=k_thread_create(&workers[id],stacks[id],K_THREAD_STACK_SIZEOF(stacks[id]),compute,(void *)(uintptr_t)id,NULL,NULL,5,K_FP_REGS,K_FOREVER);if(k_thread_cpu_pin(t,id))fail(id,0,8);k_thread_start(t);}
  k_tid_t t=k_thread_create(&producer,producer_stack,K_THREAD_STACK_SIZEOF(producer_stack),produce,NULL,NULL,NULL,5,K_FP_REGS,K_FOREVER);if(k_thread_cpu_pin(t,2))fail(2,0,9);k_thread_start(t);
  for(unsigned n=0;n<PIPE_WORKERS+1;++n)k_sem_take(&finished,K_FOREVER);
  for(unsigned job=0;job<JOBS;++job){
    printk("IRIS_COMPILER_RESULT {\"job\":%u,\"accumulator_u32\":[",job);
    for(unsigned i=0;i<PIPE_M*PIPE_N;++i)printk("%s%u",i?",":"",(uint32_t)outputs[job][i]);
    printk("],\"w8a8_f32_words\":[");
    for(unsigned i=0;i<PIPE_M*PIPE_N;++i){int64_t q=((int64_t)outputs[job][i]+512)>>10;if(q>127)q=127;if(q<-128)q=-128;union{float f;uint32_t u;}v;v.f=(float)q;printk("%s%u",i?",":"",v.u);}printk("]}\n");
    for(unsigned id=0;id<PIPE_WORKERS;++id)printk("IRIS_REGION {\"case_id\":\"zephyr.compiler.%s\",\"region\":\"job%u\",\"hart\":%u,\"role\":\"%s\",\"hart_mask\":%u,\"start_cycle\":%llu,\"end_cycle\":%llu,\"instret_delta\":%llu}\n",PIPE_OP,job,samples[job][id].hart,
#ifdef MERLIN_MATRIX_SCALAR_TILE
      "scalar.compute",
#else
      "vme.compute",
#endif
      (1u<<PIPE_WORKERS)-1,(unsigned long long)samples[job][id].begin,(unsigned long long)samples[job][id].end,(unsigned long long)samples[job][id].instret);
  }
  printk("IRIS_COMPILER_PRODUCER {\"hart\":2,\"jobs\":3,\"overlap_masks\":[%u,%u,%u],\"vector_checksum\":%llu,\"vme_refused\":true}\n",producer_overlap[0],producer_overlap[1],producer_overlap[2],(unsigned long long)producer_vector_checksum);
  printk("PASSED compiler Zephyr double-buffer pipeline\n");
  uintptr_t uart=DT_REG_ADDR(DT_CHOSEN(zephyr_console));sys_write32((sys_read32(uart+8)&~(0x1ffu<<16))|(1u<<16),uart+8);while(!(sys_read32(uart+0x14)&1))k_yield();k_sleep(K_MSEC(1));__asm__ volatile("fence rw,rw":::"memory");sys_reboot(SYS_REBOOT_COLD);return 0;
}
