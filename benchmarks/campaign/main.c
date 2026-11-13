#include "campaign.h"
#include "campaign_counts.h"
void campaign_identity(const char *suite,const char *id) {
  char parent[192];unsigned n=0,trial=0;
  while(id[n]&&!(id[n]=='.'&&id[n+1]=='t'&&id[n+2]=='r'&&id[n+3]=='i'&&id[n+4]=='a'&&id[n+5]=='l'&&id[n+6]=='.')) {
    if(n+1>=sizeof(parent)) fail(0,0,0,1);
    parent[n]=id[n];++n;
  }
  if(!id[n]) fail(0,0,0,2);
  parent[n]=0;n+=7;
  for(;id[n];++n) { if(id[n]<'0'||id[n]>'9')fail(0,0,0,3);trial=trial*10+(unsigned)(id[n]-'0'); }
  if(trial>=CAMPAIGN_TRIALS)fail(0,0,0,4);
  putstr(",\"parent_case_id\":\"");putstr(parent);putstr("\",\"trial_id\":");putuint(trial);
  putstr(",\"suite\":\"");putstr(suite);putstr("\"");
}
void campaign_phase(const char *suite,unsigned trial,unsigned begin) {
  if(hart_id())return;
  putstr("IRIS_CAMPAIGN_PHASE {\"suite\":\"");putstr(suite);putstr("\",\"trial_id\":");putuint(trial);
  putstr(",\"begin\":");putstr(begin?"true":"false");putstr("}\n");
}
void campaign_abort(const char *suite,unsigned failed) {
  putstr("IRIS_CAMPAIGN_FAILED {\"suite\":\"");putstr(suite);putstr("\",\"failed\":");putuint(failed);putstr("}\n");finish(1);
}
void benchmark_main(unsigned hart) {
  barrier();
  for(unsigned trial=0;trial<CAMPAIGN_TRIALS;++trial)campaign_baseline_run(hart,trial);
  campaign_distribution_run(hart);campaign_memory_run(hart);barrier();
  if(!hart){
    putstr("IRIS_BATCH_DONE {\"failed\":0,\"cases\":");putuint(CAMPAIGN_CASES);
    putstr(",\"regions\":");putuint(CAMPAIGN_REGIONS);putstr(",\"trials\":");putuint(CAMPAIGN_TRIALS);putstr("}\n");finish(0);
  }
  for(;;)__asm__ volatile("wfi");
}
