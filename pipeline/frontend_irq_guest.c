#include "runtime.h"
struct metrics {uint64_t cycles,instret,first,second;};
extern void irq_stream(struct metrics*,volatile uint64_t*);
extern void emit_pulse(void);
extern void edge_fetch(uint64_t*);
extern void illegal_sequence(uint64_t*);
extern unsigned char illegal_pc[];
extern unsigned char irq_stream_begin[],irq_stream_end[],edge_resume[],edge_word[];
extern uint64_t base_trap_dispatch(uint64_t,uint64_t,uint64_t,unsigned);
static struct metrics results[2];
static volatile uint64_t phase,ready,ipi_pc,timer_pc,pending_in_handler,fetch_pc,fetch_tval,fetch_seen,illegal_count,illegal_trap_pc,illegal_tval;
static uint64_t edge_result,illegal_result;
uint64_t trap_dispatch(uint64_t cause,uint64_t pc,uint64_t value,unsigned h){
  if(h==0&&cause==((1ULL<<63)|3)){ipi_pc=pc;pending_in_handler=*(volatile uint32_t*)IRIS_CLINT;}
  if(h==0&&cause==((1ULL<<63)|7))timer_pc=pc;
  if(h==0&&cause==1){fetch_pc=pc;fetch_tval=value;++fetch_seen;return(uint64_t)edge_resume;}
  if(h==0&&cause==2){illegal_trap_pc=pc;illegal_tval=value;++illegal_count;return pc+4;}
  return base_trap_dispatch(cause,pc,value,h);
}
static void field(const char* name,uint64_t value){putstr(name);putuint(value);}
void benchmark_main(unsigned h){
  barrier();
  if(h==2){ready=1;memory_fence();while(!phase){};emit_pulse();for(;;)__asm__ volatile("wfi");}
  if(h==1)for(;;)__asm__ volatile("wfi");
  while(!ready){}
  irq_stream(&results[0],&phase);
  set_timer(0,mtime()+4);
  __asm__ volatile("csrs mie,%0"::"r"(128UL):"memory");
  irq_stream(&results[1],&phase);
  __asm__ volatile("csrw mie,zero":::"memory");
  // The source I-cache fetches complete64B lines. Define every byte of
  // this executable last-TCM line before testing the unchanged boundary
  // fault oracle; model unknown-refill refusal must not fabricate padding.
  for(unsigned word=0;word<16;++word)((volatile uint32_t*)0x7003ffc0UL)[word]=0x00000013;
  *(volatile uint32_t*)0x7003fffcUL=*(const uint32_t*)edge_word;
  __asm__ volatile("fence.i":::"memory");
  edge_fetch(&edge_result);
  illegal_sequence(&illegal_result);
  unsigned bad=ipi_seen[0]!=1||timer_seen[0]!=1||pending_in_handler!=0||fetch_seen!=1||fetch_pc!=0x70040000||fetch_tval!=fetch_pc||edge_result!=42||illegal_count!=1||illegal_trap_pc!=(uint64_t)illegal_pc||illegal_tval!=0xb||illegal_result!=21;
  bad+=ipi_pc<(uint64_t)irq_stream_begin||ipi_pc>=(uint64_t)irq_stream_end||timer_pc<(uint64_t)irq_stream_begin||timer_pc>=(uint64_t)irq_stream_end;
  for(unsigned i=0;i<2;++i)bad+=results[i].first!=2048||results[i].second!=6144;
  putstr("PIPELINE_PRECISION {");field("\"ipi_seen\":",ipi_seen[0]);field(",\"timer_seen\":",timer_seen[0]);
  field(",\"ipi_pc\":",ipi_pc);field(",\"timer_pc\":",timer_pc);field(",\"pending_in_handler\":",pending_in_handler);
  field(",\"fetch_seen\":",fetch_seen);field(",\"fetch_pc\":",fetch_pc);field(",\"fetch_tval\":",fetch_tval);field(",\"edge_result\":",edge_result);
  field(",\"illegal_count\":",illegal_count);field(",\"illegal_pc\":",illegal_trap_pc);field(",\"illegal_tval\":",illegal_tval);field(",\"illegal_result\":",illegal_result);
  field(",\"failed\":",bad);putstr("}\n");finish(bad);
}
