// Optional adapter to the generic Spike timing plugin ABI. This translation
// unit can be loaded separately beside the unchanged functional extension.
#include "provider.hpp"
#include <timing/provider.hpp>

#include <memory>
#include <set>

namespace {
namespace G = gemmini_annotated_spike;
using spike_timing::Services;

struct CounterFeature {
  const char *name;
  std::uint64_t G::Counters::*member;
};
constexpr CounterFeature counter_features[] = {
    {"commands", &G::Counters::commands_total}, {"fences", &G::Counters::fences},
    {"requested_read_bytes", &G::Counters::requested_read_bytes},
    {"requested_write_bytes", &G::Counters::requested_write_bytes},
    {"local_read_bytes", &G::Counters::local_read_bytes}, {"local_write_bytes", &G::Counters::local_write_bytes},
    {"nominal_padded_macs", &G::Counters::nominal_padded_macs}, {"useful_shape_macs", &G::Counters::useful_shape_macs},
    {"zero_fill_elements", &G::Counters::zero_fill_elements}, {"pooled_outputs", &G::Counters::pooled_outputs},
    {"semantic_unknown_events", &G::Counters::semantic_unknown_events}, {"illegal_events", &G::Counters::illegal_events}};

std::uint32_t integer(Services &s, const std::string &name) {
  const auto value = s.number("target.hardware." + name);
  if (!value || !std::isfinite(*value) || *value < 0 || std::floor(*value) != *value ||
      *value > std::numeric_limits<std::uint32_t>::max())
    throw std::invalid_argument("missing or invalid target hardware fact: " + name);
  return static_cast<std::uint32_t>(*value);
}

G::HardwareConfig hardware(Services &s) {
  const auto first = integer(s, "first_layer_optimizations");
  const auto full = integer(s, "full_width_accumulator_readout");
  if (first > 1 || full > 1) throw std::invalid_argument("invalid target feature fact");
  std::optional<std::uint8_t> activation;
  const auto selected = s.number("target.hardware.reset_accumulator_activation");
  if (selected) {
    if (!std::isfinite(*selected) || *selected < 0 || *selected > 4 || std::floor(*selected) != *selected)
      throw std::invalid_argument("invalid reset activation fact");
    activation = static_cast<std::uint8_t>(*selected);
  }
  return {integer(s, "dim"), integer(s, "scratchpad_rows"), integer(s, "accumulator_rows"),
          integer(s, "element_bytes"), integer(s, "accumulator_bytes"), integer(s, "address_bits"),
          bool(first), bool(full), activation};
}

G::Parameters parameters(Services &s) {
  G::Parameters result;
  for (const auto *kind : G::priced_primitive_classes)
    for (const auto *field : {"latency_cycles", "occupancy_cycles", "latency_per_byte_cycles",
                             "occupancy_per_byte_cycles", "latency_per_mac_cycles", "occupancy_per_mac_cycles"}) {
      const auto key = std::string(kind) + "." + field;
      if (const auto value = s.number("target.prices." + key)) result[key] = *value;
    }
  for (const auto *field : {"dma.read_bytes_per_cycle", "dma.write_bytes_per_cycle"})
    if (const auto value = s.number(std::string("target.prices.") + field)) result[field] = *value;
  return result;
}

G::ResourceBindings resources(Services &s) {
  const auto selected = [&](const std::string &name) -> std::optional<merlin_timing::ResourceId> {
    try { return s.resource("accelerator." + name); }
    catch (const std::exception &) {
      s.unresolved("missing_target_resource:" + name);
      return {};
    }
  };
  // Shared memory owns DMA reservations; standalone-only DMA bindings are not
  // requested, and their absence cannot taint a valid integrated observation.
  return {selected("config"), selected("load"), selected("store"), selected("execute"), {}, {}};
}

struct Inputs {
  G::HardwareConfig hardware;
  G::Parameters parameters;
  G::ResourceBindings resources;
  merlin_timing::ValueId tokens;
  std::uint32_t opcode, opcode_mask;
};

class Provider final : public spike_timing::TargetProvider {
public:
  Provider(Services services, Inputs inputs)
      : services_(std::move(services)), opcode_(inputs.opcode), opcode_mask_(inputs.opcode_mask),
        observer_(services_.engine, inputs.hardware, std::move(inputs.parameters),
          inputs.resources, inputs.tokens, [this](merlin_timing::View<G::Transfer> transfers) {
            std::vector<spike_timing::MemoryEffect> rows;
            for (std::size_t i = 0; i < transfers.size; ++i) {
              const auto &transfer = transfers[i];
              for (std::uint64_t row = 0; row < transfer.rows; ++row)
                rows.push_back({transfer.address + row * transfer.row_stride, transfer.row_bytes, transfer.write});
            }
            const auto effects = services_.memory(rows);
            return G::TransferEffects{effects.reads, effects.writes, effects.demands, effects.latency};
          }) {
    for (const auto &counter : counter_features) services_.feature(std::string("target.") + counter.name, 0);
    services_.feature("target.foreign_custom_opcode", 0);
    services_.feature("target.custom_counter_result_unknown", 0);
    for (const auto *kind : G::priced_primitive_classes) services_.feature(std::string("target.class.") + kind, 0);
    for (const auto *kind : G::diagnostic_primitive_classes) services_.feature(std::string("target.class.") + kind, 0);
  }

