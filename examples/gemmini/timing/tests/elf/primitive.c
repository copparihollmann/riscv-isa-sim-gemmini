/* Independent raw-ISA probe. No vendor headers or kernel routines. */
typedef unsigned long u64;
typedef signed char i8;
typedef int i32;

extern volatile u64 tohost;

static volatile i8 a[16] __attribute__((aligned(64)));
static volatile i8 b[16] __attribute__((aligned(64)));
static volatile i8 roundtrip[16] __attribute__((aligned(64)));
static volatile i32 output[16] __attribute__((aligned(64)));

#define COMMAND(funct, rs1, rs2) \
  __asm__ volatile(".insn r 0x7b, 3, %c2, x0, %0, %1" \
                   : : "r"((u64)(rs1)), "r"((u64)(rs2)), "i"(funct) : "memory")

static u64 tile(unsigned address) {
  return address | (4ul << 32) | (4ul << 48);
}

static void print(const char *text) {
  while (*text) {
    tohost = 0x0101000000000000ul | (unsigned char)*text++;
    while (tohost) {}
  }
}

int main(void) {
  __asm__ volatile("csrr zero, mcycle" : : : "memory");
  for (unsigned i = 0; i < 16; ++i) {
    a[i] = (i8)((int)(i * 3u % 7u) - 3);
    b[i] = (i8)((int)(i * 5u % 9u) - 4);
    roundtrip[i] = 0x6d;
    output[i] = 0x6d6d6d6d;
  }
  const u64 one = 0x3f800000ul; /* exact float32 scale 1.0 */
  // Reset leaves acc_act unspecified. Set RELU, then NONE, before use.
  COMMAND(0, 2ul | (1ul << 2), (one << 32) | 4);
  COMMAND(0, 2, (one << 32) | 4);
  COMMAND(0, 3ul | (1ul << 17), 0); // selected stat0, no normalizing activation
  COMMAND(0, 1ul | (16ul << 16) | (one << 32), 4); // load0, pixels1, block stride16
  COMMAND(2, a, tile(0));
  COMMAND(2, b, tile(16));
  COMMAND(3, roundtrip, tile(0));
  COMMAND(127, 0, 0);
  __asm__ volatile("fence" : : : "memory");
  for (unsigned i = 0; i < 16; ++i)
    if (roundtrip[i] != a[i]) return 1;

  // Weight-stationary, no transpose/shift/activation; both row strides1.
  COMMAND(0, 4ul | (1ul << 16) | (one << 32), 1ul << 48);
  COMMAND(6, tile(16), tile(0x80000000u));
  COMMAND(4, tile(0), 0xfffffffful); // explicit zero bias
  COMMAND(0, 2, (one << 32) | 16); // dense int32 output rows
  COMMAND(3, output, tile(0xa0000000u)); // full-width accumulator readout
  COMMAND(127, 0, 0);
  __asm__ volatile("fence" : : : "memory");
  for (unsigned i = 0; i < 4; ++i)
    for (unsigned j = 0; j < 4; ++j) {
      i32 golden = 0;
      for (unsigned k = 0; k < 4; ++k)
        golden += (i32)a[i * 4 + k] * (i32)b[k * 4 + j];
      if (output[i * 4 + j] != golden) return 2;
    }
  __asm__ volatile("csrr zero, mcycle" : : : "memory");
  print("native primitive probe PASS\n");
  return 0;
}
