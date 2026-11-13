/* Cross-feature mechanism witness, never a timing-fitting or heldout workload. */
#include "runtime.h"
typedef struct __attribute__((aligned(64))) {uint64_t words[8];}line_t;
typedef struct __attribute__((aligned(64))) {uint64_t failed,fp,last,irq,flags;}row_t;
static line_t lines[3];static row_t rows[3];
void benchmark_main(unsigned h){
 volatile uint64_t*p=lines[h].words;
 for(unsigned i=0;i<8;++i)p[i]=0;
 barrier();
 __asm__ volatile("fmv.w.x ft0,%0\nfmv.w.x ft1,%0"::"r"(0x3f800000ul):"ft0","ft1");
 set_timer(h,mtime()+1);
 __asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(128ul),"r"(8ul):"memory");
 __asm__ volatile("li t0,100\n.rept 128\nsd t0,0(%0)\nfadd.s ft0,ft0,ft1,rne\naddi t0,t0,1\n.endr"
                  ::"r"(p):"t0","ft0","memory");
 uint64_t fp,flags;
 __asm__ volatile("fmv.x.w %0,ft0":"=r"(fp)::"memory");
 __asm__ volatile("csrr %0,fflags":"=r"(flags)::"memory");
 while(!timer_seen[h])__asm__ volatile("nop");
 __asm__ volatile("csrc mstatus,%0\ncsrw mie,zero"::"r"(8ul):"memory");
 const uint64_t last=p[0];
 rows[h]=(row_t){fp!=0x43010000ul||last!=227||timer_seen[h]!=1||flags!=0,fp,last,timer_seen[h],flags};
 barrier();
 if(h==0){unsigned total=0;for(unsigned i=0;i<3;++i){row_t*r=&rows[i];total+=r->failed;
  putstr("IRIS_FADD_STORE ");putuint(i);putstr(" ");putuint(r->failed);putstr(" ");putuint(r->fp);putstr(" ");putuint(r->last);putstr(" ");putuint(r->irq);putstr(" ");putuint(r->flags);putstr("\n");}finish(total);}
 for(;;)__asm__ volatile("wfi");
}