  merlin_timing::Result command(std::uint64_t pc, std::uint64_t bits, std::uint64_t rs1,
                                std::uint64_t rs2, merlin_timing::Cycle earliest) override {
    if ((bits & opcode_mask_) != opcode_) {
      count_errors_.insert("foreign_custom_opcode");
      services_.unresolved("foreign_custom_opcode");
      services_.feature("target.foreign_custom_opcode", 1);
      merlin_timing::Event unknown;
      unknown.earliest = earliest;
      return services_.engine.submit(unknown);
    }
    // Pinned rocc_insn_t places xs2 after opcode[6:0] + rd[4:0],
    // followed by xs1. libgemmini passes all-ones for a disabled operand.
    if (!(bits & (1ull << 13))) rs1 = std::numeric_limits<std::uint64_t>::max();
    if (!(bits & (1ull << 12))) rs2 = std::numeric_limits<std::uint64_t>::max();
    // The functional extension supplies a dummy/random custom counter return.
    // It cannot qualify control/data that depends on a hardware counter result.
    if (((bits >> 25) & 127) == 126 && (bits & (1ull << 14))) {
      count_errors_.insert("custom_counter_result_not_hardware_equivalent");
      services_.unresolved("custom_counter_result_not_hardware_equivalent");
      services_.feature("target.custom_counter_result_unknown", 1);
      merlin_timing::Event unknown;
      unknown.earliest = earliest;
      return services_.engine.submit(unknown);
    }
    const auto result = observer_.observe_command(pc, (bits >> 25) & 127, rs1, rs2, earliest);
    features();
    return result;
  }
  void fence(merlin_timing::Cycle earliest) override {
    observer_.observe_fence(earliest);
    features();
  }
  spike_timing::FeatureObservationStatus feature_status() const {
    auto reasons = count_errors_;
    for (const auto &entry : observer_.unknown_semantics()) reasons.insert("target:" + entry.first);
    if (observer_.counters().accounting_overflow) reasons.insert("target_counter_overflow");
    if (observer_.counters().illegal_events) reasons.insert("target_illegal_events");
    return {reasons.empty(), {reasons.begin(), reasons.end()}};
  }

private:
  Services services_; // Own callback closures for the complete provider lifetime.
  std::uint32_t opcode_, opcode_mask_;
  G::TargetObserver observer_;
  G::Counters previous_{};
  std::map<std::string, std::uint64_t> previous_classes_;
  std::set<std::string> reported_unknowns_;
  std::set<std::string> count_errors_;

  void features() {
    const auto &now = observer_.counters();
    const auto feature = [&](const char *name, std::uint64_t current, std::uint64_t previous) {
      if (current > previous) services_.feature(std::string("target.") + name, current - previous);
    };
    for (const auto &counter : counter_features)
      feature(counter.name, now.*counter.member, previous_.*counter.member);
    for (const auto &entry : observer_.primitive_classes()) {
      if (!G::registered_primitive_class(entry.first)) {
        count_errors_.insert("unregistered_target_primitive_class");
        services_.unresolved("unregistered_target_primitive_class");
        continue;
      }
      auto &before = previous_classes_[entry.first];
      if (entry.second > before) services_.feature("target.class." + entry.first, entry.second - before);
      before = entry.second;
    }
    for (const auto *reasons : {&observer_.unknown_semantics(), &observer_.unknown_timing()})
      for (const auto &entry : *reasons)
        if (reported_unknowns_.insert(entry.first).second) services_.unresolved("target:" + entry.first);
    if (now.accounting_overflow && !previous_.accounting_overflow) services_.unresolved("target_counter_overflow");
    previous_ = now;
  }
};
} // namespace

extern "C" spike_timing::TargetProvider *spike_timing_create_provider_v1(spike_timing::Services *services) {
  if (!services) return nullptr;
  try {
    auto h = hardware(*services);
    const auto opcode = integer(*services, "custom_opcode");
    const auto mask = integer(*services, "custom_opcode_mask");
    if (!mask || mask > 127 || (opcode & ~mask)) throw std::invalid_argument("invalid target custom opcode fact");
    Inputs inputs{h, parameters(*services), resources(*services),
                  services->allocate_tokens(G::TargetObserver::required_tokens(h)), opcode, mask};
    return new Provider(*services, std::move(inputs));
  } catch (const std::exception &error) {
    services->unresolved(std::string("target_provider_configuration:") + error.what());
    return nullptr;
  }
}

extern "C" spike_timing::FeatureObservationStatus
spike_timing_provider_feature_observation_v1(const spike_timing::TargetProvider *provider) {
  const auto selected = dynamic_cast<const Provider *>(provider);
  if (!selected) return {false, {"feature observation belongs to a different provider"}};
  return selected->feature_status();
}
