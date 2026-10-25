#ifndef SPIKE_TIMING_PROVIDER_HPP
#define SPIKE_TIMING_PROVIDER_HPP

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>
#include "merlin_timing/engine.hpp"

namespace spike_timing {

struct MemoryEffect {
  std::uint64_t address, bytes;
  bool write;
  bool immutable = false;
};
struct SharedEffects {
  std::vector<merlin_timing::ValueId> reads, writes;
  std::vector<merlin_timing::Demand> demands;
  std::optional<merlin_timing::Cycle> latency;
};

// A separate timing provider observes the unchanged functional extension.
struct Services {
  merlin_timing::Engine &engine;
  std::function<std::optional<double>(const std::string &)> number;
  std::function<merlin_timing::ResourceId(const std::string &)> resource;
  std::function<merlin_timing::ValueId(std::size_t)> allocate_tokens;
  std::function<SharedEffects(const std::vector<MemoryEffect> &)> memory;
  std::function<void(const std::string &, std::uint64_t)> feature;
  std::function<void(const std::string &)> unresolved;
};
class TargetProvider {
public:
  virtual ~TargetProvider() = default;
  virtual merlin_timing::Result command(std::uint64_t pc, std::uint64_t bits,
                                      std::uint64_t rs1, std::uint64_t rs2,
                                      merlin_timing::Cycle earliest) = 0;
  virtual void fence(merlin_timing::Cycle earliest) = 0;
};
using CreateProvider = TargetProvider *(*)(Services *);

// Optional separate ABI: v1 factories/providers remain binary compatible.
// Missing timing prices/resources need not invalidate exact feature counts;
// unsupported effects, illegal commands and accounting gaps do.
struct FeatureObservationStatus {
  bool complete = false;
  std::vector<std::string> unresolved;
};
using ObserveProviderFeatures = FeatureObservationStatus (*)(const TargetProvider *);

} // namespace spike_timing

#endif
