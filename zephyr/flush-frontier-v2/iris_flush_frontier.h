#ifndef IRIS_FLUSH_FRONTIER_H
#define IRIS_FLUSH_FRONTIER_H
#include <stdint.h>
/* Diagnostic scalar observations only; no completion, current-PC, or coherent-state claim. */
void iris_frontier_init(void);
void iris_frontier_stamp(uint64_t stage,uintptr_t owner,uintptr_t current,uintptr_t peer);
void iris_frontier_app_stamp(unsigned channel,uint64_t stage);
int iris_frontier_arm(unsigned milliseconds,unsigned enabled);
void iris_frontier_cancel(void);
int iris_frontier_preserve_hart1_cmp(void);
void iris_frontier_timer_entry(void);
#endif
