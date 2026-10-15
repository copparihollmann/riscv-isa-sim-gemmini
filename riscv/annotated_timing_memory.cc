#include "../timing/memory.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>

namespace spike_timing {
namespace {
using merlin_timing::Cycle;
bool add(Cycle &value, Cycle increment) {
  if (increment > std::numeric_limits<Cycle>::max() - value) return false;
  value += increment; return true;
}
std::size_t positive(const boost::property_tree::ptree &row, const char *key, std::size_t max) {
  const auto v = row.get<std::size_t>(key);
  if (!v || v > max) throw std::invalid_argument("cache geometry exceeds bounds");
  return v;
}
} // namespace

MemorySystem::MemorySystem(const Model &model, merlin_timing::Engine &engine,
                           std::function<merlin_timing::ValueId(std::size_t)> allocate,
                           std::function<void(const std::string &, std::uint64_t)> feature,
                           std::function<void(const std::string &)> unresolved)
    : model_(model), engine_(engine), allocate_(std::move(allocate)),
      feature_(std::move(feature)), unresolved_(std::move(unresolved)) {
  for (const auto *name : {"modeled.dram_request_bytes", "modeled.writeback_bytes",
                           "modeled.coherence_probes", "modeled.coherence_writeback_bytes",
                           "modeled.immutable_requested_bytes"}) feature_(name, 0);
  for (const auto *path : {"cpu_fetch", "cpu_data", "device"}) {
    feature_(std::string(path) + ".requested_read_bytes", 0);
    feature_(std::string(path) + ".requested_write_bytes", 0);
  }
  if (const auto granule = model.number("memory.coherence_granule")) {
    if (*granule >= 1 && *granule <= (1 << 20) && std::floor(*granule) == *granule &&
        !(static_cast<std::uint64_t>(*granule) & (static_cast<std::uint64_t>(*granule) - 1)))
      granule_ = static_cast<std::uint64_t>(*granule);
  }
  if (const auto caches = model.document.get_child_optional("memory.caches")) {
    if (caches->size() > 16) throw std::invalid_argument("too many cache levels");
    for (const auto &entry : *caches) {
      const auto sets = positive(entry.second, "sets", 1 << 20);
      const auto ways = positive(entry.second, "ways", 1024);
      const auto line = positive(entry.second, "line_bytes", 1 << 20);
      if (line & (line - 1)) throw std::invalid_argument("cache line size must be a power of two");
      if (sets > (1 << 20) / ways) throw std::invalid_argument("cache entry budget exceeded");
      if (entry.second.get<std::string>("policy") != "write_back_write_allocate")
        throw std::invalid_argument("cache allocation policy is unsupported");
      caches_.emplace(entry.first, std::make_unique<merlin_timing::SetAssociativeCache>(
          merlin_timing::CacheSpec{sets, ways, line}));
      feature_("modeled.cache." + entry.first + ".hits", 0);
      feature_("modeled.cache." + entry.first + ".misses", 0);
      lines_[entry.first] = line;
      cache_tokens_[entry.first] = allocate_(sets * ways);
    }
  }
  if (const auto paths = model.document.get_child_optional("memory.paths")) {
    for (const auto &entry : *paths) {
      if (entry.second.size() > 16) throw std::invalid_argument("cache path is too long");
      auto &path = paths_[entry.first];
      std::set<std::string> seen;
      for (const auto &level : entry.second) {
        const auto name = level.second.get_value<std::string>();
        if (!caches_.count(name) || !seen.insert(name).second)
          throw std::invalid_argument("unknown or cyclic cache path");
        path.push_back(name);
      }
    }
  }
}

std::optional<merlin_timing::ValueId> MemorySystem::token(std::uint64_t region) {
  const auto old = tokens_.find(region);
  if (old != tokens_.end()) { building_.insert(old->second); return old->second; }
  if (!allocated_) {
    const auto base = allocate_(model_.max_memory_entries);
    free_.reserve(model_.max_memory_entries);
    for (std::size_t i = 0; i < model_.max_memory_entries; ++i) free_.push_back(base + i);
    allocated_ = true;
  }
  if (free_.empty()) {
    const auto frontier = engine_.issue_frontier();
    if (frontier) {
      for (auto it = tokens_.begin(); it != tokens_.end();) {
        const auto done = engine_.last_use(it->second);
        if (done && *done <= *frontier && !building_.count(it->second)) {
          engine_.reset(it->second); free_.push_back(it->second); it = tokens_.erase(it);
        } else ++it;
      }
    }
  }
  if (free_.empty()) {
    unresolved_("shared memory dependency capacity exceeded"); return {};
  }
  const auto result = free_.back(); free_.pop_back(); tokens_.emplace(region, result); building_.insert(result);
  return result;
}

void MemorySystem::charge(Walk &walk, const std::string &price, double units, bool bus) {
  const auto cost = model_.cycles(price, units);
  if (!cost || !add(walk.latency, *cost) || (bus && !add(walk.bus, *cost)))
    walk.complete = false;
}

void MemorySystem::cache_access(std::uint64_t address, std::uint64_t bytes, bool write,
                               const std::vector<std::string> &path, std::size_t level, Walk &walk) {
  if (!bytes) return;
  if (level == path.size()) {
    if (!granule_ || bytes - 1 > std::numeric_limits<std::uint64_t>::max() - address ||
        (bytes - 1) / granule_ + 1 > model_.max_memory_entries) {
      walk.complete = false; return;
    }
    const auto last_region = (address + bytes - 1) / granule_;
    for (auto region = address / granule_;; ++region) {
      if (const auto id = token(region)) (write ? walk.writes : walk.reads).insert(*id);
      else walk.complete = false;
      if (region == last_region) break;
    }
    charge(walk, "memory.dram_latency_cycles");
    charge(walk, "memory.dram_per_byte_cycles", bytes, true);
    feature_("modeled.dram_request_bytes", bytes);
    return;
  }
  const auto &name = path[level];
  const auto line_bytes = lines_.at(name);
  const auto last = (address + bytes - 1) / line_bytes;
  for (auto line = address / line_bytes;; ++line) {
    const auto key = std::make_pair(name, line);
    auto prior = walk.visited.find(key);
    if (prior != walk.visited.end() && !caches_.at(name)->probe(line * line_bytes).hit) {
      walk.visited.erase(prior); prior = walk.visited.end();
    }
    if (prior != walk.visited.end()) {
      // Preserve write state when an earlier effect read this line. It has
      // already been filled/priced in this architectural command.
      if (write && !prior->second) {
        const auto updated = caches_.at(name)->access(line * line_bytes, true);
        walk.writes.insert(cache_tokens_.at(name) + updated.slot);
        prior->second = true;
      }
    } else {
      if (walk.visited.size() >= model_.max_memory_entries) {
        unresolved_("single memory event exceeds cache transaction budget");
        walk.complete = false; return;
      }
      walk.visited.emplace(key, write);
      const auto result = caches_.at(name)->access(line * line_bytes, write);
      const auto slot = cache_tokens_.at(name) + result.slot;
      // Cache hits depend on the outstanding fill. Replacement waits for
      // the prior slot's fill and readers through the engine's WAW/WAR rules.
      if (result.hit && !write) walk.reads.insert(slot); else walk.writes.insert(slot);
      feature_("modeled.cache." + name + (result.hit ? ".hits" : ".misses"), 1);
      charge(walk, "memory." + name + (result.hit ? ".hit_cycles" : ".miss_cycles"));
      if (result.dirty_eviction) {
        feature_("modeled.writeback_bytes", line_bytes);
        cache_access(*result.evicted_line * line_bytes, line_bytes, true, path, level + 1, walk);
      }
      if (!result.hit)
        cache_access(line * line_bytes, line_bytes, false, path, level + 1, walk);
    }
    if (line == last) break;
  }
}

void MemorySystem::coherent_access(std::uint64_t address, bool, Walk &walk) {
  // This is an explicit timing policy, not a claim that Spike models a cache
  // coherence protocol. Profiles must opt in to writeback/invalidate snoops.
  if (model_.document.get<std::string>("memory.coherence_policy", "") != "writeback_invalidate") {
    unresolved_("device coherence timing policy is unspecified"); walk.complete = false; return;
  }
  const auto device = paths_.find("device");
  if (device == paths_.end()) { walk.complete = false; return; }
  for (const auto *cpu : {"cpu_data", "cpu_fetch"}) {
    const auto path = paths_.find(cpu);
    if (path == paths_.end()) continue;
    for (std::size_t level = 0; level < path->second.size(); ++level) {
      const auto &name = path->second[level];
      if (std::find(device->second.begin(), device->second.end(), name) != device->second.end()) continue;
      const auto probe = caches_.at(name)->invalidate(address);
      if (!probe.hit) continue;
      walk.writes.insert(cache_tokens_.at(name) + *probe.slot);
      charge(walk, "memory.snoop_cycles");
      feature_("modeled.coherence_probes", 1);
      if (probe.dirty) {
        const auto bytes = lines_.at(name);
        feature_("modeled.coherence_writeback_bytes", bytes);
        cache_access(address / bytes * bytes, bytes, true, path->second, level + 1, walk);
      }
    }
  }
}

SharedEffects MemorySystem::access(const std::vector<MemoryEffect> &effects, const std::string &path) {
  building_.clear();
  Walk walk;
  walk.complete = granule_ != 0;
  std::map<std::uint64_t, bool> regions;
  for (const auto &effect : effects) {
    if (!effect.bytes) continue;
    if (effect.immutable) {
      if (effect.write) walk.complete = false;
      else {
        charge(walk, "memory.immutable_access_cycles");
        feature_("modeled.immutable_requested_bytes", effect.bytes);
      }
      continue;
    }
    feature_(path + (effect.write ? ".requested_write_bytes" : ".requested_read_bytes"), effect.bytes);
    if (!granule_ || effect.bytes - 1 > std::numeric_limits<std::uint64_t>::max() - effect.address) {
      walk.complete = false; continue;
    }
    const auto last = (effect.address + effect.bytes - 1) / granule_;
    for (auto region = effect.address / granule_;; ++region) {
      if (regions.size() >= model_.max_memory_entries && !regions.count(region)) {
        unresolved_("single memory event exceeds dependency capacity"); walk.complete = false; break;
      }
      regions[region] = regions[region] || effect.write;
      if (region == last) break;
    }
  }
  const auto selected = paths_.find(path);
  if (!regions.empty() && selected == paths_.end()) {
    unresolved_("memory path is unspecified: " + path); walk.complete = false;
  }
  // Hazard tracking uses coherence granules. Cache timing independently visits
  // every line intersected by each exact byte interval (never a rounded granule).
  for (const auto &region : regions) {
    if (const auto id = token(region.first))
      (region.second ? walk.writes : walk.reads).insert(*id);
    else walk.complete = false;
  }
  if (selected != paths_.end()) {
    for (const auto &effect : effects) {
      if (effect.immutable || !effect.bytes || effect.bytes - 1 > std::numeric_limits<std::uint64_t>::max() - effect.address) continue;
      std::uint64_t smallest = granule_;
      for (const auto &entry : lines_) smallest = smallest ? std::min(smallest, entry.second) : entry.second;
      if (!smallest || (effect.bytes - 1) / smallest + 1 > model_.max_memory_entries) {
        unresolved_("memory transfer exceeds bounded transaction budget"); walk.complete = false; continue;
      }
      if (path == "device") {
        // Each private-cache line is probed, including lines finer than the
        // logical coherence granule. Invalidation makes duplicate probes cheap.
        std::uint64_t step = granule_;
        for (const auto &entry : lines_) step = step ? std::min(step, entry.second) : entry.second;
        if (!step) { walk.complete = false; continue; }
        const auto last = (effect.address + effect.bytes - 1) / step;
        for (auto line = effect.address / step;; ++line) {
          coherent_access(line * step, effect.write, walk);
          if (line == last) break;
        }
      }
      cache_access(effect.address, effect.bytes, effect.write, selected->second, 0, walk);
    }
  }
  walk.effects.reads.assign(walk.reads.begin(), walk.reads.end());
  walk.effects.writes.assign(walk.writes.begin(), walk.writes.end());
  if (walk.bus) {
    const auto resource = model_.resource("memory.shared");
    if (resource) walk.effects.demands.push_back({*resource, 1, walk.bus});
    else walk.complete = false;
  }
  if (walk.complete) walk.effects.latency = walk.latency;
  else unresolved_("memory timing has unresolved prices, resources or semantics");
  return walk.effects;
}
void MemorySystem::instruction_fence() {
  const auto path = paths_.find("cpu_fetch");
  if (path == paths_.end() || path->second.empty()) {
    unresolved_("instruction cache fence path is unspecified"); return;
  }
  for (const auto *other : {"cpu_data", "device"}) {
    const auto selected = paths_.find(other);
    if (selected != paths_.end() && std::find(selected->second.begin(), selected->second.end(), path->second.front()) != selected->second.end()) {
      unresolved_("instruction fence requires an explicitly supported private instruction cache"); return;
    }
  }
  // Caller has drained the engine before invalidation.
  caches_.at(path->second.front())->clear();
}
} // namespace spike_timing
