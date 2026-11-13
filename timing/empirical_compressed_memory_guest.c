/* Six actual RVC store encodings, per-hart numeric and feature witnesses. */
#include "runtime.h"
typedef struct __attribute__((aligned(64))) {uint64_t start,end,failed;} record_t;
static record_t records[3];
static volatile uint64_t data[3][8] __attribute__((aligned(64)));
void benchmark_main(unsigned h){
 const uint64_t bits=0x3ff0000000000000ul,value=0x1122334455667788ul;
 __asm__ volatile("csrs mstatus,%0\nfmv.d.x fa0,%1"::"r"(3ul<<13),"r"(bits):"fa0","memory");
 register uintptr_t address __asm__("a0")=(uintptr_t)&data[h][0];
 register uintptr_t payload __asm__("a1")=value;
 uint64_t start,end,a,b,c;
 __asm__ volatile("addi sp,sp,-32\ncsrr %0,mcycle\n.option push\n.option rvc\n"
  "c.sw a1,0(a0)\nc.sd a1,8(a0)\nc.fsd fa0,16(a0)\n"
  "c.swsp a1,0(sp)\nc.sdsp a1,8(sp)\nc.fsdsp fa0,16(sp)\n"
  ".option pop\ncsrr %1,mcycle\nlwu %2,0(sp)\nld %3,8(sp)\nld %4,16(sp)\naddi sp,sp,32"
  :"=&r"(start),"=&r"(end),"=&r"(a),"=&r"(b),"=&r"(c)
  :"r"(address),"r"(payload):"memory");
 uint64_t failed=data[h][0]!=(uint32_t)value||data[h][1]!=value||data[h][2]!=bits||a!=(uint32_t)value||b!=value||c!=bits;
 records[h]=(record_t){start,end,failed};barrier();
 if(h==0){unsigned total=0;for(unsigned i=0;i<3;++i){record_t*r=&records[i];putstr("IRIS_COMPRESSED_MEMORY ");putuint(i);putstr(" ");putuint(r->start);putstr(" ");putuint(r->end);putstr(" ");putuint(r->failed);putstr("\n");total+=r->failed;}finish(total);}
 for(;;)__asm__ volatile("wfi");
}
