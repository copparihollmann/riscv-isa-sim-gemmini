#include "noc_arbiter.hpp"
#include <stdexcept>
#include <string>

namespace iris::noc {
namespace {
std::uint64_t width_mask(unsigned width) {
  if (width == 0 || width > 63)
    throw std::invalid_argument("NoC component represents explicit widths1..63 only");
  return (std::uint64_t{1} << width) - 1;
}
void fits(std::uint64_t value, unsigned width, const char* name) {
  if ((value & ~width_mask(width)) != 0)
    throw std::invalid_argument(std::string("NoC out-of-width ") + name);
}
std::uint64_t rr(std::uint64_t requests, std::uint64_t mask) {
  const auto eligible = requests & ~mask;
  const auto selected = eligible != 0 ? eligible : requests;
  return selected & (~selected + 1);
}
std::uint64_t advance(std::uint64_t mask, std::uint64_t selected) {
  return selected != 0 ? (selected << 1) - 1 : mask;
}
} // namespace
Arbiter::Arbiter(Parameters p, State s) : parameters_(p), state_(s) {
  width_mask(p.input_virtual_channels);
  width_mask(p.router_input_units);
  width_mask(p.output_virtual_channels);
  if (p.local_input_unit >= p.router_input_units)
    throw std::invalid_argument("NoC local input index outside elaborated router");
  fits(s.input_unit_mask, p.input_virtual_channels, "input-unit mask");
  fits(s.single_vc_input_mask, p.router_input_units, "single-VC input mask");
  fits(s.islip_output_mask, p.output_virtual_channels, "ISLIP output mask");
}
State Arbiter::reset_state() { return {0,0,0}; }
Result Arbiter::preview(const Inputs& i) const {
  fits(i.waiting_vcs, parameters_.input_virtual_channels, "waiting VCs");
  fits(i.eligible_input_units, parameters_.router_input_units, "eligible inputs");
  fits(i.selected_eligible_output_vcs, parameters_.output_virtual_channels, "eligible outputs");
  if (i.incoming_route_fire && i.incoming_route_vc >= parameters_.input_virtual_channels)
    throw std::invalid_argument("NoC routed VC outside elaborated input");
  if ((i.eligible_input_units == 0) != (i.selected_eligible_output_vcs == 0))
    throw std::invalid_argument("NoC external selected-output eligibility inconsistent with input winner");
  if ((i.eligible_input_units & (std::uint64_t{1} << parameters_.local_input_unit)) != 0 && i.waiting_vcs == 0)
    throw std::invalid_argument("NoC local eligibility has no ready VC request");
  Result r{};
  r.selected_vc = rr(i.waiting_vcs, state_.input_unit_mask);
  // InputUnit.scala250..260: a valid attempt advances even if request.ready=0.
  r.next.input_unit_mask = i.incoming_route_fire
    ? (std::uint64_t{1} << i.incoming_route_vc) - 1
    : advance(state_.input_unit_mask, r.selected_vc);
  // SingleVCAllocator.scala16..22: requests here already exclude occupied VCs.
  r.input_unit_grants = rr(i.eligible_input_units, state_.single_vc_input_mask);
  r.next.single_vc_input_mask = advance(state_.single_vc_input_mask, r.input_unit_grants);
  // ISLIP.scala13..34: output mask advances only on accepted allocation.
  r.islip_output_selection = rr(i.selected_eligible_output_vcs, state_.islip_output_mask);
  r.output_vc_grants = r.input_unit_grants ? r.islip_output_selection : 0;
  r.next.islip_output_mask = r.input_unit_grants
    ? advance(state_.islip_output_mask, r.islip_output_selection) : state_.islip_output_mask;
  r.local_request_accepted = r.selected_vc != 0 &&
    (r.input_unit_grants & (std::uint64_t{1} << parameters_.local_input_unit)) != 0;
  return r;
}
Result Arbiter::step(const Inputs& i) {
  auto r=preview(i);state_=r.next;return r;
}
} // namespace iris::noc
