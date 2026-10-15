#ifndef SPIKE_TIMING_CPU_DECODE_HPP
#define SPIKE_TIMING_CPU_DECODE_HPP

#include <array>
#include <cstdint>

namespace spike_timing {

// One vocabulary supplies both decoder spellings and explicit zero counts.
#define SPIKE_TIMING_CPU_CLASSES(X) \
  X(atomic) \
  X(branch) \
  X(csr) \
  X(custom) \
  X(divide) \
  X(fence) \
  X(fp_add) \
  X(fp_classify) \
  X(fp_compare) \
  X(fp_convert) \
  X(fp_divide) \
  X(fp_fma) \
  X(fp_load) \
  X(fp_minmax) \
  X(fp_move_from_int) \
  X(fp_move_to_int) \
  X(fp_multiply) \
  X(fp_sign) \
  X(fp_sqrt) \
  X(fp_store) \
  X(fp_subtract) \
  X(fp_to_int) \
  X(int_to_fp) \
  X(integer) \
  X(load) \
  X(multiply) \
  X(store) \
  X(system) \
  X(unknown)
struct CpuKinds {
#define SPIKE_TIMING_CPU_NAME(name) static constexpr const char *name = "cpu." #name;
  SPIKE_TIMING_CPU_CLASSES(SPIKE_TIMING_CPU_NAME)
#undef SPIKE_TIMING_CPU_NAME
};
inline constexpr const char *cpu_feature_classes[] = {
#define SPIKE_TIMING_CPU_VALUE(name) CpuKinds::name,
  SPIKE_TIMING_CPU_CLASSES(SPIKE_TIMING_CPU_VALUE)
#undef SPIKE_TIMING_CPU_VALUE
};
#undef SPIKE_TIMING_CPU_CLASSES

// ISA operand classification only. Latencies and microarchitecture are data.
struct CpuInstruction {
  const char *kind = CpuKinds::unknown;
  std::array<std::uint64_t, 4> reads{};
  std::array<std::uint64_t, 2> writes{};
  unsigned read_count = 0, write_count = 0;
  bool known = true, branch = false, fence = false, custom = false;
  bool counter_read = false, icache_fence = false;
  bool floating_register_operands = false;
  unsigned fp_width = 0, fp_source_width = 0;
  // Sticky exception updates commute with one another but must follow prior
  // destructive flag writes. Reading/clearing flags must join pending updates.
  bool reads_rounding_mode = false, reads_fflags = false;
  bool writes_rounding_mode = false, writes_fflags = false;
  bool accumulates_fflags = false;
  void read(unsigned reg, bool floating = false) {
    floating_register_operands = floating_register_operands || floating;
    if (floating || reg) reads.at(read_count++) = reg + (floating ? 32 : 0);
  }
  void write(unsigned reg, bool floating = false) {
    floating_register_operands = floating_register_operands || floating;
    if (floating || reg) writes.at(write_count++) = reg + (floating ? 32 : 0);
  }
};

inline CpuInstruction decode_cpu(std::uint64_t bits) {
  CpuInstruction d;
  const unsigned rd = (bits >> 7) & 31, r1 = (bits >> 15) & 31;
  const unsigned r2 = (bits >> 20) & 31, f3 = (bits >> 12) & 7;
  if ((bits & 3) != 3) {
    const unsigned q = bits & 3, f = (bits >> 13) & 7;
    const unsigned a = 8 + ((bits >> 7) & 7), b = 8 + ((bits >> 2) & 7);
    const unsigned r = (bits >> 2) & 31;
    d.kind = CpuKinds::integer;
    if (q == 0) {
      if (f == 0) { d.read(2); d.write(b); }
      else if (f == 1 || f == 2 || f == 3) {
        d.kind = f == 1 ? CpuKinds::fp_load : CpuKinds::load;
        d.read(a); d.write(b, f == 1);
        if (f == 1) d.fp_width = 64;
      } else if (f == 5 || f == 6 || f == 7) {
        d.kind = f == 5 ? CpuKinds::fp_store : CpuKinds::store;
        d.read(a); d.read(b, f == 5);
        if (f == 5) d.fp_width = 64;
      } else d.known = false;
    } else if (q == 1) {
      if (f == 0 || f == 1) { d.read(rd); d.write(rd); }
      else if (f == 2) d.write(rd);
      else if (f == 3) { if (rd == 2) d.read(2); d.write(rd); }
      else if (f == 4) {
        d.read(a); d.write(a);
        if (((bits >> 10) & 3) == 3) d.read(b);
      } else {
        d.kind = CpuKinds::branch; d.branch = true;
        if (f == 6 || f == 7) d.read(a);
      }
    } else if (q == 2) {
      if (f == 0) { d.read(rd); d.write(rd); }
      else if (f == 1 || f == 2 || f == 3) {
        d.kind = f == 1 ? CpuKinds::fp_load : CpuKinds::load;
        d.read(2); d.write(rd, f == 1);
        if (f == 1) d.fp_width = 64;
      } else if (f == 4) {
        if (!r) {
          if (rd == 0 && ((bits >> 12) & 1)) d.kind = CpuKinds::system;
          else {
            d.kind = CpuKinds::branch; d.branch = true; d.read(rd);
            if ((bits >> 12) & 1) d.write(1);
          }
        } else {
          if ((bits >> 12) & 1) d.read(rd);
          d.read(r); d.write(rd);
        }
      } else if (f == 5 || f == 6 || f == 7) {
        d.kind = f == 5 ? CpuKinds::fp_store : CpuKinds::store;
        d.read(2); d.read(r, f == 5);
        if (f == 5) d.fp_width = 64;
      } else d.known = false;
    } else d.known = false;
    return d;
  }
  if ((bits & 31) == 31) { d.known = false; return d; }
  const unsigned op = bits & 127, f7 = (bits >> 25) & 127;
  switch (op) {
  case 0x37: case 0x17: d.kind = CpuKinds::integer; d.write(rd); break;
  case 0x13: case 0x1b:
    d.kind = CpuKinds::integer; d.read(r1); d.write(rd); break;
  case 0x33: case 0x3b:
    d.kind = f7 == 1 ? (f3 < 4 ? CpuKinds::multiply : CpuKinds::divide) : CpuKinds::integer;
    d.read(r1); d.read(r2); d.write(rd); break;
  case 0x03:
    d.kind = CpuKinds::load; d.read(r1); d.write(rd); break;
  case 0x07:
    if (f3 != 2 && f3 != 3) { d.known = false; break; }
    d.kind = CpuKinds::fp_load; d.fp_width = f3 == 2 ? 32 : 64;
    d.read(r1); d.write(rd, true); break;
  case 0x23:
    d.kind = CpuKinds::store; d.read(r1); d.read(r2); break;
  case 0x27:
    if (f3 != 2 && f3 != 3) { d.known = false; break; }
    d.kind = CpuKinds::fp_store; d.fp_width = f3 == 2 ? 32 : 64;
    d.read(r1); d.read(r2, true); break;
  case 0x63:
    d.kind = CpuKinds::branch; d.branch = true; d.read(r1); d.read(r2); break;
  case 0x6f: case 0x67:
    d.kind = CpuKinds::branch; d.branch = true; d.write(rd);
    if (op == 0x67) d.read(r1);
    break;
  case 0x0f:
    d.kind = CpuKinds::fence; d.fence = true; d.icache_fence = f3 == 1; break;
  case 0x73: {
    d.kind = CpuKinds::system;
    if (f3) {
      if (f3 == 4) { d.known = false; break; }
      d.kind = CpuKinds::csr; d.write(rd);
      if (f3 < 4) d.read(r1);
      const auto csr = (bits >> 20) & 4095;
      d.counter_read = (f3 == 2 || f3 == 3) && !r1 &&
                       (csr == 0xc00 || csr == 0xb00);
      if (csr >= 1 && csr <= 3) {
        const bool read = (f3 != 1 && f3 != 5) || rd != 0;
        const bool write = f3 == 1 || f3 == 5 || r1 != 0;
        d.reads_fflags = read && (csr == 1 || csr == 3);
        d.reads_rounding_mode = read && (csr == 2 || csr == 3);
        d.writes_fflags = write && (csr == 1 || csr == 3);
        d.writes_rounding_mode = write && (csr == 2 || csr == 3);
      }
    }
    break;
  }
  case 0x43: case 0x47: case 0x4b: case 0x4f:
    if (((bits >> 25) & 3) > 1 || (f3 >= 5 && f3 != 7)) {
      d.known = false; break;
    }
    d.kind = CpuKinds::fp_fma; d.fp_width = ((bits >> 25) & 1) ? 64 : 32;
    d.read(r1, true); d.read(r2, true); d.read((bits >> 27) & 31, true);
    d.write(rd, true); d.reads_rounding_mode = f3 == 7;
    d.accumulates_fflags = true; break;
  case 0x53: {
    // Only scalar S/D formats and standard operand forms are admitted here.
    // Other extensions must acquire their own decoded operands and prices.
    const auto rounding = [&] {
      if (f3 >= 5 && f3 != 7) d.known = false;
      d.reads_rounding_mode = f3 == 7;
      d.accumulates_fflags = true;
    };
    switch (f7) {
    case 0: case 1: case 4: case 5: case 8: case 9: case 12: case 13:
      d.kind = f7 < 4 ? CpuKinds::fp_add : f7 < 8 ? CpuKinds::fp_subtract :
               f7 < 12 ? CpuKinds::fp_multiply : CpuKinds::fp_divide;
      d.read(r1, true); d.read(r2, true); d.write(rd, true); rounding(); break;
    case 44: case 45:
      if (r2 != 0) { d.known = false; break; }
      d.kind = CpuKinds::fp_sqrt; d.read(r1, true); d.write(rd, true); rounding(); break;
    case 16: case 17:
      if (f3 > 2) { d.known = false; break; }
      d.kind = CpuKinds::fp_sign; d.read(r1, true); d.read(r2, true); d.write(rd, true); break;
    case 20: case 21:
      if (f3 > 1) { d.known = false; break; }
      d.kind = CpuKinds::fp_minmax; d.read(r1, true); d.read(r2, true); d.write(rd, true);
      d.accumulates_fflags = true; break;
    case 32: case 33:
      if (r2 != (f7 == 32 ? 1u : 0u)) { d.known = false; break; }
      d.kind = CpuKinds::fp_convert; d.fp_source_width = r2 == 0 ? 32 : 64;
      d.read(r1, true); d.write(rd, true); rounding(); break;
    case 80: case 81:
      if (f3 > 2) { d.known = false; break; }
      d.kind = CpuKinds::fp_compare; d.read(r1, true); d.read(r2, true); d.write(rd);
      d.accumulates_fflags = true; break;
    case 96: case 97:
      if (r2 > 3) { d.known = false; break; }
      d.kind = CpuKinds::fp_to_int; d.read(r1, true); d.write(rd); rounding(); break;
    case 104: case 105:
      if (r2 > 3) { d.known = false; break; }
      d.kind = CpuKinds::int_to_fp; d.read(r1); d.write(rd, true); rounding(); break;
    case 112: case 113:
      if (r2 != 0 || f3 > 1) { d.known = false; break; }
      d.kind = f3 == 0 ? CpuKinds::fp_move_to_int : CpuKinds::fp_classify;
      d.read(r1, true); d.write(rd); break;
    case 120: case 121:
      if (r2 != 0 || f3 != 0) { d.known = false; break; }
      d.kind = CpuKinds::fp_move_from_int; d.read(r1); d.write(rd, true); break;
    default: d.known = false;
    }
    if (d.known) d.fp_width = (f7 & 1) ? 64 : 32;
    break;
  }
  case 0x2f:
    d.kind = CpuKinds::atomic; d.read(r1); d.read(r2); d.write(rd); break;
  case 0x0b: case 0x2b: case 0x5b: case 0x7b:
    d.kind = CpuKinds::custom; d.custom = true;
    if ((bits >> 13) & 1) d.read(r1);
    if ((bits >> 12) & 1) d.read(r2);
    if ((bits >> 14) & 1) d.write(rd);
    break;
  default: d.known = false;
  }
  return d;
}

} // namespace spike_timing
#endif
