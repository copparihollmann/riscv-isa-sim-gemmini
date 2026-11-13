#include "runtime.h"

typedef struct { const char *id,*parent; unsigned kind,rm,pattern,trial; uint32_t insn; uint64_t operand,expected; } case_t;
#include "cases.inc"
static volatile uint64_t request __attribute__((aligned(64)));
static volatile uint64_t complete __attribute__((aligned(64)));
static volatile struct { uint64_t cause,pc,value; } traps[3] __attribute__((aligned(64)));
static struct { uint64_t start,end,instret,destination,fcsr,delta,pc_match,checksum; } result[3] __attribute__((aligned(64)));
uint64_t base_trap_dispatch(uint64_t,uint64_t,uint64_t,unsigned);

uint64_t trap_dispatch(uint64_t cause,uint64_t pc,uint64_t value,unsigned hart) {
  if(cause==2 && expect_illegal[hart]) {
    traps[hart].cause=cause;traps[hart].pc=pc;traps[hart].value=value;
  }
  return base_trap_dispatch(cause,pc,value,hart);
}

static uint64_t hash_word(uint64_t hash,uint64_t word) {
  for(unsigned b=0;b<8;++b) {hash^=(word>>(8*b))&255;hash*=1099511628211ULL;}
  return hash;
}

static void probe(unsigned hart,const case_t *c) {
  uint64_t before=illegal_seen[hart],expected_pc=0,destination=0,fcsr=0;
  traps[hart].cause=UINT64_MAX;traps[hart].pc=0;traps[hart].value=0;
  expect_illegal[hart]=1;
  /* Explicitly initialize every floating-point value touched by the probe. */
  __asm__ volatile("fmv.d.x f1,%0\n\tfmv.d.x f2,%1\n\tcsrw fcsr,%2"
    ::"r"(c->operand),"r"(0x0123456789abcdefULL),"r"(0x1bUL):"f1","f2","memory");
  uint64_t start=cycles(),instret=retired();
  switch(c->kind*8+c->rm) {
#define OP(KEY,WORD) case KEY: __asm__ volatile("lla %0,1f\n\t1: .word " #WORD :"=r"(expected_pc)::"memory");break
    OP(0,0x44808153);OP(1,0x44809153);OP(2,0x4480a153);OP(3,0x4480b153);
    OP(4,0x4480c153);OP(5,0x4480d153);OP(6,0x4480e153);OP(7,0x4480f153);
    OP(8,0x40608153);OP(9,0x40609153);OP(10,0x4060a153);OP(11,0x4060b153);
    OP(12,0x4060c153);OP(13,0x4060d153);OP(14,0x4060e153);OP(15,0x4060f153);
  }
  uint64_t endret=retired(),end=cycles();
  __asm__ volatile("fmv.x.d %0,f2\n\tcsrr %1,fcsr":"=r"(destination),"=r"(fcsr)::"memory");
  expect_illegal[hart]=0;
  uint64_t delta=illegal_seen[hart]-before,pc_match=expected_pc==traps[hart].pc;
  uint64_t hash=14695981039346656037ULL;
  hash=hash_word(hash,delta);hash=hash_word(hash,destination);hash=hash_word(hash,fcsr);
  hash=hash_word(hash,traps[hart].cause);hash=hash_word(hash,pc_match);
  result[hart].start=start;result[hart].end=end;result[hart].instret=endret-instret;
  result[hart].destination=destination;result[hart].fcsr=fcsr;result[hart].delta=delta;
  result[hart].pc_match=pc_match;result[hart].checksum=hash;
}

static void print_region(unsigned hart,const case_t *c) {
  putstr("IRIS_REGION {\"case_id\":\"");putstr(c->id);
  putstr("\",\"parent_case_id\":\"");putstr(c->parent);
  putstr("\",\"suite\":\"scalar_bf16_decode\",\"region\":\"kernel\",\"hart\":");putuint(hart);
  putstr(",\"trial_id\":");putuint(c->trial);putstr(",\"instruction\":");putuint(c->insn);
  putstr(",\"operand_bits\":");putuint(c->operand);
  putstr(",\"start_cycle\":");putuint(result[hart].start);putstr(",\"end_cycle\":");putuint(result[hart].end);
  putstr(",\"instret_delta\":");putuint(result[hart].instret);putstr(",\"illegal_delta\":");putuint(result[hart].delta);
  putstr(",\"trap_cause\":");putuint(traps[hart].cause);putstr(",\"trap_pc\":");putuint(traps[hart].pc);
  putstr(",\"trap_value\":");putuint(traps[hart].value);putstr(",\"pc_match\":");putuint(result[hart].pc_match);
  putstr(",\"destination_bits\":");putuint(result[hart].destination);putstr(",\"fcsr\":");putuint(result[hart].fcsr);
  putstr(",\"checksum\":");putuint(result[hart].checksum);putstr(",\"expected_checksum\":");putuint(c->expected);
  putstr(",\"pass\":");putstr(result[hart].checksum==c->expected?"true":"false");putstr("}\n");
}

void benchmark_main(unsigned hart) {
  barrier();
  unsigned count=sizeof(cases)/sizeof(cases[0]);
  if(hart) {
    for(unsigned i=0;i<count;++i) {
      uint64_t token=(uint64_t)i*3+hart+1;
      while(__atomic_load_n(&request,__ATOMIC_ACQUIRE)!=token){}
      probe(hart,&cases[i]);__atomic_store_n(&complete,token,__ATOMIC_RELEASE);
    }
    for(;;)__asm__ volatile("wfi");
  }
  unsigned failed=0;
  for(unsigned i=0;i<count;++i)for(unsigned h=0;h<3;++h) {
    const case_t *c=&cases[i];
    putstr("IRIS_PROBE_BEGIN {\"case_id\":\"");putstr(c->id);putstr("\",\"hart\":");putuint(h);putstr("}\n");
    if(!h)probe(0,c);
    else {
      uint64_t token=(uint64_t)i*3+h+1,deadline=mtime()+250000;
      __atomic_store_n(&request,token,__ATOMIC_RELEASE);
      unsigned polls=0;
      while(__atomic_load_n(&complete,__ATOMIC_ACQUIRE)!=token) {
        if((++polls&1023)==0&&mtime()>deadline) {
          putstr("IRIS_PROBE_TIMEOUT {\"case_id\":\"");putstr(c->id);putstr("\",\"hart\":");putuint(h);putstr("}\n");finish(1);
        }
      }
    }
    print_region(h,c);if(result[h].checksum!=c->expected)++failed;
  }
  putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"regions\":");putuint(count*3);putstr("}\n");
  finish(failed!=0);
}
