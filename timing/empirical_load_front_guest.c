/* Functional/knownness/coherence mechanism test, excluded from calibration. */
#include "runtime.h"
static volatile uint64_t shared __attribute__((aligned(64)));
typedef struct __attribute__((aligned(64))){uint64_t failed,reads,opaque_byte;}record_t;
static record_t records[3];
void benchmark_main(unsigned h){
 volatile uint8_t*unknown=(volatile uint8_t*)(uintptr_t)(0x90000000ul+128*h);
 volatile uint8_t*copy=unknown+64;*unknown=7;
 __asm__ volatile("ld t0,0(%0)\nsd t0,0(%1)"::"r"(unknown),"r"(copy):"t0","memory");
 const uint64_t byte=*copy;
 if(h==0)shared=1;
 memory_fence();barrier();
 uint64_t warm=shared;__asm__ volatile(""::"r"(warm):"memory");barrier();
 uint64_t failed=byte!=7,reads=0;
 if(h==0){for(unsigned i=0;i<512;++i){uint64_t value;__asm__ volatile("ld %0,0(%1)":"=r"(value):"r"(&shared):"memory");failed+=value<1||value>3;++reads;}}
 else for(unsigned i=0;i<512;++i)__asm__ volatile("sd %0,0(%1)"::"r"((uint64_t)(h+1)),"r"(&shared):"memory");
 records[h]=(record_t){failed,reads,byte};barrier();
 if(h==0){unsigned total=0;for(unsigned i=0;i<3;++i){record_t*r=&records[i];putstr("IRIS_LOAD_FRONT ");putuint(i);putstr(" ");putuint(r->failed);putstr(" ");putuint(r->reads);putstr(" ");putuint(r->opaque_byte);putstr("\n");total+=r->failed;}finish(total);}
 for(;;)__asm__ volatile("wfi");
}
