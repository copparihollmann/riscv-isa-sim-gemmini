#ifndef SPIKE_TIMING_MEMORY_HPP
#define SPIKE_TIMING_MEMORY_HPP
#include "model.hpp"
#include "provider.hpp"
#include <map>
#include <unordered_map>
#include <set>

namespace spike_timing {
class MemorySystem {
public:
  MemorySystem(const Model &, merlin_timing::Engine &,
               std::function<merlin_timing::ValueId(std::size_t)> allocate,
               std::function<void(const std::string &, std::uint64_t)> feature,
               std::function<void(const std::string &)> unresolved);
  SharedEffects access(const std::vector<MemoryEffect> &, const std::string &path);
  void instruction_fence();
  std::size_t pending_tokens() const { return tokens_.size(); }
private:
  const Model &model_;
  merlin_timing::Engine &engine_;
  std::function<merlin_timing::ValueId(std::size_t)> allocate_;
  std::function<void(const std::string &, std::uint64_t)> feature_;
  std::function<void(const std::string &)> unresolved_;
  std::map<std::string, std::unique_ptr<merlin_timing::SetAssociativeCache>> caches_;
  std::map<std::string, std::uint64_t> lines_;
  std::map<std::string, merlin_timing::ValueId> cache_tokens_;
  std::map<std::string, std::vector<std::string>> paths_;
  std::unordered_map<std::uint64_t, merlin_timing::ValueId> tokens_;
  std::vector<merlin_timing::ValueId> free_;
  std::set<merlin_timing::ValueId> building_;
  std::uint64_t granule_ = 0;
  bool allocated_ = false;
  std::optional<merlin_timing::ValueId> token(std::uint64_t region);
  struct Walk {
    SharedEffects effects;
    std::set<merlin_timing::ValueId> reads, writes;
    std::map<std::pair<std::string, std::uint64_t>, bool> visited;
    merlin_timing::Cycle latency = 0, bus = 0;
    bool complete = true;
  };
  void cache_access(std::uint64_t, std::uint64_t, bool,
                    const std::vector<std::string> &, std::size_t, Walk &);
  void coherent_access(std::uint64_t, bool, Walk &);
  void charge(Walk &, const std::string &, double units = 1, bool bus = false);
};
} // namespace spike_timing
#endif
