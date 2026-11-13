#include "runtime.h"
#include "vme.h"

#define RECORDS 576
#define RECORD_MAGIC 0x49524953434f4c31ULL
typedef struct { uint64_t meta[16]; uint32_t words[32]; } observation_t;
struct signature_t { uint64_t header[16]; observation_t records[2][RECORDS]; };
_Static_assert(sizeof(observation_t)==256,"Observation layout changed");
_Static_assert(sizeof(struct signature_t)==295040,"Signature layout changed");
struct signature_t sig __attribute__((section(".data.signature"),aligned(64)))={
  .header={0x49524953434f4c30ULL,1,RECORDS,256}};
__asm__(".globl begin_signature\n.set begin_signature,sig\n.globl end_signature\n.set end_signature,sig+295040\n");
/* The silent RTL derivative changes ONLY this initialized software input.
 * It is read after collection finishes; no probe takes a different branch. */
volatile uint64_t emit_console=1;
static uint32_t result[2][32] __attribute__((aligned(4096)));
static volatile struct { uint64_t cause,pc,value; } trap_record[3];
uint64_t base_trap_dispatch(uint64_t,uint64_t,uint64_t,unsigned);

uint64_t trap_dispatch(uint64_t cause,uint64_t pc,uint64_t value,unsigned hart) {
  if(cause==2 && expect_illegal[hart]) {
    trap_record[hart].cause=cause;trap_record[hart].pc=pc;trap_record[hart].value=value;
  }
  return base_trap_dispatch(cause,pc,value,hart);
}
static uint32_t base(unsigned h,unsigned trial,unsigned pattern) {
  return 0x12000000u+(h<<20)+(pattern<<16)+(trial<<12);
}
static uint64_t checksum(const uint32_t *words) {
  uint64_t hash=14695981039346656037ULL;
  for(unsigned i=0;i<32;++i)for(unsigned b=0;b<4;++b)
    hash=(hash^((words[i]>>(b*8))&255))*1099511628211ULL;
  return hash;
}
static void settle(void) {
  __asm__ volatile("fence rw,rw\n.rept 32\nnop\n.endr":::"memory");
}
static void initialize(unsigned h,unsigned trial,unsigned pattern) {
  vme_vsettnt_e32w1(32);vme_vsettm(32);vme_vsettk(1);
  VME_VTZERO(0);VME_VTZERO(1);VME_VTZERO(2);VME_VTZERO(3);settle();
  for(unsigned row=0;row<32;++row) {
    unsigned value=base(h,trial,pattern)+(row<<6);
    __asm__ volatile("vid.v v16\n\tvadd.vx v16,v16,%0"::"r"(value):"memory");
    VME_VTMV_T_V(vme_tss(0,VME_TSS_ROW,row),16);settle();
  }
}
static unsigned observe(unsigned h,unsigned trial,unsigned pattern,unsigned kind,unsigned index,unsigned slot) {
  observation_t *o=&sig.records[h][slot];
  uint64_t vl=vme_vsettnt_e32w1(32),pc=0,prior=illegal_seen[h];
  __asm__ volatile("vmv.v.x v24,%0"::"r"(0xfeed0000UL+index):"memory");settle();
  trap_record[h].cause=0;trap_record[h].pc=0;trap_record[h].value=0;
  size_t tss=vme_tss(0,kind==1?VME_TSS_COL:VME_TSS_ROW,index);
  expect_illegal[h]=kind==1;memory_fence();
  uint64_t start=cycles(),instret=retired();
  __asm__ volatile("lla %0,1f\n\t1: .insn r 0x57,6,0x21,x24,%1,x31":"=&r"(pc):"r"(tss):"memory");
  expect_illegal[h]=0;
  __asm__ volatile("vse32.v v24,(%0)\n\tfence rw,rw"::"r"(result[h]):"memory");
  uint64_t endret=retired(),end=cycles();
  unsigned failed=0;
  for(unsigned c=0;c<32;++c) {
    o->words[c]=result[h][c];
    if(kind!=1 && result[h][c]!=base(h,trial,pattern)+(index<<6)+c)++failed;
  }
  uint64_t values[16]={RECORD_MAGIC,h,trial,pattern,kind,index,vl,illegal_seen[h]-prior,
    start,end,endret-instret,checksum(o->words),trap_record[h].cause,trap_record[h].pc,trap_record[h].value,pc};
  for(unsigned i=0;i<16;++i)o->meta[i]=values[i];
  settle();return failed+(vl!=32);
}
__attribute__((noinline)) static void collect(unsigned h) {
  unsigned slot=0,failed=0;
  for(unsigned trial=0;trial<3;++trial)for(unsigned pattern=0;pattern<2;++pattern) {
    initialize(h,trial,pattern);
    for(unsigned row=0;row<32;++row)failed+=observe(h,trial,pattern,0,row,slot++);
    for(unsigned col=0;col<32;++col) {
      failed+=observe(h,trial,pattern,1,col,slot++);
      failed+=observe(h,trial,pattern,2,col,slot++);
    }
  }
  sig.header[10+h]=failed;sig.header[12+h]=slot;memory_fence();sig.header[4+h]=1;
}
static void case_id(const observation_t *o) {
  putstr("vme.column.");putstr(o->meta[4]==0?"pre-row":o->meta[4]==1?"column-observation":"post-row");
  putstr(".pattern");putuint(o->meta[3]);putstr(".index");putuint(o->meta[5]);
}
static void print(const observation_t *o) {
  unsigned column=o->meta[4]==1;
  putstr(column?"IRIS_COLUMN_OBSERVATION {\"case_id\":\"":"IRIS_REGION {\"case_id\":\"");
  case_id(o);putstr(".trial");putuint(o->meta[2]);putstr("\",\"parent_case_id\":\"");case_id(o);
  putstr("\",\"suite\":\"vme_column_probe\",\"region\":\"kernel\",\"hart\":");putuint(o->meta[1]);
  putstr(",\"trial_id\":");putuint(o->meta[2]);putstr(",\"pattern\":");putuint(o->meta[3]);
  putstr(",\"kind\":");putuint(o->meta[4]);putstr(",\"index\":");putuint(o->meta[5]);putstr(",\"vl\":");putuint(o->meta[6]);
  putstr(",\"illegal_delta\":");putuint(o->meta[7]);putstr(",\"start_cycle\":");putuint(o->meta[8]);
  putstr(",\"end_cycle\":");putuint(o->meta[9]);putstr(",\"instret_delta\":");putuint(o->meta[10]);
  putstr(",\"checksum\":");putuint(o->meta[11]);putstr(",\"trap_cause\":");putuint(o->meta[12]);
  putstr(",\"trap_pc\":");putuint(o->meta[13]);putstr(",\"trap_value\":");putuint(o->meta[14]);
  putstr(",\"instruction_pc\":");putuint(o->meta[15]);
  if(column) {
    putstr(",\"words\":[");for(unsigned c=0;c<32;++c){if(c)putstr(",");putuint(o->words[c]);}putstr("]");
  } else {
    uint32_t expected[32];for(unsigned c=0;c<32;++c)expected[c]=base(o->meta[1],o->meta[2],o->meta[3])+(o->meta[5]<<6)+c;
    uint64_t hash=checksum(expected);putstr(",\"expected_checksum\":");putuint(hash);
    putstr(",\"pass\":");putstr(o->meta[11]==hash&&o->meta[7]==0?"true":"false");
  }
  putstr("}\n");
}
void benchmark_main(unsigned h) {
  uint64_t vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));sig.header[7+h]=vlenb;
  barrier();
  if(h<2)collect(h);else{memory_fence();sig.header[6]=1;}
  barrier();
  if(h)for(;;)__asm__ volatile("wfi");
  unsigned failed=sig.header[10]+sig.header[11]+(sig.header[7]!=32)+(sig.header[8]!=32)+(sig.header[9]!=32);
  if(emit_console) {
    for(unsigned hart=0;hart<2;++hart)for(unsigned i=0;i<RECORDS;++i)print(&sig.records[hart][i]);
    putstr("IRIS_BATCH_DONE {\"failed\":");putuint(failed);putstr(",\"regions\":768,\"column_observations\":384}\n");
  }
  finish(failed!=0);
}
