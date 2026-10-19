#include "execute_service.hpp"
#include <cassert>

using namespace merlin_timing;
using namespace gemmini_annotated_spike;

static StagedConfig config() {
  StagedConfig c;
  c.reservations = {2, 4, 2}; c.controller_entries = {2, 2, 2}; c.dma_commands = {2, 2};
  c.issue_resources = {0, 1, 2}; c.controller_resources = {3, 4, 5};
  c.issue_latency = 1; c.issue_occupancy = 1; c.require_fenced_phases = true;
  c.conservative_local_store_holds = true; c.scratchpad_bank_rows = 16;
  c.scratchpad_bank_resources = {6, 7, 8, 9}; c.accumulator_storage_resource = 10;
  return c;
}
static std::vector<ResourceSpec> resources() {
  std::vector<ResourceSpec> result;
  for (unsigned i = 0; i < 11; ++i) result.push_back({i, 1, 0});
  return result;
}
static std::uint64_t packet(std::uint32_t address, unsigned rows) {
  return address | (4ull << 32) | (std::uint64_t(rows) << 48);
}

int main() {
  const ExecuteInputService pricing{8, 2, 1u << 24, 5, 1};
  for (const unsigned rows : {0u, 1u, 2u, 3u, 7u, 8u}) {
    Engine engine(256, resources());
    ExecuteServiceObserver target(pricing, engine, config(), 100, {}, 0, 64, 8, 32);
    Event set{0, {}, {}, {}, 1}; target.submit("config", set, 1, 0, 4, 0);
    Event compute{1, {}, {}, {}, 100};
    const auto result = target.submit("compute_ws", compute, 8, 4, packet(0, rows), 0xffffffffu);
    const auto expected = std::max(rows, 2u);
    assert(target.last_input_rows() == expected);
    assert(result.ready && result.start && *result.ready - *result.start == expected + 5);
  }
  // Actual B rows, garbage A, and persistent transpose/stride-only state are
  // independent controls. Geometry and minimum service are selected data.
  {
    Engine engine(256, resources());
    ExecuteServiceObserver target(pricing, engine, config(), 100, {}, 0, 64, 8, 32);
    Event set{0, {}, {}, {}, 1}, event{1, {}, {}, {}, 100};
    target.submit("config", set, 1, 0, 4, 0);
    target.submit("compute_ws", event, 8, 4, 0xffffffffu, packet(16, 7));
    assert(target.last_input_rows() == 7);
  }
  {
    Engine engine(256, resources());
    ExecuteServiceObserver target(pricing, engine, config(), 100, {}, 0, 64, 8, 32);
    Event set{0, {}, {}, {}, 1}, event{1, {}, {}, {}, 100};
    target.submit("config", set, 1, 0, 4 | (1u << 8), 0);
    target.submit("config", set, 1, 0, 128, 0); // preserve transpose
    target.submit("compute_ws", event, 8, 4, packet(0, 1), 0xffffffffu);
    assert(target.last_input_rows() == 8);
  }
  // Unknown original prices or configuration remain unknown, never replaced
  // with a known geometry-derived value.
  for (const bool configure : {false, true}) {
    Engine engine(256, resources()); std::vector<std::string> reasons;
    ExecuteServiceObserver target(pricing, engine, config(), 100,
      [&](const auto &reason) { reasons.push_back(reason); }, 0, 64, 8, 32);
    Event event{0, {}, {}, {}, 1};
    if (configure) target.submit("config", event, 1, 0, 4, 0);
    event.latency.reset();
    assert(!target.submit("compute_ws", event, 8, 4, packet(0, 1), 0xffffffffu).ready);
    assert(!engine.report().complete);
    if (!configure) assert(reasons[0] == "execute_service:missing_selected_execute_state");
  }
  // The old pending-descriptor/fence semantics remain delegated intact.
  {
    Engine engine(256, resources());
    ExecuteServiceObserver target(pricing, engine, config(), 100, {}, 0, 64, 8, 32);
    Event event{0, {}, {}, {}, 1};
    target.submit("config", event, 1, 0, 4, 0);
    target.submit("preload", event, 8, 6, packet(16, 8), 0x80000000u);
    target.submit("fence", event, 0, 127, 0, 0);
    assert(target.pending_preload());
    target.submit("compute_ws", event, 8, 4, packet(0, 1), 0xffffffffu);
    assert(!target.pending_preload());
  }
  {
    Engine engine(256, resources()); auto c = config(); c.require_fenced_phases = false;
    bool refused = false;
    try { ExecuteServiceObserver target(pricing, engine, c, 100, {}, 0, 64, 8, 32); }
    catch (const std::invalid_argument &) { refused = true; }
    assert(refused);
  }
  for (const unsigned field : {0u, 1u, 2u, 3u, 4u}) {
    Engine engine(256, resources()); auto invalid = pricing;
    if (field == 0) invalid.dimension = 65;
    if (field == 1) invalid.minimum_rows = 0;
    if (field == 2) invalid.minimum_rows = 9;
    if (field == 3) invalid.pipeline_cycles = std::numeric_limits<double>::infinity();
    if (field == 4) invalid.cycles_per_row = 0.5;
    bool refused = false;
    try { ExecuteServiceObserver target(invalid, engine, config(), 100, {}, 0, 64, 8, 32); }
    catch (const std::invalid_argument &) { refused = true; }
    assert(refused);
  }
  {
    Engine engine(256, resources()); auto overflow = pricing;
    overflow.pipeline_cycles = std::ldexp(1.0, 64);
    ExecuteServiceObserver target(overflow, engine, config(), 100, {}, 0, 64, 8, 32);
    Event event{0, {}, {}, {}, 1};
    target.submit("config", event, 1, 0, 4, 0);
    assert(!target.submit("compute_ws", event, 8, 4, packet(0, 1), 0xffffffffu).ready);
    assert(!engine.report().complete);
  }
}
