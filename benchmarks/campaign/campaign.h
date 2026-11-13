#pragma once
#include "runtime.h"
void campaign_identity(const char *suite,const char *id);
void campaign_phase(const char *suite,unsigned trial,unsigned begin);
void campaign_abort(const char *suite,unsigned failed) __attribute__((noreturn));
void campaign_baseline_run(unsigned hart,unsigned trial);
void campaign_distribution_run(unsigned hart);
void campaign_memory_run(unsigned hart);
