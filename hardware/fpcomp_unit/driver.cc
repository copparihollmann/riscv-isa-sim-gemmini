#include "VFPComp.h"
#include <verilated.h>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

// Hex strings name whole little-endian packed vectors as unsigned integers.
template<class T> void unpack(T& dst, const std::string& text) {
  if (text.size() != FP_DLEN / 4) throw std::runtime_error("bad vector width");
  for (unsigned i = 0; i < FP_DLEN / 32; ++i)
    dst[i] = std::stoul(text.substr(text.size() - 8 * (i + 1), 8), nullptr, 16);
}
template<class T> void print_vector(const T& src) {
  for (int i = FP_DLEN / 32 - 1; i >= 0; --i)
    std::cout << std::hex << std::setw(8) << std::setfill('0') << uint32_t(src[i]);
  std::cout << std::dec;
}

int main(int argc, char** argv) {
  try {
    Verilated::commandArgs(argc, argv);
    VFPComp top;
    top.clock = 0;
    top.io_pipe_0_valid = top.io_pipe_1_valid = 0;
    top.eval();
    unsigned id, v0, v1, f6, f3, sew, eew1, eewd, rs1, rs2, eidx, eg;
    uint64_t wmask;
    std::string a, b;
    while (std::cin >> id >> v0 >> v1 >> f6 >> f3 >> sew >> eew1 >> eewd
                    >> rs1 >> rs2 >> eidx >> eg >> wmask >> a >> b) {
      top.clock = 0;
      top.io_pipe_0_valid = v0;
      top.io_pipe_0_bits_funct6 = f6;
      top.io_pipe_0_bits_funct3 = f3;
      top.io_pipe_0_bits_sew = sew;
      top.io_pipe_0_bits_rvs1_eew = eew1;
      top.io_pipe_0_bits_rvd_eew = eewd;
      top.io_pipe_0_bits_rs1 = rs1;
      top.io_pipe_0_bits_rs2 = rs2;
      unpack(top.io_pipe_0_bits_rvs2_data, a);
      unpack(top.io_pipe_0_bits_rvs1_data, b);
      top.io_pipe_1_valid = v1;
      // Stage 1 metadata is independent of current stage 0 input.
      top.io_pipe_1_bits_eidx = eidx;
      top.io_pipe_1_bits_wvd_eg = eg;
      top.io_pipe_1_bits_wmask = wmask;
      // eew1/eewd below are supplied separately at the end of each row.
      unsigned stage1_eew1, stage1_eewd;
      if (!(std::cin >> stage1_eew1 >> stage1_eewd))
        throw std::runtime_error("truncated stage1 metadata");
      top.io_pipe_1_bits_rvs1_eew = stage1_eew1;
      top.io_pipe_1_bits_rvd_eew = stage1_eewd;
      top.eval();
      std::cout << id << ' ' << unsigned(top.io_write_valid) << ' '
                << unsigned(top.io_set_fflags_valid) << ' '
                << unsigned(top.io_write_bits_eg) << ' ';
      print_vector(top.io_write_bits_data);
      std::cout << ' ';
      print_vector(top.io_write_bits_mask);
      std::cout << ' ' << unsigned(top.io_set_fflags_bits) << '\n';
      top.clock = 1;
      top.eval();
    }
    if (!std::cin.eof()) throw std::runtime_error("malformed input row");
    top.final();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
