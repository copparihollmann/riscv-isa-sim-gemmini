#pragma once
#include <array>
#include <cstdint>
#include <memory>
#include <span>
#include <string_view>
#include <vector>

namespace iris::cache {
// This boundary is the actual saved RTL, not an architectural memory operation.
// Each component has its own clock. An integrator drives physical handshakes;
// it must not replace individual beats with a guessed final completion time.
enum class Component { ShuttleL1D, RocketL1D, InclusiveL2 };
// Source DCache.scala359 consumes an invalid replay-head command. Its queue
// RAM has no reset. Default refusal prevents one arbitrary seed posing as a
// uniquely defined timing result. Explicit exploration never certifies timing.
enum class UnresetReplayPolicy { RefuseUse, ExploreConcreteReset };
struct Bits {
  std::array<std::uint64_t,4> limbs{}; // little endian, at most 256 physical bits
  constexpr Bits()=default;
  constexpr Bits(std::uint64_t low):limbs{low,0,0,0}{}
  bool operator==(const Bits&) const=default;
};
struct Field { std::string_view name; unsigned width; };
class Model {
 public:
  // Seed selects arbitrary unreset Verilator state, not hardware reset values.
  // A new instance refuses active operation before an explicitly committed reset.
  // Drive reset through input ports; no arrays are silently host-zeroed here.
  explicit Model(Component, std::uint32_t seed=1,
                 UnresetReplayPolicy=UnresetReplayPolicy::RefuseUse);
  ~Model();
  Model(const Model&)=delete;
  Model& operator=(const Model&)=delete;
  void evaluate(std::span<const Bits> inputs);
  std::vector<Bits> sample() const;
  void commit();
  std::vector<Bits> step(std::span<const Bits> inputs);
  std::uint64_t edges() const;
  Component component() const;
  bool concretized_unknown_replay_timing() const;
  std::span<const Field> input_fields() const;
  std::span<const Field> output_fields() const;
  static const char* source_identity();
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
