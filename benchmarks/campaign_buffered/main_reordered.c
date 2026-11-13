#include "buffered.h"
#include "buffered_cases.inc"

volatile buffered_record_t buffered_records[CAMPAIGN_REGIONS];
/* File-backed known sentinel: debugger reads are valid even before CRT/BSS. */
volatile uint64_t buffered_measurements_done = UINT64_MAX;
volatile uint64_t buffered_record_count, buffered_case_count;
static unsigned rows_in_case;

static unsigned equal(const char *a,const char *b) {
  while(*a && *a==*b) { ++a; ++b; }
  return *a==*b;
}

void buffer_record(const char *id,unsigned hart,uint64_t start,uint64_t end,
                   uint64_t instret,uint64_t checksum,uint64_t expected) {
  uint64_t c=buffered_case_count,r=buffered_record_count;
  if(hart_id()!=0 || c>=CAMPAIGN_CASES || r>=CAMPAIGN_REGIONS ||
     !equal(id,buffered_original_ids[c]) || !(buffered_masks[c]&(1U<<hart)) ||
     expected!=buffered_goldens[c][hart]) campaign_abort("record_identity",1);
  buffered_records[r]=(buffered_record_t){c,hart,start,end,instret,checksum,expected,checksum==expected};
  ++buffered_record_count; ++rows_in_case;
}

void buffer_commit_case(void) {
  if(buffered_case_count>=CAMPAIGN_CASES ||
     rows_in_case!=(unsigned)__builtin_popcount(buffered_masks[buffered_case_count]))
    campaign_abort("case_count",1);
  rows_in_case=0; ++buffered_case_count;
}

void campaign_phase(const char *suite,unsigned trial,unsigned begin) {
  (void)suite; (void)trial; (void)begin;
}
/* This is a new execution/history workload. No per-case console work remains. */
void campaign_identity(const char *suite,const char *id) { (void)suite; (void)id; }

static void print_records(void) {
  for(uint64_t i=0;i<buffered_record_count;++i) {
    buffered_record_t r=buffered_records[i];
    if(r.case_index>=CAMPAIGN_CASES) fail(0,0,0,99);
    uint64_t c=r.case_index;
    putstr("IRIS_REGION {\"case_id\":\"");putstr(buffered_ids[c]);
    putstr("\",\"region\":\"kernel\",\"hart\":");putuint(r.hart);
    putstr(",\"parent_case_id\":\"");putstr(buffered_parent_ids[c]);
    putstr("\",\"trial_id\":");putuint(buffered_trials[c]);
    putstr(",\"suite\":\"");putstr(buffered_suites[c]);
    putstr("\",\"start_cycle\":");putuint(r.start);
    putstr(",\"end_cycle\":");putuint(r.end);
    putstr(",\"instret_delta\":");putuint(r.instret);
    putstr(",\"checksum\":");putuint(r.checksum);
    putstr(",\"expected_checksum\":");putuint(r.expected);
    putstr(",\"pass\":");putstr(r.pass?"true":"false");putstr("}\n");
  }
}

void campaign_abort(const char *suite,unsigned failed) {
  print_records();
  putstr("IRIS_CAMPAIGN_FAILED {\"suite\":\"");putstr(suite);
  putstr("\",\"failed\":");putuint(failed);putstr("}\n");finish(1);
  __builtin_unreachable();
}

void benchmark_main(unsigned hart) {
  barrier();
  campaign_memory_run(hart);campaign_distribution_run(hart);
  for(unsigned trial=0;trial<CAMPAIGN_TRIALS;++trial) campaign_baseline_run(hart,trial);
  barrier();
  if(!hart) {
    if(buffered_case_count!=CAMPAIGN_CASES || buffered_record_count!=CAMPAIGN_REGIONS)
      campaign_abort("final_count",1);
    memory_fence(); buffered_measurements_done=0; memory_fence();
    print_records();
    putstr("IRIS_BATCH_DONE {\"failed\":0,\"cases\":");putuint(CAMPAIGN_CASES);
    putstr(",\"regions\":");putuint(CAMPAIGN_REGIONS);
    putstr(",\"trials\":");putuint(CAMPAIGN_TRIALS);putstr("}\n");finish(0);
  }
  for(;;) __asm__ volatile("wfi");
}
