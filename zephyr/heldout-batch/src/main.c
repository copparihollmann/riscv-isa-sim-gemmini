#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/sys/sys_io.h>
#include <zephyr/devicetree.h>
#include <stdint.h>
#include "task_setup.h"
#include "iris_uart_profile.h"
#include "batch_config.h"

#define M 64
#define N 64
#define KMAX 72
#define JOBS (3 * BATCH_TRIALS)
/* Full/compact deployment derivatives change only this retained ELF data byte. */
volatile const unsigned char iris_heldout_full_output=1;
static int8_t left[2][2][M*KMAX] __aligned(16);
static int8_t right[2][KMAX*N] __aligned(16);
static int32_t outputs[JOBS][M*N] __aligned(16);
static unsigned generation[2],phase,worker_count,kdim;
static struct k_thread workers[2],producer;
K_THREAD_STACK_ARRAY_DEFINE(stacks,2,8192);
K_THREAD_STACK_DEFINE(producer_stack,8192);
static struct k_sem work[2];
K_SEM_DEFINE(started,0,2);
K_SEM_DEFINE(completed,0,2);
K_SEM_DEFINE(finished,0,3);
static atomic_t active;
static struct {uint64_t begin,end,instret;unsigned hart;} samples[JOBS][2];
static unsigned overlap[JOBS];
static uint64_t producer_checksum,e2e_begin,e2e_end,e2e_retired;
static uint64_t e2e_mtime_begin,e2e_mtime_end;
static unsigned hart(void){unsigned long x;__asm__ volatile("csrr %0,mhartid":"=r"(x));return x;}
static uint64_t cycles(void){uint64_t x;__asm__ volatile("csrr %0,mcycle":"=r"(x)::"memory");return x;}
static uint64_t retired(void){uint64_t x;__asm__ volatile("csrr %0,minstret":"=r"(x)::"memory");return x;}
static unsigned op(void){return phase/4;}
static unsigned twin(void){return phase&1;}
static const char *opname(void){return op()?"conv2d":"gemm";}
static const char *kind(void){return twin()?"twin":"shipped";}
static void fail(unsigned job,unsigned reason){printk("IRIS_HELDOUT_FATAL {\"phase\":%u,\"hart\":%u,\"job\":%u,\"reason\":%u}\n",phase,hart(),job,reason);k_panic();}
static uint64_t output_hash(const int32_t *v,unsigned count){uint64_t h=14695981039346656037ULL;for(unsigned i=0;i<count;++i)for(unsigned b=0;b<4;++b)h=(h^(((uint32_t)v[i]>>(b*8))&255))*1099511628211ULL;return h;}
static uint32_t quant_word(int32_t x){int64_t q=((int64_t)x+512)>>10;if(q>127)q=127;if(q<-128)q=-128;union{float f;uint32_t u;}v;v.f=(float)q;return v.u;}
static uint64_t quant_hash(const int32_t *v,unsigned count){uint64_t h=14695981039346656037ULL;for(unsigned i=0;i<count;++i){uint32_t w=quant_word(v[i]);for(unsigned b=0;b<4;++b)h=(h^((w>>(b*8))&255))*1099511628211ULL;}return h;}
static void compute(void *arg,void *b,void *c){
  unsigned id=(uintptr_t)arg;(void)b;(void)c;
  if(hart()!=id||(!twin()&&merlin_target_compute_task_setup()))fail(0,1);
  for(unsigned job=0;job<JOBS;++job){
    k_sem_take(&work[id],K_FOREVER);unsigned buffer=job&1;
    if(generation[buffer]!=job+1)fail(job,2);
    atomic_or(&active,1u<<id);k_sem_give(&started);
    uint64_t r=retired();samples[job][id].begin=cycles();samples[job][id].hart=hart();
#ifndef IRIS_TEST_SKIP_KERNEL
    for(unsigned row=0;row<M/worker_count;row+=32){
      struct batch_memref2 a={left[buffer][id]+row*kdim,left[buffer][id]+row*kdim,0,{32,kdim},{kdim,1}};
      struct batch_memref2 bdesc={right[buffer],right[buffer],0,{kdim,N},{N,1}};
      int32_t *dst=outputs[job]+(M*id/worker_count+row)*N;
      struct batch_memref2 out={dst,dst,0,{32,N},{N,1}};
      batch_models[op()*2+twin()](&a,&bdesc,&out);
    }
#endif
    samples[job][id].end=cycles();samples[job][id].instret=retired()-r;
    atomic_and(&active,~(1u<<id));k_sem_give(&completed);
  }
  k_sem_give(&finished);
}
static void prepare(unsigned job){
  unsigned buffer=job&1,dataset=job%3;
  for(unsigned k=0;k<kdim;++k)for(unsigned j=0;j<N;++j)right[buffer][k*N+j]=(int8_t)(k*13+j*7+5+dataset*9);
  for(unsigned id=0;id<worker_count;++id)for(unsigned i=0;i<M/worker_count;++i)for(unsigned k=0;k<kdim;++k){
    unsigned pos=M*id/worker_count+i;
    if(op()){unsigned oy=pos/8,ox=pos%8,fy=k/24,fx=(k/8)%3,channel=k%8,index=((oy+fy)*10+ox+fx)*8+channel;left[buffer][id][i*kdim+k]=(int8_t)(index*17+3+dataset*5);}
    else left[buffer][id][i*kdim+k]=(int8_t)(pos*17+k*11+3+dataset*5);
  }
  generation[buffer]=job+1;
}
static void produce(void *a,void *b,void *c){
  (void)a;(void)b;(void)c;
  if(hart()!=2||merlin_target_cpu_producer_setup())fail(0,4);
  e2e_mtime_begin=sys_read64(DT_REG_ADDR_BY_NAME(DT_NODELABEL(mtimer),mtime));
  uint64_t initial=retired();e2e_begin=cycles();prepare(0);
  uint64_t sum=14695981039346656037ULL;
  for(unsigned job=0;job<JOBS;++job){
    for(unsigned id=0;id<worker_count;++id)k_sem_give(&work[id]);
    for(unsigned id=0;id<worker_count;++id)k_sem_take(&started,K_FOREVER);
    overlap[job]=(unsigned)atomic_get(&active);
    if(job+1<JOBS)prepare(job+1);
    uint32_t in[8],out[8];for(unsigned n=0;n<8;++n)in[n]=(job%3)*8+n;
    __asm__ volatile("vsetivli zero,8,e32,m1,ta,ma\n\tvle32.v v0,(%0)\n\tvadd.vi v0,v0,7\n\tvse32.v v0,(%1)"::"r"(in),"r"(out):"v0","memory");
    for(unsigned n=0;n<8;++n){if(out[n]!=in[n]+7)fail(job,5);for(unsigned byte=0;byte<4;++byte)sum=(sum^((out[n]>>(byte*8))&255))*1099511628211ULL;}
    for(unsigned id=0;id<worker_count;++id)k_sem_take(&completed,K_FOREVER);
    for(unsigned i=0;i<M*N;++i)if(outputs[job][i]<-(int)(kdim*16384)||outputs[job][i]>(int)(kdim*16384))fail(job,6);
  }
#ifndef IRIS_TEST_SKIP_KERNEL
  if(!(overlap[0]|overlap[1]))fail(JOBS,7);
#endif
  producer_checksum=sum;e2e_end=cycles();e2e_retired=retired()-initial;
  e2e_mtime_end=sys_read64(DT_REG_ADDR_BY_NAME(DT_NODELABEL(mtimer),mtime));k_sem_give(&finished);
}
static void print_phase(void){
  printk("IRIS_HELDOUT_PHASE {\"phase\":%u,\"op\":\"%s\",\"workers\":%u,\"kind\":\"%s\"}\n",phase,opname(),worker_count,kind());
  printk("IRIS_REGION {\"case_id\":\"heldout.batch.%s.h%u.%s.e2e\",\"parent_case_id\":\"merlin.zephyr.%s.%ucompute\",\"region\":\"pipeline_end_to_end\",\"hart\":2,\"role\":\"pipeline.end_to_end\",\"scope\":\"producer_entry_to_all_outputs_consumed\",\"start_cycle\":%llu,\"end_cycle\":%llu,\"instret_delta\":%llu,\"checksum\":%llu,\"pass\":true}\n",opname(),worker_count,kind(),opname(),worker_count,(unsigned long long)e2e_begin,(unsigned long long)e2e_end,(unsigned long long)e2e_retired,(unsigned long long)producer_checksum);
  printk("IRIS_HELDOUT_ELAPSED {\"phase\":%u,\"hart\":2,\"source\":\"CLINT.mtime.MMIO\",\"start_mtime\":%llu,\"end_mtime\":%llu,\"timebase_hz\":%u,\"core_cycles_per_tick\":%u,\"scope\":\"producer_entry_to_all_outputs_consumed\"}\n",phase,(unsigned long long)e2e_mtime_begin,(unsigned long long)e2e_mtime_end,CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC,CONFIG_RTC_CLOCK_DIVIDER_VALUE);
  for(unsigned job=0;job<JOBS;++job){
    if(iris_heldout_full_output){
      printk("IRIS_HELDOUT_RESULT {\"phase\":%u,\"job\":%u,\"accumulator_u32\":[",phase,job);
      for(unsigned i=0;i<M*N;++i)printk("%s%u",i?",":"",(uint32_t)outputs[job][i]);
      printk("],\"w8a8_f32_words\":[");for(unsigned i=0;i<M*N;++i)printk("%s%u",i?",":"",quant_word(outputs[job][i]));printk("]}\n");
    }else{
      printk("IRIS_HELDOUT_RESULT {\"phase\":%u,\"job\":%u,\"encoding\":\"checked-word-hashes-v1\",\"word_count\":4096,\"accumulator_checksum\":%llu,\"w8a8_checksum\":%llu,\"mismatching_int32_words\":0,\"mismatching_w8a8_words\":0}\n",phase,job,(unsigned long long)output_hash(outputs[job],M*N),(unsigned long long)quant_hash(outputs[job],M*N));
    }
    for(unsigned id=0;id<worker_count;++id)printk("IRIS_REGION {\"case_id\":\"heldout.batch.%s.h%u.%s.job%u\",\"parent_case_id\":\"merlin.zephyr.%s.%ucompute\",\"region\":\"job%u\",\"hart\":%u,\"trial_id\":%u,\"dataset_id\":%u,\"role\":\"%s\",\"hart_mask\":%u,\"start_cycle\":%llu,\"end_cycle\":%llu,\"instret_delta\":%llu,\"checksum\":%llu,\"pass\":true}\n",opname(),worker_count,kind(),job,opname(),worker_count,job,samples[job][id].hart,job/3,job%3,twin()?"scalar.compute":"vme.compute",(1u<<worker_count)-1,(unsigned long long)samples[job][id].begin,(unsigned long long)samples[job][id].end,(unsigned long long)samples[job][id].instret,(unsigned long long)output_hash(outputs[job]+(M*id/worker_count)*N,M/worker_count*N));
  }
  printk("IRIS_HELDOUT_PRODUCER {\"phase\":%u,\"hart\":2,\"jobs\":%u,\"overlap_masks\":[",phase,JOBS);for(unsigned job=0;job<JOBS;++job)printk("%s%u",job?",":"",overlap[job]);printk("],\"vector_checksum\":%llu,\"vme_refused\":true}\n",(unsigned long long)producer_checksum);
}
int main(void){
  iris_uart_profile_report();
  for(phase=0;phase<8;++phase){
    worker_count=1+(phase%4)/2;kdim=op()?72:64;atomic_set(&active,0);generation[0]=generation[1]=0;
    for(unsigned job=0;job<JOBS;++job)for(unsigned i=0;i<M*N;++i)((volatile uint32_t*)outputs[job])[i]=batch_expected[op()][job%3][i]^0xffffffffu;
    for(unsigned id=0;id<worker_count;++id){k_sem_init(&work[id],0,1);k_tid_t t=k_thread_create(&workers[id],stacks[id],K_THREAD_STACK_SIZEOF(stacks[id]),compute,(void*)(uintptr_t)id,NULL,NULL,5,K_FP_REGS,K_FOREVER);if(k_thread_cpu_pin(t,id))fail(0,8);k_thread_start(t);}
    k_tid_t t=k_thread_create(&producer,producer_stack,K_THREAD_STACK_SIZEOF(producer_stack),produce,NULL,NULL,NULL,5,K_FP_REGS,K_FOREVER);if(k_thread_cpu_pin(t,2))fail(0,9);k_thread_start(t);
    for(unsigned i=0;i<worker_count+1;++i)k_sem_take(&finished,K_FOREVER);
    for(unsigned id=0;id<worker_count;++id)if(k_thread_join(&workers[id],K_FOREVER))fail(0,10);
    if(k_thread_join(&producer,K_FOREVER))fail(0,11);
    for(unsigned job=0;job<JOBS;++job)for(unsigned i=0;i<M*N;++i){
      if((uint32_t)outputs[job][i]!=batch_expected[op()][job%3][i])fail(job,12);
      if(quant_word(outputs[job][i])!=batch_expected_w8[op()][job%3][i])fail(job,13);
    }
    print_phase();
  }
  printk("IRIS_BATCH_DONE {\"failed\":0,\"cases\":128,\"regions\":188,\"trials\":5}\n");
  uintptr_t uart=DT_REG_ADDR(DT_CHOSEN(zephyr_console));sys_write32((sys_read32(uart+8)&~(0x1ffu<<16))|(1u<<16),uart+8);while(!(sys_read32(uart+0x14)&1))k_yield();k_sleep(K_MSEC(1));__asm__ volatile("fence rw,rw":::"memory");sys_reboot(SYS_REBOOT_COLD);return 0;
}
