#include "runtime.h"
#ifndef UART_MODE
#define UART_MODE 0
#endif
#define UART 0x10020000UL
#define PLIC 0x0c000000UL
static volatile uint64_t irq_seen,received;
static volatile uint32_t *uart(unsigned o){return (volatile uint32_t*)(UART+o);}
static volatile uint32_t *plic(unsigned o){return (volatile uint32_t*)(PLIC+o);}
static void require(int v,unsigned line){if(!v)fail(hart_id(),252,line,0);}
extern uint64_t base_trap_dispatch(uint64_t,uint64_t,uint64_t,unsigned);
uint64_t trap_dispatch(uint64_t cause,uint64_t pc,uint64_t value,unsigned h){
  if(cause==((1ULL<<63)|11)){
    require(h==0&&*plic(0x200004)==1,__LINE__);
#if UART_MODE == 2
    received=*uart(4);
#endif
    *uart(0x10)=0;*plic(0x200004)=1;++irq_seen;return pc;
  }
  return base_trap_dispatch(cause,pc,value,h);
}
static void initialize_plic(void){
  *plic(4)=1;
  for(unsigned c=0;c<6;++c){*plic(0x2000+c*0x80)=c?0:2;*plic(0x200000+c*0x1000)=0;}
}
static void wait_irq(void){
  __asm__ volatile("li t0,2048\n\tcsrw mie,t0":::"t0","memory");
  while(!irq_seen){__asm__ volatile("csrc mstatus,%0"::"r"(8UL):"memory");if(!irq_seen)__asm__ volatile("wfi":::"memory");__asm__ volatile("csrs mstatus,%0"::"r"(8UL):"memory");}
  __asm__ volatile("csrw mie,zero":::"memory");
}
static void drain(void){
  *uart(8)=0x10001;while(!(*uart(0x14)&1)){}
  uint64_t until=mtime()+2;while(mtime()<until){}
}
void benchmark_main(unsigned h){
  __asm__ volatile("csrw mie,zero":::"memory");set_timer(h,UINT64_MAX);barrier();
  if(h)for(;;)__asm__ volatile("wfi");
#if UART_MODE == 0 || UART_MODE == 1
  *uart(8)=0;require(*uart(0x18)==135,__LINE__);
  for(unsigned i=0;i<256;++i)*uart(0)=i;
  require(*uart(0)==0x80000000,__LINE__);*uart(0)=99;*uart(0)=0x80000061;
  // Ninth watermark bit is observable while full; TX is still disabled.
  *uart(8)=0x1000000;require(*uart(8)==0x1000000,__LINE__);
  initialize_plic();*uart(8)=0x10001;*uart(0x10)=1;wait_irq();
  require(irq_seen==1,__LINE__);drain();
#elif UART_MODE == 2
  initialize_plic();*uart(0xc)=1;*uart(0x10)=2;wait_irq();
  require(received==0x5a&&*(volatile uint8_t*)(UART+7)==0x80,__LINE__);
#elif UART_MODE == 3
  (void)*uart(4);putstr("UNEXPECTED unknown empty RX accepted\n");finish(1);
#elif UART_MODE == 4
  require(*(volatile uint8_t*)(UART+7)==0x80,__LINE__);
#elif UART_MODE == 5
  *(volatile uint8_t*)(UART+0xa)=255;require(*(volatile uint16_t*)(UART+0xa)==0,__LINE__);
  *(volatile uint16_t*)(UART+0xa)=511;require(*(volatile uint16_t*)(UART+0xa)==511,__LINE__);
  *(volatile uint8_t*)(UART+0x18)=7;require(*uart(0x18)==135,__LINE__);
  *(volatile uint16_t*)(UART+0x18)=0;require(*uart(0x18)==0,__LINE__);*uart(0x18)=135;
#elif UART_MODE == 6
  *uart(8)=0x1000001;*uart(0xc)=0x1000001;
  require((*uart(8)>>16)==256&&(*uart(0xc)>>16)==256,__LINE__);
  *uart(0x10)=3;require((*uart(0x14)&3)==1,__LINE__);*uart(0x10)=0;
#endif
  putstr("PASSED UART device mode ");putuint(UART_MODE);putstr("\n");drain();finish(0);
}
