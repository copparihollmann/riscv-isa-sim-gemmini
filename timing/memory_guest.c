#include "runtime.h"

static volatile uint64_t dram_values[3][16] __attribute__((aligned(64)));
void benchmark_main(unsigned hart) {
  volatile uint64_t *tcm=(volatile uint64_t *)(uintptr_t)(0x70000000ull+hart*8);
  volatile uint64_t *scratch=(volatile uint64_t *)(uintptr_t)(0x580000000ull+hart*8);
  const uint64_t begin=cycles();
  *tcm=hart+1; tcm[8]=hart+7; *scratch=hart+11;
  for (unsigned i=0;i<16;++i) {
    dram_values[hart][i]=*tcm+tcm[8]+*scratch+i;
    *scratch+=1;
  }
  uint64_t sum=0;
  for (unsigned i=0;i<16;++i) sum+=dram_values[hart][i];
  const uint64_t end=cycles();
  const uint64_t expected=16*(3*hart+19)+240;
  if (sum!=expected) finish(1);
  barrier();
  for (unsigned turn=0;turn<3;++turn) {
    if (hart==turn) {
      putstr("IRIS_MEMORY {\"hart\":");putuint(hart);
      putstr(",\"start\":");putuint(begin);putstr(",\"end\":");putuint(end);
      putstr(",\"checksum\":");putuint(sum);putstr("}\n");
    }
    barrier();
  }
  if (!hart) finish(0);
}
