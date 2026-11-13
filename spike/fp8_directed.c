// Exercise the pinned source's FP8 section without its unconfigured column-out tests.
#define main original_directed_main
#include "main.c"
#undef main
int main(void) {
  size_t te = test_config();
  test_mm_fp8(te);
  printf("checksum 0x%08x\n", checksum);
  if (failures) { printf("FAILED (%d)\n", failures); return 1; }
  printf("PASSED\n");
  return 0;
}
