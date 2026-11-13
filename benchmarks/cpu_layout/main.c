#include "runtime.h"
typedef struct __attribute__((aligned(64))) { uint64_t begin,end,instructions,value,counter,loop_pc,begin_pc,end_pc; } row_t;
typedef void (*fn_t)(unsigned,uint64_t,volatile row_t*);
#include "functions.inc"
extern void layout_noop(unsigned,uint64_t,volatile row_t*);
static volatile row_t rows[64][4][3][3];
static volatile row_t noops[3][3];
static const unsigned ns[4]={16,64,256,1024};
static volatile unsigned failed;
static void print_row(const char*mode,unsigned offset,unsigned n,unsigned repeat,unsigned h,const volatile row_t*r){
 putstr("IRIS_REGION {\"case_id\":\"cpu.layout.");putstr(mode);putstr(".off");putuint(offset);putstr(".n");putuint(n);putstr(".repeat");putuint(repeat);
 putstr("\",\"region\":\"loop\",\"hart\":");putuint(h);putstr(",\"mode\":\"");putstr(mode);putstr("\",\"loop_offset\":");putuint(offset);putstr(",\"n\":");putuint(n);putstr(",\"repeat\":");putuint(repeat);
 putstr(",\"start_cycle\":");putuint(r->begin);putstr(",\"end_cycle\":");putuint(r->end);putstr(",\"instret_delta\":");putuint(r->instructions);putstr(",\"checksum\":");putuint(r->value);putstr(",\"expected_checksum\":");putuint(h+1+3*n);
 putstr(",\"counter_end\":");putuint(r->counter);putstr(",\"loop_pc\":");putuint(r->loop_pc);putstr(",\"begin_pc\":");putuint(r->begin_pc);putstr(",\"end_pc\":");putuint(r->end_pc);putstr(",\"pass\":");putstr(r->value==h+1+3*n&&r->counter==n?"true":"false");putstr("}\n");
}
void benchmark_main(unsigned h){
 for(unsigned i=0;i<64;++i)for(unsigned j=0;j<4;++j){
  barrier();__asm__ volatile("fence.i":::"memory");
  for(unsigned rep=0;rep<3;++rep){functions[i](ns[j],h+1,&rows[i][j][rep][h]);if(rows[i][j][rep][h].value!=h+1+3*ns[j]||rows[i][j][rep][h].counter!=ns[j])__atomic_fetch_add(&failed,1,__ATOMIC_SEQ_CST);}
  barrier();
 }
 barrier();for(unsigned rep=0;rep<3;++rep){layout_noop(0,h+1,&noops[rep][h]);if(noops[rep][h].value!=h+1)__atomic_fetch_add(&failed,1,__ATOMIC_SEQ_CST);}barrier();
 if(h==0){
  for(unsigned i=0;i<64;++i)for(unsigned j=0;j<4;++j)for(unsigned rep=0;rep<3;++rep)for(unsigned hart=0;hart<3;++hart)print_row(i<32?"compact":"wide",2*(i%32),ns[j],rep,hart,&rows[i][j][rep][hart]);
  for(unsigned rep=0;rep<3;++rep)for(unsigned hart=0;hart<3;++hart)print_row("noop",8,0,rep,hart,&noops[rep][hart]);
  putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"regions\":2313}\n");finish(failed?1:0);
 }
 for(;;)__asm__ volatile("wfi");
}
