/* Actual CLINT IPI during control speculation; excluded from timing fitting. */
#include "runtime.h"
static uint64_t result[3];
static uint64_t branch_work(unsigned n){uint64_t value=0;for(unsigned i=0;i<n;++i)__asm__ volatile("andi t0,%1,1\nbeqz t0,1f\naddi %0,%0,3\nj 2f\n1:addi %0,%0,1\n2:":"+r"(value):"r"(i):"t0");return value;}
void benchmark_main(unsigned h){
 __asm__ volatile("csrs mie,%0\ncsrs mstatus,%1"::"r"(8ul),"r"(8ul):"memory");barrier();uint64_t total=0;
 for(unsigned round=0;round<32;++round){barrier();total+=branch_work(32);send_ipi((h+1)%3);total+=branch_work(128);while(ipi_seen[h]<=round)__asm__ volatile("nop");}
 result[h]=total;barrier();
 if(h==0){unsigned failed=0;for(unsigned i=0;i<3;++i){failed+=result[i]!=10240||ipi_seen[i]!=32;putstr("IRIS_IPI_BRANCH ");putuint(i);putstr(" ");putuint(result[i]);putstr(" ");putuint(ipi_seen[i]);putstr("\n");}finish(failed);}
 for(;;)__asm__ volatile("wfi");
}
