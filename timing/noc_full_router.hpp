#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
namespace iris::noc {
struct FullPayload {std::array<std::uint32_t,3> words;};
struct FullFlow {std::uint8_t vnet,ingress_node,ingress_id,egress_node,egress_id;};
struct FullChannelFlit {bool valid,head,tail;FullPayload payload;FullFlow flow;std::uint8_t vc;};
struct FullIngressFlit {bool valid,head,tail;FullPayload payload;std::uint8_t egress_id;};
struct FullEgressFlit {bool valid,head,tail;FullPayload payload;};
struct FullCreditEvents {std::uint8_t credit_return,vc_free;};
struct FullRouterInputs {
 bool reset;
 std::array<FullChannelFlit,2> from_network;
 std::array<FullIngressFlit,2> from_local;
 std::array<FullCreditEvents,2> downstream;
 bool local_ready;
};
struct FullRouterOutputs {
 std::array<FullChannelFlit,2> to_network;
 std::array<bool,2> local_ready;
 std::array<FullCreditEvents,2> upstream;
 FullEgressFlit to_local;
 std::array<std::uint8_t,4> va_stalls,sa_stalls;
};
// Exact configured Router_5 subtree. Every step is an uncore rising edge.
// No queue/eligibility/free-slot inputs: all such state is internal.
// Constructor seed is explicit and does not assert reset. step() returns the
// combinational outputs preceding that edge, then advances all clocked state.
// Actual-reset replay and restoring a snapshot are separate entry modes. A
// snapshot must come from the same exact source/tool/ABI identity and native
// build; no imported whole-SoC internal state is accepted.
class FullNode5Router {
 public:
 explicit FullNode5Router(std::uint32_t random_seed);
 ~FullNode5Router();
 FullNode5Router(FullNode5Router&&) noexcept;
 FullNode5Router& operator=(FullNode5Router&&) noexcept;
 FullNode5Router(const FullNode5Router&)=delete;
 FullNode5Router& operator=(const FullNode5Router&)=delete;
 FullRouterOutputs step(const FullRouterInputs&);
 void save(const std::filesystem::path&)const;
 void restore(const std::filesystem::path&);
 std::uint64_t edges()const;
 static const char* source_identity();
 private:struct Impl;std::unique_ptr<Impl> impl_;
};
} // namespace iris::noc
