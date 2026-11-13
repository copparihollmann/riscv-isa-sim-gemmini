#include <zephyr/kernel.h>
#include <zephyr/kernel_structs.h>
#include <zephyr/arch/riscv/iris_flush_frontier.h>
#include <zephyr/drivers/htif.h>
#include <stdint.h>
#define BASE 0x58001e000UL
#define UART 0x10020000UL
#define MTIME (*(volatile uint64_t *)0x0200bff8UL)
#define CMP1 (*(volatile uint64_t *)0x02004008UL)
#define CONTROL ((volatile uint64_t *)(BASE+0x1c00))
struct frontier {uint64_t begin,stage,owner,current,peer,status,mie,mip,cycle,time,end,pad[5];};
static volatile unsigned ready;
static unsigned long hart(void){unsigned long h;__asm__ volatile("csrr %0,mhartid":"=r"(h));return h;}
/* MSCRATCH is established per-hart by source SMP init; no mobile-CPU assertion or new IRQ lock. Metadata is best-effort if preempted. */
static struct _cpu *raw_cpu(void){struct _cpu*c;__asm__ volatile("csrr %0,mscratch":"=r"(c));return c;}
static uint64_t read_status(void){uint64_t x;__asm__ volatile("csrr %0,mstatus":"=r"(x));return x;}
static uint64_t read_mie(void){uint64_t x;__asm__ volatile("csrr %0,mie":"=r"(x));return x;}
static uint64_t read_mip(void){uint64_t x;__asm__ volatile("csrr %0,mip":"=r"(x));return x;}
static uint64_t read_cycle(void){uint64_t x;__asm__ volatile("csrr %0,mcycle":"=r"(x));return x;}
static volatile struct frontier *slot(unsigned i){return(volatile struct frontier *)(BASE+(uintptr_t)i*256);}
/* NO hardware fence/AMO/FP/vector here: metadata can race or be observed incompletely. */
static __attribute__((noinline,optimize("no-tree-vectorize","no-tree-slp-vectorize"))) void record(unsigned i,uint64_t stage,uintptr_t owner,uintptr_t current,uintptr_t peer){
 volatile struct frontier*p=slot(i);uint64_t seq=(p->end+2)&~1ULL;p->begin=seq|1;__asm__ volatile("":::"memory");
 p->stage=stage;p->owner=owner;p->current=current;p->peer=peer;p->status=read_status();p->mie=read_mie();p->mip=read_mip();p->cycle=read_cycle();p->time=MTIME;
 __asm__ volatile("":::"memory");p->end=seq;p->begin=seq;
}
void iris_frontier_stamp(uint64_t stage,uintptr_t owner,uintptr_t current,uintptr_t peer){if(ready){unsigned h=hart();if(h<3)record(h,stage,owner,current,peer);}}
void iris_frontier_app_stamp(unsigned channel,uint64_t stage){if(ready&&channel<3)record(channel+3,stage,(uintptr_t)raw_cpu()->arch.fpu_owner,(uintptr_t)raw_cpu()->current,0);}
void iris_frontier_init(void){
 ready=0;for(unsigned i=0;i<0x2000/8;++i)((volatile uint64_t*)BASE)[i]=0;__asm__ volatile("fence rw,rw":::"memory");ready=1;
}
static void ch(char c){volatile uint32_t *u=(volatile uint32_t*)UART;while(u[0]&0x80000000u){}u[0]=(unsigned char)c;}
static void text(const char*s){while(*s)ch(*s++);}
static void number(uint64_t v){char b[21];unsigned n=0;do{b[n++]=(char)('0'+v%10);v/=10;}while(v);while(n)ch(b[--n]);}
static void field(const char*k,uint64_t v){text(k);number(v);}
int iris_frontier_arm(unsigned milliseconds,unsigned enabled){
 if(hart()!=1||milliseconds<2000||milliseconds>5000)return-1;
 if(enabled){
  unsigned long key=arch_irq_lock();(void)key;uint64_t begin=MTIME;CMP1=begin+(uint64_t)milliseconds*500;
  unsigned spin;for(spin=0;spin<10000&&(read_mip()&(1UL<<7));++spin)__asm__ volatile("");
  if(spin==10000){arch_irq_unlock(key);return-2;}
  CONTROL[1]=begin;CONTROL[2]=begin+(uint64_t)milliseconds*500;__asm__ volatile("fence rw,rw":::"memory");CONTROL[0]=1;
  __asm__ volatile("csrs mie,%0\n\tcsrs mstatus,%1"::"r"(1UL<<7),"r"(8UL):"memory");
 }
 iris_frontier_stamp(enabled?600:610,(uintptr_t)raw_cpu()->arch.fpu_owner,(uintptr_t)raw_cpu()->current,0);
 text("IRIS_FLUSH_ARM {\"hart\":1,\"enabled\":");text(enabled?"true":"false");field(",\"delay_ms\":",milliseconds);field(",\"armed_mtime\":",CONTROL[1]);field(",\"deadline_mtime\":",CONTROL[2]);field(",\"last_recorded_mstatus\":",read_status());field(",\"last_recorded_mie\":",read_mie());text("}\n");return 0;
}
void iris_frontier_cancel(void){if(ready&&CONTROL[0]){CONTROL[0]=0;__asm__ volatile("fence rw,rw":::"memory");CMP1=UINT64_MAX;}}
int iris_frontier_preserve_hart1_cmp(void){return ready&&hart()==1&&CONTROL[0];}
void iris_frontier_timer_entry(void){
 if(!ready||hart()!=1||!CONTROL[0]||MTIME<CONTROL[2])return;
 uint64_t entry_time=MTIME,entry_status=read_status(),entry_mie=read_mie(),entry_mip=read_mip();CONTROL[0]=0;CMP1=UINT64_MAX;
 volatile struct frontier*snap=(volatile struct frontier*)(BASE+0x1000);uint64_t stable[6];
 /* First copy every slot, before console/clock announcement/scheduler. Stable sequence is best-effort, not coherence proof. */
 for(unsigned i=0;i<6;++i){volatile uint64_t*src=(volatile uint64_t*)slot(i);volatile uint64_t*dst=(volatile uint64_t*)&snap[i];for(unsigned k=0;k<16;++k)dst[k]=src[k];stable[i]=snap[i].begin==snap[i].end&&!(snap[i].begin&1);}
 text("IRIS_FLUSH_ONESHOT {\"hart\":1,\"normal_completion\":false,\"exit_code\":1");field(",\"armed_mtime\":",CONTROL[1]);field(",\"deadline_mtime\":",CONTROL[2]);field(",\"entry_mtime\":",entry_time);field(",\"entry_mstatus\":",entry_status);field(",\"entry_mie\":",entry_mie);field(",\"entry_mip\":",entry_mip);text(",\"before_timer_spinlock_and_announce\":true}\n");
 for(unsigned i=0;i<6;++i){volatile struct frontier*p=&snap[i];text("IRIS_FLUSH_SNAPSHOT {");field("\"slot\":",i);text(",\"stable_sequence_observed\":");text(stable[i]?"true":"false");text(",\"metadata_race_possible\":true,\"current_PC_or_state_claimed\":false");field(",\"begin\":",p->begin);field(",\"stage\":",p->stage);field(",\"owner_thread_id\":",p->owner);field(",\"current_thread_id\":",p->current);field(",\"peer\":",p->peer);field(",\"last_recorded_mstatus\":",p->status);field(",\"last_recorded_mie\":",p->mie);field(",\"last_recorded_mip\":",p->mip);field(",\"last_recorded_mcycle\":",p->cycle);field(",\"last_recorded_mtime\":",p->time);field(",\"end\":",p->end);text("}\n");}
 volatile uint32_t*u=(volatile uint32_t*)UART;u[2]=(u[2]&~(0x1ffu<<16))|(1u<<16);while(!(u[5]&1)){}uint64_t edges=65536ULL+11ULL*((u[6]&65535)+1),ticks=(edges+999)/1000+1,begin=MTIME;while(MTIME-begin<ticks){}__asm__ volatile("fence rw,rw":::"memory");tohost=3;__asm__ volatile("fence rw,rw":::"memory");for(;;)__asm__ volatile("wfi");
}
