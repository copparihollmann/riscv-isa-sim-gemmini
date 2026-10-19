#ifndef GEMMINI_EXECUTE_INPUT_SERVICE_V1_HPP
#define GEMMINI_EXECUTE_INPUT_SERVICE_V1_HPP

#include "staged.hpp"
#include <timing/provider.hpp>

namespace gemmini_annotated_spike {

// Explicitly selected source-derived input service plus separately fitted mesh
// propagation. Nothing here changes functional state or the original counters.
struct ExecuteInputService {
  std::uint32_t dimension, minimum_rows, reduction_guard_mask;
  double pipeline_cycles, cycles_per_row;
};

inline void validate_execute_input_service(const ExecuteInputService &value) {
  if (!value.dimension || value.dimension > 64 || !value.minimum_rows ||
      value.minimum_rows > value.dimension || value.cycles_per_row != 1 ||
      !std::isfinite(value.pipeline_cycles) || value.pipeline_cycles < 0)
    throw std::invalid_argument("execute input service needs independently checked extent and scalar row service");
}

inline ExecuteInputService read_execute_input_service(spike_timing::Services &services) {
  const auto number = [&](const char *name) {
    const auto value = services.number(std::string("target.execution_service.") + name);
    if (!value || !std::isfinite(*value) || *value < 0)
      throw std::invalid_argument(std::string("missing/invalid execute input service: ") + name);
    return *value;
  };
  const auto integer = [&](const char *name) {
    const auto value = number(name);
    if (std::floor(value) != value || value > std::numeric_limits<std::uint32_t>::max())
      throw std::invalid_argument("execute input service requires bounded integers");
    return static_cast<std::uint32_t>(value);
  };
  if (integer("version") != 1)
    throw std::invalid_argument("unsupported execute input service release");
  ExecuteInputService result{integer("dimension"), integer("minimum_rows"), integer("reduction_guard_mask"),
                             number("pipeline_cycles"), number("cycles_per_row")};
  validate_execute_input_service(result);
  return result;
}

class ExecuteServiceObserver {
public:
  ExecuteServiceObserver(ExecuteInputService pricing, merlin_timing::Engine &engine,
                        StagedConfig config, ValueId state_base,
                        std::function<void(const std::string &)> unresolved = {},
                        ValueId local_base = 0, std::uint32_t scratchpad_rows = 0,
                        std::uint32_t dimension = 0, std::uint32_t accumulator_rows = 0)
      : pricing_(pricing), unresolved_(std::move(unresolved)),
        staged_(engine, config, state_base, unresolved_, local_base, scratchpad_rows,
                dimension, accumulator_rows) {
    validate_execute_input_service(pricing_);
    if (pricing_.dimension != dimension || !config.require_fenced_phases ||
        !config.conservative_local_store_holds)
      throw std::invalid_argument("row service requires selected fenced single-MUL conservative resource semantics");
  }

  Result submit(const std::string &kind, const Event &source, std::optional<Cycle> occupancy,
                std::uint32_t funct, std::uint64_t rs1, std::uint64_t rs2) {
    if (funct == 0 && (rs1 & 3) == 0 && !(rs1 & 128)) {
      ws_ = (rs1 >> 2) & 1;
      a_transpose_ = (rs1 >> 8) & 1;
      b_transpose_ = (rs1 >> 9) & 1;
      configured_ = true;
    }
    auto selected = source;
    if (kind == "compute_ws") {
      last_input_rows_.reset();
      // require_fenced_phases refuses a following PRELOAD before completion.
      // The admitted compute is single-MUL: D is inactive. A/B transposer
      // predicates follow the selected execute configuration.
      if (!configured_ || !ws_) {
        selected.latency.reset();
        occupancy.reset();
        if (unresolved_) unresolved_("execute_service:missing_selected_execute_state");
      } else if (source.latency && occupancy) {
        const auto index = (std::uint32_t(ws_) << 4) | (1u << 3) |
                           (std::uint32_t(a_transpose_) << 2) | std::uint32_t(b_transpose_);
        auto rows = pricing_.dimension;
        if (pricing_.reduction_guard_mask & (1u << index)) {
          const auto a = std::uint32_t(rs1) == 0xffffffffu || a_transpose_ ? 1u :
              std::min<std::uint32_t>(rs1 >> 48, pricing_.dimension);
          const auto b = std::uint32_t(rs2) == 0xffffffffu ? 1u :
              std::min<std::uint32_t>(rs2 >> 48, pricing_.dimension);
          rows = std::max({a, b, pricing_.minimum_rows});
        }
        last_input_rows_ = rows;
        const long double service = static_cast<long double>(rows) * pricing_.cycles_per_row;
        const long double latency = std::ceil(service + pricing_.pipeline_cycles);
        if (latency >= std::ldexp(1.0L, 64)) {
          selected.latency.reset(); occupancy.reset();
          if (unresolved_) unresolved_("execute_service:cycle_overflow");
        } else {
          selected.latency = static_cast<Cycle>(latency);
          occupancy = static_cast<Cycle>(std::ceil(service));
        }
      }
    }
    return staged_.submit(kind, selected, occupancy, funct, rs1, rs2);
  }

  bool pending_preload() const { return staged_.pending_preload(); }
  std::optional<std::uint32_t> last_input_rows() const { return last_input_rows_; }

private:
  ExecuteInputService pricing_;
  std::function<void(const std::string &)> unresolved_;
  StagedObserver staged_;
  bool configured_ = false, ws_ = false, a_transpose_ = false, b_transpose_ = false;
  std::optional<std::uint32_t> last_input_rows_;
};
} // namespace gemmini_annotated_spike
#endif
