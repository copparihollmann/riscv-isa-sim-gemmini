#ifndef SPIKE_TIMING_INTEGER_DIVIDER_TIMING_HPP
#define SPIKE_TIMING_INTEGER_DIVIDER_TIMING_HPP
#include "model.hpp"
#include <set>
#include <stdexcept>

namespace spike_timing {
struct IntegerDividerBound {
  // Request accepted -> response valid. Count 0..64 inclusive, plus at most
  // one input-sign and one output-sign state. Early-out can only shorten this.
  static constexpr merlin_timing::Cycle latency = 65 + 1 + 1;
  // The done state cannot accept a request; assume resp.ready immediately.
  static constexpr merlin_timing::Cycle occupancy = latency + 1;
};
inline std::optional<IntegerDividerBound> integer_divider_bound(const Model &model) {
  const auto selected = model.document.get_child_optional("cpu.integer_divider_service");
  if (!selected) return {};
  const std::set<std::string> expected{"schema", "xlen", "div_unroll", "early_out",
      "early_out_granularity", "response_ready", "rtl_sha256", "source_sha256"};
  std::set<std::string> keys;
  for (const auto &entry : *selected) {
    if (!entry.second.empty()) throw std::invalid_argument("nested divider selection");
    keys.insert(entry.first);
  }
  if (keys != expected || selected->get<std::string>("schema") !=
      "merlin.rocket_integer_divider_service_bound.v1" ||
      selected->get<unsigned>("xlen") != 64 || selected->get<unsigned>("div_unroll") != 1 ||
      !selected->get<bool>("early_out") || selected->get<unsigned>("early_out_granularity") != 1 ||
      selected->get<std::string>("response_ready") != "assumed_immediate" ||
      !is_digest(selected->get<std::string>("rtl_sha256")) ||
      !is_digest(selected->get<std::string>("source_sha256")))
    throw std::invalid_argument("unsupported Rocket integer-divider bound configuration");
  if (model.parameter("cpu.divide.latency_cycles") || model.parameter("cpu.divide.occupancy_cycles"))
    throw std::invalid_argument("divider bound conflicts with explicit divider prices");
  const auto &mappings = model.document.get_child("cpu_execution_resources");
  const auto divide = mappings.find("cpu.divide"), multiply = mappings.find("cpu.multiply");
  if (divide == mappings.not_found() || multiply == mappings.not_found() ||
      divide->second.data() != multiply->second.data())
    throw std::invalid_argument("divider bound requires shared multiply/divide resource");
  const auto id = model.resource(divide->second.data());
  bool single = false;
  for (const auto &resource : model.resources)
    if (id && resource.id == *id) single = resource.capacity == 1 && resource.queue_capacity == 0;
  if (!single) throw std::invalid_argument("divider bound requires one unqueued MulDiv unit");
  return IntegerDividerBound{};
}
} // namespace spike_timing
#endif
