#include "integer_divider_timing.hpp"
#include "cpu_decode.hpp"
#include <iostream>
int main(int argc, char **argv) {
  if (argc != 3) return 2;
  const std::string mode(argv[2]);
  try {
    spike_timing::Model model(argv[1]);
    if (mode == "reject") return 1;
    const auto bound = spike_timing::integer_divider_bound(model);
    if (bool(bound) != (mode == "selected")) return 1;
    if (!bound && model.cycles("cpu.divide.latency_cycles")) return 1;
    for (unsigned opcode : {0x33u, 0x3bu}) for (unsigned funct3 : {4u,5u,6u,7u}) {
      const auto decoded = spike_timing::decode_cpu((1u<<25)|(4u<<20)|(3u<<15)|(funct3<<12)|(2u<<7)|opcode);
      if (!decoded.known || std::string(decoded.kind) != "cpu.divide" ||
          decoded.read_count != 2 || decoded.reads[0] != 3 || decoded.reads[1] != 4 ||
          decoded.write_count != 1 || decoded.writes[0] != 2) return 1;
    }
  } catch (const std::exception &e) {
    if (mode == "reject") return 0;
    std::cerr << e.what() << '\n'; return 1;
  }
  return 0;
}
