/* Finite timing-mechanism witness, excluded from fitting/accuracy claims. */
#include "runtime.h"
#ifndef IRIS_STORE_IRQ
#define IRIS_STORE_IRQ 0
#endif
typedef struct __attribute__((aligned(64))){uint64_t words[8];}line_t;
typedef struct __attribute__((aligned(64))){uint64_t failed,irq,last;}record_t;
static line_t private_lines[3];static record_t records[3];
static volatile uint64_t shared __attribute__((aligned(64)));
void benchmark_main(unsigned h){
 volatile uint64_t*p=private_lines[h].words;for(unsigned i=0;i<8;++i)p[i]=0;
 if(h==0){shared=0;}
 barrier();uint64_t failed=0;
 __asm__ volatile("li t0,1000\n.rept 64\nsd t0,0(%0)\naddi t0,t0,1\n.endr"::"r"(p):"t0","memory");failed+=p[0]!=1063;
 __asm__ volatile("addi t0,%0,8\nli t1,123\nsd t1,0(t0)"::"r"(p):"t0","t1","memory");failed+=p[1]!=123;
 p[0]=0x1122334455667788ul;
 __asm__ volatile("li t0,171\nsb t0,0(%0)\nli t0,52719\nsh t0,2(%0)\nli t0,305419896\nsw t0,4(%0)"::"r"(p):"t0","memory");failed+=p[0]!=0x12345678cdef77abul;
 register uint64_t value __asm__("a0")=0x12345678ul;register volatile uint64_t*address __asm__("a1")=p;
 __asm__ volatile(".option push\n.option rvc\nc.sd a0,0(a1)\nc.sw a0,8(a1)\naddi sp,sp,-16\nc.sdsp a0,0(sp)\nc.swsp a0,8(sp)\nld t0,0(sp)\nlwu t1,8(sp)\naddi sp,sp,16\nsd t0,16(a1)\nsd t1,24(a1)\n.option pop":"+r"(value),"+r"(address)::"t0","t1","memory");
 failed+=p[0]!=0x12345678ul||p[1]!=0x12345678ul||p[2]!=0x12345678ul||p[3]!=0x12345678ul;
 volatile uint8_t*unknown=(volatile uint8_t*)(uintptr_t)(0x92000000ul+128*h);*unknown=7;
 __asm__ volatile("ld t0,0(%0)\nsd t0,0(%1)"::"r"(unknown),"r"(p+4):"t0","memory");failed+=*(volatile uint8_t*)(p+4)!=7;
 volatile uint64_t canary=0x76543210ul;
 __asm__ volatile("li t0,1\nbnez t0,1f\nsd zero,0(%0)\n1:"::"r"(&canary):"t0","memory");failed+=canary!=0x76543210ul;
 barrier();
 if(IRIS_STORE_IRQ){set_timer(h,mtime()+4);__asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(128ul),"r"(8ul):"memory");
  __asm__ volatile("li t0,17\n.rept 1024\nsd t0,0(%0)\naddi t0,t0,1\n.endr"::"r"(p):"t0","memory");
  while(!timer_seen[h]){__asm__ volatile("nop");}
  failed+=timer_seen[h]!=1||p[0]!=1040;__asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8ul):"memory");}
 for(unsigned i=0;i<512;++i){if(h==1){uint64_t v=shared;failed+=v>3;}else __asm__ volatile("sd %0,0(%1)"::"r"((uint64_t)(h+1)),"r"(&shared):"memory");}
 records[h]=(record_t){failed,timer_seen[h],p[0]};barrier();
 if(h==0){unsigned total=0;for(unsigned i=0;i<3;++i){total+=records[i].failed;putstr("IRIS_OWNED_STORE ");putuint(i);putstr(" ");putuint(records[i].failed);putstr(" ");putuint(records[i].irq);putstr(" ");putuint(records[i].last);putstr("\n");}finish(total);}
 for(;;)__asm__ volatile("wfi");
}
