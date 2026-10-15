#include <timing/provider.hpp>
#include <cassert>
#include <iostream>
#include <map>
#include <set>

extern "C" spike_timing::TargetProvider *spike_timing_create_provider_v1(spike_timing::Services *);

int main() {
  merlin_timing::Engine engine(128, {{0, 1, 4}, {1, 1, 4}, {2, 1, 4}, {3, 1, 4}, {4, 1, 4}, {5, 1, 4}});
  std::map<std::string, double> values{
      {"target.hardware.dim", 4}, {"target.hardware.scratchpad_rows", 64},
      {"target.hardware.accumulator_rows", 32}, {"target.hardware.element_bytes", 1},
      {"target.hardware.accumulator_bytes", 4}, {"target.hardware.address_bits", 32},
      {"target.hardware.custom_opcode", 123}, {"target.hardware.custom_opcode_mask", 127},
      {"target.hardware.first_layer_optimizations", 1}, {"target.hardware.full_width_accumulator_readout", 1},
      {"target.hardware.reset_accumulator_activation", 0}};
  for (const auto *kind : {"config", "load", "store", "fence", "counter"})
    for (const auto *field : {"latency_cycles", "occupancy_cycles", "latency_per_byte_cycles",
                             "occupancy_per_byte_cycles"})
      values[std::string("target.prices.") + kind + "." + field] = 1;
  std::map<std::string, unsigned> resources{{"accelerator.config", 0}, {"accelerator.load", 1},
      {"accelerator.store", 2}, {"accelerator.execute", 3}, {"accelerator.dma_read", 4}, {"accelerator.dma_write", 5}};
  std::map<std::string, std::uint64_t> features;
  std::set<std::string> registered;
  bool registration_done = false;
  std::vector<std::string> unresolved;
  unsigned memory_calls = 0;
  std::set<std::string> queried_prices;
  spike_timing::Services services{
      engine,
      [&](const std::string &name) -> std::optional<double> {
        if (name.find("target.prices.") == 0) queried_prices.insert(name);
        const auto found = values.find(name);
        return found == values.end() ? std::optional<double>{} : found->second;
      },
      [&](const std::string &name) { return resources.at(name); },
      [&](std::size_t count) -> merlin_timing::ValueId { assert(count == 107); return 0; },
      [&](const std::vector<spike_timing::MemoryEffect> &effects) {
        ++memory_calls;
        if (memory_calls == 3) {
          assert(effects.size() == 1 && effects[0].bytes == 1);
          assert(effects[0].address == std::numeric_limits<std::uint64_t>::max());
          return spike_timing::SharedEffects{{120}, {}, {{4, 1, 1}}, 1};
        }
        assert(effects.size() == 2 && effects[0].bytes == 4);
        assert(effects[1].address == effects[0].address + 8);
        spike_timing::SharedEffects result;
        (effects[0].write ? result.writes : result.reads).push_back(120);
        result.demands.push_back({4, 1, 2}); result.latency = 5;
        return result;
      },
      [&](const std::string &name, std::uint64_t amount) {
        if (!registration_done) {
          assert(amount == 0 && registered.insert(name).second);
        } else assert(registered.count(name));
        features[name] += amount;
      },
      [&](const std::string &reason) { unresolved.push_back(reason); }};
  std::unique_ptr<spike_timing::TargetProvider> provider(spike_timing_create_provider_v1(&services));
  assert(provider);
  std::set<std::string> expected{
      "target.commands", "target.fences", "target.requested_read_bytes", "target.requested_write_bytes",
      "target.local_read_bytes", "target.local_write_bytes", "target.nominal_padded_macs", "target.useful_shape_macs",
      "target.zero_fill_elements", "target.pooled_outputs", "target.semantic_unknown_events", "target.illegal_events",
      "target.foreign_custom_opcode", "target.custom_counter_result_unknown"};
  for (const auto *kind : {"config", "preload", "flush", "counter", "fence", "load", "store", "pool_store",
                          "normalize1", "normalize2", "normalize3", "normalize4", "normalize5", "normalize6", "normalize7",
                          "compute_ws", "compute_os", "compute_ws_relu", "compute_os_relu",
                          "store_act1", "store_act2", "store_act3", "store_act4", "pool_store_act1", "unknown", "compute"})
    expected.insert(std::string("target.class.") + kind);
  assert(registered == expected && features.size() == 40);
  for (const auto &entry : features) assert(entry.second == 0);
  registration_done = true;
  // The adapter owns copies of service closures, not the factory argument.
  services.memory = {};
  const auto enabled = 123ull | 1ull << 13 | 1ull << 12;
  provider->command(4, enabled, 1 | 4ull << 16, 8, 0);
  provider->command(8, enabled, 2, 8, 1);
  const auto packet = 4ull << 32 | 2ull << 48;
  assert(provider->command(12, 2ull << 25 | enabled, 0x1000, packet, 2).ready);
  assert(provider->command(16, 3ull << 25 | enabled, 0x2000, packet, 3).ready);
  provider->fence(4);
  assert(memory_calls == 2 && engine.report().complete && unresolved.empty());
  assert(features["target.commands"] == 4 && features["target.fences"] == 1);
  assert(features["target.requested_read_bytes"] == 8 && features["target.requested_write_bytes"] == 8);
  assert(features["target.class.load"] == 1 && features["target.class.store"] == 1);
  assert(features.at("target.zero_fill_elements") == 0 && features.at("target.class.pool_store") == 0);
  assert(!features.count("target.not_implemented") && !features.count("target.class.normalize8"));
  assert(provider->command(18, 126ull << 25 | enabled, 0, 0, 4).ready);
  assert(features["target.class.counter"] == 1); // side-effect-only counter command has a price
  assert(!provider->command(19, 126ull << 25 | enabled | 1ull << 14, 0, 0, 4).ready);
  assert(features["target.custom_counter_result_unknown"] == 1);
  assert(unresolved.back() == "custom_counter_result_not_hardware_equivalent");
  assert(provider->command(20, 2ull << 25 | 123 | 1ull << 12, 0, 1ull << 32 | 1ull << 48, 5).ready);
  assert(memory_calls == 3); // disabled xs1 selects all-ones, not raw XPR zero
  assert(!provider->command(24, 2ull << 25 | 123 | 1ull << 13, 0, packet, 6).ready);
  assert(memory_calls == 3); // disabled xs2 selects an invalid all-ones packet, not raw XPR geometry
  assert(!provider->command(28, 2ull << 25 | 11, 0x1000, packet, 7).ready);
  assert(features["target.commands"] == 7 && features["target.foreign_custom_opcode"] == 1);
  assert(memory_calls == 3 && !engine.report().complete);
  values.erase("target.hardware.dim");
  assert(!spike_timing_create_provider_v1(&services));
  assert(!unresolved.empty());
  assert(!spike_timing_create_provider_v1(nullptr));
  for (const auto &key : queried_prices) std::cout << "price-query:" << key << '\n';
}
