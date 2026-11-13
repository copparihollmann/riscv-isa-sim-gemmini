#pragma once
#include "campaign.h"
#include "campaign_counts.h"
typedef struct __attribute__((aligned(64))) {
  uint64_t case_index, hart, start, end, instret, checksum, expected, pass;
} buffered_record_t;
extern volatile buffered_record_t buffered_records[CAMPAIGN_REGIONS];
extern volatile uint64_t buffered_measurements_done;
extern volatile uint64_t buffered_record_count;
extern volatile uint64_t buffered_case_count;
void buffer_record(const char *,unsigned,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
void buffer_commit_case(void);
