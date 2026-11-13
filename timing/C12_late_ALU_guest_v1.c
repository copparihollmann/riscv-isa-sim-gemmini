#include "runtime.h"
static uint64_t words[3][8] __attribute__((aligned(64)));
static uint64_t rows[3][3];
extern uint64_t late_add(uint64_t*,uint64_t),late_sub(uint64_t*,uint64_t),late_word(uint64_t*),late_rvc(uint64_t*,uint64_t),late_zero(uint64_t*);
__asm__(".text\n.option push\n.option norvc\n.balign 64\n.globl late_add\n.type late_add,@function\nlate_add:\nld a2,0(a0)\nadd a2,a2,a1\naddi a0,a2,1\nret\n.size late_add,.-late_add\n.balign 64\n.globl late_sub\n.type late_sub,@function\nlate_sub:\nld a2,0(a0)\nsub a3,a1,a2\naddi a0,a3,1\nret\n.size late_sub,.-late_sub\n.balign 64\n.globl late_word\n.type late_word,@function\nlate_word:\nlw a2,0(a0)\naddiw a2,a2,3\naddi a0,a2,1\nret\n.size late_word,.-late_word\n.balign 64\n.globl late_zero\n.type late_zero,@function\nlate_zero:\nld a2,0(a0)\nandi a2,a2,0\naddi a0,a2,1\nret\n.size late_zero,.-late_zero\n.option pop\n.option push\n.option rvc\n.balign 64\n.globl late_rvc\n.type late_rvc,@function\nlate_rvc:\nc.ld a5,0(a0)\nc.add a5,a1\nmv a0,a5\nret\n.size late_rvc,.-late_rvc\n.option pop\n");
void benchmark_main(unsigned h){
 words[h][0]=0x80000005ul;words[h][1]=0x123456789abcdef0ul;memory_fence();barrier();uint64_t bad=0,count=0;
 if(h<2){for(unsigned i=0;i<128;++i){bad+=late_add(words[h]+1,5)!=0x123456789abcdef6ul;bad+=late_sub(words[h]+1,5)!=(uint64_t)(6ul-0x123456789abcdef0ul);bad+=late_word(words[h])!=0xffffffff80000009ul;bad+=late_rvc(words[h]+1,5)!=0x123456789abcdef5ul;count+=4;}
 volatile uint8_t*u=(volatile uint8_t*)(0x90002000ul+128*h);*u=7;memory_fence();__asm__ volatile("ld t0,0(%0)\nsd t0,0(%1)"::"r"(u),"r"(u+64):"t0","memory");memory_fence();for(unsigned i=0;i<16;++i){bad+=late_zero((uint64_t*)u)!=1;++count;}}
 rows[h][0]=bad;rows[h][1]=count;rows[h][2]=words[h][1];barrier();if(h==0){unsigned failed=0;for(unsigned t=0;t<3;++t){failed+=rows[t][0];putstr("LATE_ALU ");putuint(t);for(unsigned k=0;k<3;++k){putstr(" ");putuint(rows[t][k]);}putstr("\n");}finish(failed);}for(;;)__asm__ volatile("wfi");
}
