#include "kernels.h"
#include <riscv_vector.h>

/* Runtime VL: no fixed VLEN or assumption that LMUL increases DLEN. */
__attribute__((noinline))
uint64_t roof_kernel(unsigned kind, unsigned char *a, unsigned char *b,
                     unsigned char *c, size_t bytes, unsigned repeats,
                     size_t pitch, size_t rows) {
  uint32_t sum = 0;
  if (kind == CHASE) {
    uintptr_t p = (uintptr_t)a;
    uint64_t checksum = 0;
    size_t loads = bytes / 64 * repeats;
    /* Add/branch are deliberately included in dependent-load latency. */
    __asm__ volatile("1: ld %0,0(%0)\nadd %1,%1,%0\naddi %2,%2,-1\nbnez %2,1b"
        : "+r"(p), "+r"(checksum), "+r"(loads) :: "memory");
    return p == (uintptr_t)a ? checksum : UINT64_MAX;
  }
  for (unsigned pass = 0; pass < repeats; ++pass) {
    if (kind == SCALAR_SUM) {
      const volatile uint32_t *p = (const volatile uint32_t *)a;
      for (size_t i = 0; i < bytes / 4; ++i) sum += p[i];
    } else if (kind == READ_SUM || kind == PANEL) {
      const size_t vlmax = __riscv_vsetvlmax_e32m4();
      vuint32m4_t acc = __riscv_vmv_v_x_u32m4(0, vlmax);
      const size_t count = kind == PANEL ? rows : 1;
      for (size_t row = 0; row < count; ++row) {
        const uint32_t *p = (const uint32_t *)(a + row * pitch);
        size_t left = bytes / 4;
        while (left) {
          size_t vl = __riscv_vsetvl_e32m4(left);
          vuint32m4_t x = __riscv_vle32_v_u32m4(p, vl);
          /* Preserve accumulated tail lanes across short final vectors. */
          acc = __riscv_vadd_vv_u32m4_tu(acc, acc, x, vl);
          p += vl; left -= vl;
        }
      }
      vuint32m1_t zero = __riscv_vmv_v_x_u32m1(0, 1);
      sum += __riscv_vmv_x_s_u32m1_u32(
          __riscv_vredsum_vs_u32m4_u32m1(acc, zero, vlmax));
    } else if (kind == TRIAD) {
      const uint32_t *pa = (uint32_t *)a, *pb = (uint32_t *)b;
      uint32_t *pc = (uint32_t *)c;
      size_t left = bytes / 4;
      while (left) {
        size_t vl = __riscv_vsetvl_e32m4(left);
        vuint32m4_t va = __riscv_vle32_v_u32m4(pa, vl);
        vuint32m4_t vb = __riscv_vle32_v_u32m4(pb, vl);
        vuint32m4_t out = __riscv_vadd_vv_u32m4(
            va, __riscv_vmul_vx_u32m4(vb, 3, vl), vl);
        __riscv_vse32_v_u32m4(pc, out, vl);
        pa += vl; pb += vl; pc += vl; left -= vl;
      }
    } else {
      size_t left = bytes;
      unsigned char *pa = a, *pc = c;
      while (left) {
        size_t vl = __riscv_vsetvl_e8m4(left);
        vuint8m4_t x = kind == COPY ? __riscv_vle8_v_u8m4(pa, vl)
                                  : __riscv_vmv_v_x_u8m4(0x3c, vl);
        __riscv_vse8_v_u8m4(pc, x, vl);
        pa += vl; pc += vl; left -= vl;
      }
    }
  }
  return sum;
}
