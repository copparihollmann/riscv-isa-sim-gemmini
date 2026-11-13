#pragma once
#include <cstdint>

namespace iris::noc {
// Widths are required elaboration inputs. No board or latency defaults.
struct Parameters {
  unsigned input_virtual_channels;
  unsigned router_input_units;
  unsigned output_virtual_channels;
  unsigned local_input_unit;
};
struct State {
  std::uint64_t input_unit_mask;
  std::uint64_t single_vc_input_mask;
  std::uint64_t islip_output_mask;
};
struct Inputs {
  std::uint64_t waiting_vcs;
  bool incoming_route_fire;
  unsigned incoming_route_vc;
  // These are explicit external boundaries after routing/occupancy filtering.
  std::uint64_t eligible_input_units;
  std::uint64_t selected_eligible_output_vcs;
};
struct Result {
  std::uint64_t selected_vc;
  std::uint64_t input_unit_grants;
  std::uint64_t islip_output_selection;
  std::uint64_t output_vc_grants;
  bool local_request_accepted;
  State next;
};
class Arbiter {
 public:
  Arbiter(Parameters parameters, State initial);
  static State reset_state(); // Source RegInit(0), used only on an actual reset.
  Result preview(const Inputs& inputs) const;
  Result step(const Inputs& inputs);
  const State& state() const { return state_; }
  const Parameters& parameters() const { return parameters_; }
 private:
  Parameters parameters_;
  State state_;
};
} // namespace iris::noc
