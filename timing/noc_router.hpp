#pragma once
#include "noc_arbiter.hpp"
#include <array>
#include <cstdint>
#include <optional>
#include <vector>

namespace iris::noc {
struct RouterParameters {
  Parameters arbitration;
  unsigned input_fifo_depth;
  unsigned egress_fifo_depth;
  unsigned node_id;
  unsigned local_egress_id;
  unsigned local_output_bit;
};
struct Flit {
  // Exact BaseFlit packed75-bit representation: head bit0, tail bit1, payload74:2.
  std::array<std::uint32_t,3> words;
  bool head()const{return words[0]&1;}
  bool tail()const{return words[0]&2;}
};
struct Fifo {
  unsigned enq,deq;
  bool maybe_full;
  std::vector<Flit> memory;
  unsigned count()const;
  const Flit& front()const;
  void commit(std::optional<Flit> push,bool pop);
};
struct ReturnVC {unsigned state;bool local;Fifo fifo;};
struct ReturnState {
  std::vector<ReturnVC> vcs;
  State arbitration;
  std::uint64_t switch_mask,switch_lock,egress_sa_mask,egress_sa_lock;
  bool egress_empty;
  Fifo egress;
};
struct ReturnInputs {
  bool arrival_valid;
  unsigned arrival_vc,arrival_dest,arrival_dest_id;
  Flit arrival;
  bool downstream_ready;
  // Other physical input units are outside this return-branch component.
  std::array<bool,3> peer_eligible;
  std::array<std::uint64_t,3> peer_eligible_outputs;
  bool route_fire;
  unsigned route_vc;
  bool route_local;
};
struct ReturnResult {
  std::uint64_t waiting,selected_vc,input_grants,output_grants,popped_vcs,freed_vcs;
  bool egress_push,egress_pop;
  std::optional<Flit> output;
};
class ReturnRouter {
 public:
  ReturnRouter(RouterParameters parameters,ReturnState initial);
  ReturnResult step(const ReturnInputs& inputs);
  const ReturnState& state()const{return state_;}
 private:
  RouterParameters parameters_;
  ReturnState state_;
};
} // namespace iris::noc
