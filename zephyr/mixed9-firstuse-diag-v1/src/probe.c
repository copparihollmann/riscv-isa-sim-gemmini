#include <zephyr/kernel.h>
#include <zephyr/kernel_structs.h>
#include <zephyr/drivers/htif.h>
#include <stdint.h>
#include "probe.h"
#define BASE 0x58001e000UL
#define UART ((volatile uint32_t*)0x10020000UL)
#define MTIME (*(volatile uint64_t*)0x0200bff8UL)
#ifndef IRIS_FIRSTUSE_TIMEOUT_MS
#define IRIS_FIRSTUSE_TIMEOUT_MS 5000
#endif
struct record {uint64_t begin,stage,iteration,physical,logical,worker,pin,status,mie,mip,cycle,end,pad[4];};
struct control {uint64_t ready,done[3];};
#define CONTROL ((volatile struct control*)(BASE+0x1000))
static unsigned long hart(void){unsigned long x;__asm__ volatile("csrr %0,mhartid":"=r"(x));return x;}
static struct _cpu* cpu(void){struct _cpu*x;__asm__ volatile("csrr %0,mscratch":"=r"(x));return x;}
static volatile struct record* slot(unsigned h){return(volatile struct record*)(BASE+(uintptr_t)h*128);}
/* Last-recorded source points, not a coherent snapshot or current PC. No hot
 * FENCE/AMO/FP/RVV and no OS/lock/console call: compiler barriers only. */
__attribute__((noinline)) void iris_probe_stamp(unsigned worker,unsigned pin,unsigned stage,unsigned iteration){
 unsigned long h=hart();if(h>2)return;volatile struct record*p=slot(h);uint64_t seq=(p->end+2)&~1ULL;p->begin=seq|1;__asm__ volatile("":::"memory");
 p->stage=stage;p->iteration=iteration;p->physical=h;p->logical=cpu()->id;p->worker=worker;p->pin=pin;
 uint64_t x;__asm__ volatile("csrr %0,mstatus":"=r"(x));p->status=x;__asm__ volatile("csrr %0,mie":"=r"(x));p->mie=x;__asm__ volatile("csrr %0,mip":"=r"(x));p->mip=x;__asm__ volatile("csrr %0,mcycle":"=r"(x));p->cycle=x;
 __asm__ volatile("":::"memory");p->end=seq;p->begin=seq;
}
void iris_probe_init(void){for(unsigned i=0;i<0x1200/8;++i)((volatile uint64_t*)BASE)[i]=0;__asm__ volatile("fence rw,rw":::"memory");}
void iris_probe_arm(void){CONTROL->ready=0;CONTROL->done[0]=CONTROL->done[1]=0;__asm__ volatile("fence rw,rw":::"memory");}
unsigned iris_probe_ready(void){return CONTROL->ready==1;}
void iris_probe_done(unsigned h){if(h<2)CONTROL->done[h]=1;}
static void ch(char c){while(UART[0]&0x80000000U){}UART[0]=(unsigned char)c;}
static void text(const char*s){while(*s)ch(*s++);}
static void number(uint64_t x){char b[21];unsigned n=0;do{b[n++]=(char)('0'+x%10);x/=10;}while(x);while(n)ch(b[--n]);}
static void field(const char*k,uint64_t x){text(k);number(x);}
static void dump(void){
 for(unsigned h=0;h<3;++h){volatile struct record*p=slot(h);uint64_t begin=p->begin,stage=p->stage,it=p->iteration,physical=p->physical,logical=p->logical,worker=p->worker,pin=p->pin,status=p->status,mie=p->mie,mip=p->mip,cycle=p->cycle,end=p->end;
  text("IRIS_FIRSTUSE_SNAPSHOT {");field("\"slot\":",h);field(",\"begin\":",begin);field(",\"end\":",end);text(",\"stable_sequence_observed\":");text(begin==end&&!(begin&1)?"true":"false");text(",\"metadata_race_possible\":true,\"current_PC_or_state_claimed\":false");field(",\"stage\":",stage);field(",\"iteration\":",it);field(",\"physical_hart\":",physical);field(",\"logical_cpu\":",logical);field(",\"worker\":",worker);field(",\"pin\":",pin);field(",\"last_recorded_mstatus\":",status);field(",\"last_recorded_mie\":",mie);field(",\"last_recorded_mip\":",mip);field(",\"last_recorded_mcycle\":",cycle);text("}\n");
 }
}
/* Sole timeout writer: main cannot reach its normal HTIF path until this
 * observer returns/gives finished, which it never does on failure. Workers
 * never use HTIF; chosen console is SiFive. No global IRQ lock is acquired. */
static __attribute__((noreturn)) void fail_exit(void){
 UART[2]=(UART[2]&~(0x1ffU<<16))|(1U<<16);while(!(UART[5]&1)){}
 uint64_t edges=65536ULL+11ULL*((UART[6]&65535U)+1),ticks=(edges+999)/1000+1,start=MTIME;while(MTIME-start<ticks){}
 start=MTIME;while(tohost&&MTIME-start<5000){if(fromhost)fromhost=0;}
 if(!tohost){__asm__ volatile("fence rw,rw":::"memory");tohost=3;__asm__ volatile("fence rw,rw":::"memory");}
 for(;;)__asm__ volatile("wfi");
}
void iris_probe_observe(unsigned worker,unsigned pin){
 iris_probe_stamp(worker,pin,1000,0);text("IRIS_FIRSTUSE_READY {");field("\"physical_hart\":",hart());field(",\"logical_cpu\":",cpu()->id);field(",\"worker\":",worker);field(",\"pin\":",pin);field(",\"timeout_ms\":",IRIS_FIRSTUSE_TIMEOUT_MS);text(",\"hart2_scalar_only\":true}\n");
 uint64_t begin=MTIME;CONTROL->ready=1;
 while(!(CONTROL->done[0]&&CONTROL->done[1])){
  if(MTIME-begin>=(uint64_t)IRIS_FIRSTUSE_TIMEOUT_MS*500){text("IRIS_FIRSTUSE_TIMEOUT {");field("\"observer_hart\":",hart());field(",\"timeout_ms\":",IRIS_FIRSTUSE_TIMEOUT_MS);field(",\"done0\":",CONTROL->done[0]);field(",\"done1\":",CONTROL->done[1]);text(",\"normal_completion\":false,\"exit_code_requested\":1}\n");dump();fail_exit();}
 }
 iris_probe_stamp(worker,pin,1001,0);dump();text("IRIS_FIRSTUSE_OBSERVER_DONE {\"physical_hart\":2,\"done0\":1,\"done1\":1}\n");
}
