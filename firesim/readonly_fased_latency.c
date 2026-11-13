#define _POSIX_C_SOURCE 200809L
/* Explicit read-only BAR0 probe for the paired Iris FireSim generated header.
 * Root agent alone owns FPGA execution. This program has no write path.
 */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "This source-verified BAR probe requires the x86 little-endian host contract"
#endif
_Static_assert(sizeof(uint32_t) == 4, "MMIO control registers are 32 bits");
enum { WRITE_LATENCY_OFFSET = 0, READ_LATENCY_OFFSET = 4, PRESENCE_OFFSET = 356 };
static const uint32_t expected_presence = UINT32_C(0x46697265);

static void quoted(const char *text) {
  putchar('"');
  for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
    if (*p == '"' || *p == '\\') printf("\\%c", *p);
    else if (*p < 32) printf("\\u%04x", *p);
    else putchar(*p);
  }
  putchar('"');
}

static void rejected(const char *reason, uint32_t presence) {
  printf("{\"status\":"); quoted(reason);
  printf(",\"presence_byte_offset\":356,\"presence_observed\":%" PRIu32
         ",\"presence_expected\":%" PRIu32 ",\"selected_parameters\":null,"
         "\"hardware_writes\":false,\"calibration_usable\":false}\n", presence, expected_presence);
}

int main(int argc, char **argv) {
  if (argc != 3 || (strcmp(argv[1], "--read-idle-device") && strcmp(argv[1], "--test-file"))) {
    fprintf(stderr, "usage: %s --read-idle-device /dev/xdma0_user | --test-file FILE\n", argv[0]);
    return 2;
  }
  const int test_file = !strcmp(argv[1], "--test-file");
  if (!test_file && strcmp(argv[2], "/dev/xdma0_user")) {
    fprintf(stderr, "Only the independently verified /dev/xdma0_user target is accepted\n"); return 2;
  }
  const int descriptor = open(argv[2], O_RDONLY | O_SYNC);
  if (descriptor < 0) { perror("open read-only"); return 1; }
  struct stat info;
  if (fstat(descriptor, &info) ||
      (test_file ? (!S_ISREG(info.st_mode) || info.st_size < PRESENCE_OFFSET + 4) : !S_ISCHR(info.st_mode))) {
    fprintf(stderr, "Unexpected probe file type or truncated fixture\n"); close(descriptor); return 1;
  }
  const long page = sysconf(_SC_PAGESIZE);
  if (page < PRESENCE_OFFSET + 4) { fprintf(stderr, "Invalid host page size\n"); close(descriptor); return 1; }
  void *mapping = mmap(NULL, (size_t)page, PROT_READ, MAP_SHARED, descriptor, 0);
  if (mapping == MAP_FAILED) { perror("mmap read-only BAR0"); close(descriptor); return 1; }
  volatile const uint32_t *registers = (volatile const uint32_t *)mapping;
  const uint32_t presence_before = registers[PRESENCE_OFFSET / sizeof(uint32_t)];
  if (presence_before != expected_presence) {
    rejected("IRIS_FASED_INVALID_PRESENCE_BEFORE_READ", presence_before);
    munmap(mapping, (size_t)page); close(descriptor); return 1;
  }
  const uint32_t first_write = registers[WRITE_LATENCY_OFFSET / sizeof(uint32_t)];
  const uint32_t first_read = registers[READ_LATENCY_OFFSET / sizeof(uint32_t)];
  const uint32_t second_write = registers[WRITE_LATENCY_OFFSET / sizeof(uint32_t)];
  const uint32_t second_read = registers[READ_LATENCY_OFFSET / sizeof(uint32_t)];
  const uint32_t presence_after = registers[PRESENCE_OFFSET / sizeof(uint32_t)];
  const int stable = first_write == second_write && first_read == second_read;
  const int unmap_status = munmap(mapping, (size_t)page);
  const int close_status = close(descriptor);
  if (unmap_status || close_status) { perror("release read-only mapping"); return 1; }
  if (presence_after != expected_presence) {
    rejected("IRIS_FASED_INVALID_PRESENCE_AFTER_READ", presence_after); return 1;
  }
  if (first_write == UINT32_MAX || first_read == UINT32_MAX || second_write == UINT32_MAX || second_read == UINT32_MAX) {
    rejected("IRIS_FASED_AMBIGUOUS_ALL_ONES_PARAMETER", presence_after); return 1;
  }
  if (!stable) {
    rejected("IRIS_FASED_UNSTABLE_PARAMETER_SAMPLES", presence_after); return 1;
  }
  printf("{\"source\":"); quoted(argv[2]);
  printf(",\"test_file\":%s,\"hardware_writes\":false,\"access\":\"O_RDONLY/PROT_READ\","
         "\"register_width_bits\":32,\"byte_order\":\"little\",\"stable_two_samples\":%s,"
         "\"presence_byte_offset\":356,\"presence_verified_before_and_after\":true,"
         "\"writeLatency\":{\"byte_offset\":0,\"first\":%" PRIu32 ",\"second\":%" PRIu32 "},"
         "\"readLatency\":{\"byte_offset\":4,\"first\":%" PRIu32 ",\"second\":%" PRIu32 "},"
         "\"calibration_usable\":false}\n",
         test_file ? "true" : "false", stable ? "true" : "false",
         first_write, second_write, first_read, second_read);
  return stable ? 0 : 1;
}
