/* Independent source mechanism checks. No hardware labels or fit inputs. */
#include "runtime.h"
extern volatile uint64_t pending_fault_expected[3],pending_fault_seen[3],pending_fault_pc[3];
static uint64_t words[3][8] __attribute__((aligned(64)));
static struct {uint64_t bad,hot,cold,irq,fault,fault_pc;} rows[3];
extern uint64_t pending_base_load(uint64_t*,uint64_t);
extern void pending_base_fault(uint64_t*,uint64_t);
__asm__(".text\n.option push\n.option norvc\n.balign 64\n.globl pending_base_load\n.type pending_base_load,@function\npending_base_load:\nslli t0,a1,3\nadd t0,t0,a0\nld a0,0(t0)\nret\n.size pending_base_load,.-pending_base_load\n.balign 64\n.globl pending_base_fault\n.type pending_base_fault,@function\npending_base_fault:\nslli t0,a1,3\nadd t0,t0,a0\n.globl pending_base_fault_load\npending_base_fault_load:\nld t1,0(t0)\nret\n.size pending_base_fault,.-pending_base_fault\n.option pop\n");
void benchmark_main(unsigned h){
 for(unsigned i=0;i<8;++i)words[h][i]=40+h+i;
 if(h==2){*(volatile uint64_t*)0x90000000ul=99;*(volatile uint64_t*)0x90000040ul=100;}
 memory_fence();barrier();uint64_t bad=0,hot=0,cold=0;
 if(h<2){
  for(unsigned i=0;i<8;++i){volatile uint64_t v=words[h][i];(void)v;}
  for(unsigned i=0;i<64;++i){hot=pending_base_load(words[h],3);bad+=hot!=43+h;}
  cold=pending_base_load((uint64_t*)(0x90000000ul+64*h),0);bad+=cold!=99+h;
  pending_fault_expected[h]=1;memory_fence();pending_base_fault((uint64_t*)((uintptr_t)words[h]+1),0);bad+=pending_fault_seen[h]!=1;
  set_timer(h,mtime()+1);__asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(128ul),"r"(8ul):"memory");
  __asm__ volatile(".rept 4\nnop\n.endr":::"memory");
  for(unsigned i=0;i<512;++i){hot=pending_base_load(words[h],3);bad+=hot!=43+h;}
  while(!timer_seen[h])__asm__ volatile("nop");
  __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8ul):"memory");bad+=timer_seen[h]!=1;
 }
 rows[h]=(typeof(rows[0])){bad,hot,cold,timer_seen[h],pending_fault_seen[h],pending_fault_pc[h]};barrier();
 if(h==0){unsigned total=0;for(unsigned t=0;t<3;++t){total+=rows[t].bad;putstr("PENDING_BASE ");putuint(t);putstr(" ");putuint(rows[t].bad);putstr(" ");putuint(rows[t].hot);putstr(" ");putuint(rows[t].cold);putstr(" ");putuint(rows[t].irq);putstr(" ");putuint(rows[t].fault);putstr(" ");putuint(rows[t].fault_pc);putstr("\n");}finish(total);}
 for(;;)__asm__ volatile("wfi");
}
