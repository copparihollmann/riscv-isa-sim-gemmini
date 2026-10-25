#include "memory.hpp"
#include <cassert>
#include <iostream>
#include <map>
using namespace spike_timing;
int main(int argc, char **argv) {
  assert(argc == 3);
  const std::string mode = argv[2];
  try {
    Model model(argv[1]); merlin_timing::Engine engine(model.max_values, model.resources);
    merlin_timing::ValueId next = 0;
    std::map<std::string, std::uint64_t> counts; unsigned unknown = 0;
    MemorySystem memory(model, engine, [&](std::size_t n) { auto id = next; next += n; return id; },
      [&](const std::string &key, std::uint64_t n) { counts[key] += n; },
      [&](const std::string &) { ++unknown; });
    assert(mode != "reject");
    for (unsigned repeat = 0; repeat < 2; ++repeat) {
      // Cross-line overlapping intervals cover exactly 24 distinct bytes.
      auto effects = memory.access({{0x1000, 12, false}, {0x1004, 12, false},
                                    {0x1008, 16, false}}, "cpu_data");
      std::uint64_t selected = 0;
      for (const auto &demand : effects.demands)
        if (demand.resource == 3) { assert(demand.occupancy); selected += *demand.occupancy; }
      if (mode == "selected") assert(selected == 12);
      else if (mode == "lower") assert(selected == (repeat ? 0 : 16));
      else assert(selected == 0);
      assert(effects.latency);
    }
    if (mode == "lower") {
      assert(counts["modeled.cache.l2.boundary_bytes"] == 32);
      assert(unknown == 0);
    } else if (mode == "selected") {
      assert(counts["modeled.cache.l1.boundary_bytes"] == 48);
      memory.access({{~std::uint64_t(0) - 7, 8, false}}, "cpu_data");
      assert(unknown > 0);
    } else {
      assert(!counts.count("modeled.cache.l1.boundary_bytes"));
      assert(unknown == 0);
    }
  } catch (const std::exception &) {
    assert(mode == "reject");
  }
  std::cout << "cache byte service " << mode << " passed\n";
}
