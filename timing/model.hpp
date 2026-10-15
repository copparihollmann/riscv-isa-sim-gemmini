#ifndef SPIKE_TIMING_MODEL_HPP
#define SPIKE_TIMING_MODEL_HPP
#include <boost/property_tree/ptree.hpp>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include "merlin_timing/engine.hpp"

namespace spike_timing {
std::string sha256_bytes(const std::string &bytes);
std::string sha256_file(const std::string &path);
std::string json_string(const std::string &text);
bool is_digest(const std::string &text);
struct Model {
  boost::property_tree::ptree document;
  std::string digest, profile, scope, device;
  std::map<std::string, std::string> domain;
  std::vector<merlin_timing::ResourceSpec> resources;
  std::map<std::string, merlin_timing::ResourceId> resource_names;
  std::map<std::string, double> prices;
  std::size_t max_values = 131072, max_memory_entries = 65536;
  std::size_t max_counter_windows = 4096, max_accesses_per_instruction = 1024;
  explicit Model(const std::string &path);
  std::optional<double> number(const std::string &path) const;
  std::optional<double> parameter(const std::string &name) const;
  std::optional<merlin_timing::Cycle> cycles(const std::string &name, double units = 1) const;
  std::optional<merlin_timing::ResourceId> resource(const std::string &name) const;
  std::string domain_json() const;
};
} // namespace spike_timing
#endif
