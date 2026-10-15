#include "../timing/model.hpp"
#include <boost/property_tree/json_parser.hpp>
#include <openssl/evp.h>
#include <array>
#include <cmath>
#include <fstream>
#include <filesystem>
#include <iomanip>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>

namespace spike_timing {
namespace {
using Tree = boost::property_tree::ptree;
void unique_keys(const Tree &node, unsigned depth = 0) {
  if (depth > 32) throw std::invalid_argument("timing JSON nesting limit exceeded");
  std::set<std::string> keys;
  bool array = !node.empty() && node.begin()->first.empty();
  for (const auto &child : node) {
    if ((!array && !keys.insert(child.first).second) || (array && !child.first.empty()))
      throw std::invalid_argument("duplicate or mixed JSON object keys");
    unique_keys(child.second, depth + 1);
  }
}
std::size_t bounded_integer(const Tree &node, const char *name,
                            std::size_t fallback, std::size_t maximum) {
  const auto value = node.get_optional<std::uint64_t>(name);
  if (!value) return fallback;
  if (*value == 0 || *value > maximum)
    throw std::invalid_argument(std::string("invalid bounded timing limit: ") + name);
  return static_cast<std::size_t>(*value);
}
std::string hex_digest(EVP_MD_CTX *ctx) {
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned size = 0;
  if (!EVP_DigestFinal_ex(ctx, digest.data(), &size) || size != 32)
    throw std::runtime_error("SHA-256 finalization failed");
  std::ostringstream result;
  for (unsigned i = 0; i < size; ++i)
    result << std::hex << std::setw(2) << std::setfill('0') << unsigned(digest[i]);
  return result.str();
}
using Hash = std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)>;
Hash hash_context() {
  Hash ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free);
  if (!ctx || !EVP_DigestInit_ex(ctx.get(), EVP_sha256(), nullptr))
    throw std::runtime_error("SHA-256 initialization failed");
  return ctx;
}
} // namespace

std::string sha256_bytes(const std::string &bytes) {
  auto ctx = hash_context();
  if (!EVP_DigestUpdate(ctx.get(), bytes.data(), bytes.size()))
    throw std::runtime_error("SHA-256 update failed");
  return hex_digest(ctx.get());
}
std::string sha256_file(const std::string &path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) throw std::runtime_error("cannot read timing identity file: " + path);
  auto ctx = hash_context();
  std::array<char, 65536> block{};
  while (stream.read(block.data(), block.size()) || stream.gcount()) {
    if (!EVP_DigestUpdate(ctx.get(), block.data(), stream.gcount()))
      throw std::runtime_error("SHA-256 update failed");
  }
  if (!stream.eof()) throw std::runtime_error("timing identity file read failed");
  return hex_digest(ctx.get());
}
bool is_digest(const std::string &value) {
  return value.size() == 64 && value.find_first_not_of("0123456789abcdef") == std::string::npos;
}
std::string json_string(const std::string &text) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : text) {
    if (c == '"' || c == '\\') out << '\\' << char(c);
    else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << unsigned(c);
    else out << char(c);
  }
  out << '"';
  return out.str();
}

Model::Model(const std::string &path) {
  std::ifstream file(path, std::ios::binary | std::ios::ate);
  if (!file || file.tellg() > (8 << 20))
    throw std::invalid_argument("timing model is absent or exceeds 8 MiB");
  file.seekg(0);
  std::ostringstream content; content << file.rdbuf();
  digest = sha256_bytes(content.str());
  std::istringstream input(content.str());
  boost::property_tree::read_json(input, document);
  unique_keys(document);
  if (document.get<std::string>("schema") != "merlin.annotated_spike_model.v1")
    throw std::invalid_argument("unsupported annotated Spike model schema");
  profile = document.get<std::string>("profile");
  if (profile != "phase1-public" && profile != "historical-private")
    throw std::invalid_argument("unknown calibration profile");
  const auto &identity = document.get_child("domain");
  for (const auto &child : identity) {
    if (!child.second.empty()) throw std::invalid_argument("timing domain values must be digests");
    domain.emplace(child.first, child.second.data());
  }
  if (domain.count("target_model_sha256"))
    throw std::invalid_argument("native timing model cannot contain its own digest");
  for (const auto *key : {"device_sha256", "feature_engine_sha256", "feature_schema_sha256",
                          "label_engine_sha256", "memory_regime_sha256", "scope_sha256"})
    if (!is_digest(domain.at(key))) throw std::invalid_argument("invalid timing domain digest");
  if (domain.at("label_engine") != "gsim" && domain.at("label_engine") != "firesim" &&
      domain.at("label_engine") != "verilator")
    throw std::invalid_argument("functional counts cannot label a timing profile");
  domain["target_model_sha256"] = digest;
  device = domain.at("device_sha256"); scope = domain.at("scope_sha256");
  const auto limits = document.get_child_optional("limits");
  if (limits) {
    max_values = bounded_integer(*limits, "scoreboard_values", max_values, 1 << 22);
    max_memory_entries = bounded_integer(*limits, "memory_entries", max_memory_entries, 1 << 20);
    max_counter_windows = bounded_integer(*limits, "counter_windows", max_counter_windows, 65536);
    max_accesses_per_instruction = bounded_integer(*limits, "instruction_accesses", max_accesses_per_instruction, 1 << 16);
  }
  for (const auto &row : document.get_child("resources")) {
    const auto &spec = row.second;
    const auto id = spec.get<std::uint32_t>("id");
    const auto name = spec.get<std::string>("name");
    const auto capacity = spec.get<std::size_t>("capacity");
    const auto queue = spec.get<std::size_t>("queue_capacity");
    if (resources.size() >= 128 || !capacity || capacity > 65536 || queue > 65536 ||
        !resource_names.emplace(name, id).second)
      throw std::invalid_argument("invalid or duplicate timing resource");
    resources.push_back({id, capacity, queue});
  }
  const auto scope_kind = document.get<std::string>("scope.kind");
  if (scope_kind != "counter_pair" && scope_kind != "counter_pc_pair" && scope_kind != "whole_program")
    throw std::invalid_argument("unknown timing scope kind");
  scope_pc_pair = scope_kind == "counter_pc_pair";
  if (scope_kind == "counter_pair") {
    scope_window = document.get<std::size_t>("scope.index");
  }
  if (scope_kind != "whole_program" && scope_window >= max_counter_windows)
    throw std::invalid_argument("selected counter window exceeds report budget");
  if (resources.empty()) throw std::invalid_argument("timing model requires explicit resources");
  const auto parameters = document.get_child_optional("parameters");
  if (parameters) {
    if (parameters->size() > 2048) throw std::invalid_argument("too many timing prices");
    for (const auto &row : *parameters) {
      if (row.second.data() == "null") continue;
      if (!row.second.empty() || row.first.size() > 256) throw std::invalid_argument("invalid timing price");
      std::size_t parsed = 0;
      const auto price = std::stod(row.second.data(), &parsed);
      if (parsed != row.second.data().size() || !std::isfinite(price) || price < 0)
        throw std::invalid_argument("invalid timing price");
      prices.emplace(row.first, price);
    }
  }
}
void Model::bind_scope(const std::string &path, const std::string &elf, const std::string &input) {
  if (!scope_pc_pair) {
    if (!path.empty()) throw std::invalid_argument("scope binding requires counter_pc_pair policy");
    return;
  }
  if (path.empty() || std::filesystem::is_symlink(path) ||
      !std::filesystem::is_regular_file(path) || std::filesystem::file_size(path) > 16384)
    throw std::invalid_argument("counter_pc_pair requires a bounded original scope binding");
  std::ifstream stream(path, std::ios::binary);
  std::ostringstream raw; raw << stream.rdbuf();
  if (!stream || raw.str().size() > 16384) throw std::invalid_argument("scope binding read failed");
  boost::property_tree::ptree binding;
  std::istringstream json(raw.str()); boost::property_tree::read_json(json, binding);
  unique_keys(binding);
  const std::set<std::string> expected{"schema", "elf_sha256", "input_sha256", "scope_sha256",
      "begin_pc", "end_pc", "occurrence", "evidence_sha256"};
  std::set<std::string> observed;
  for (const auto &entry : binding) observed.insert(entry.first);
  if (observed != expected || binding.get<std::string>("schema") != "merlin.spike_scope_binding.v1" ||
      binding.get<std::string>("elf_sha256") != elf || binding.get<std::string>("input_sha256") != input ||
      binding.get<std::string>("scope_sha256") != scope)
    throw std::invalid_argument("scope binding differs from exact ELF/input/scope identity");
  scope_begin_pc = binding.get<std::uint64_t>("begin_pc");
  scope_end_pc = binding.get<std::uint64_t>("end_pc");
  scope_window = binding.get<std::size_t>("occurrence");
  scope_binding_evidence = binding.get<std::string>("evidence_sha256");
  if (!scope_begin_pc || !scope_end_pc || scope_begin_pc == scope_end_pc ||
      scope_begin_pc % 2 || scope_end_pc % 2 || scope_window >= max_counter_windows ||
      !is_digest(scope_binding_evidence))
    throw std::invalid_argument("scope binding has invalid boundaries, occurrence or evidence identity");
  scope_binding_digest = sha256_bytes(raw.str());
}
std::optional<double> Model::number(const std::string &path) const {
  const auto value = document.get_optional<std::string>(path);
  if (!value || *value == "null") return {};
  std::size_t parsed = 0;
  double result;
  try { result = std::stod(*value, &parsed); }
  catch (const std::exception &) { return {}; }
  if (parsed != value->size() || !std::isfinite(result) || result < 0) return {};
  return result;
}
std::optional<double> Model::parameter(const std::string &name) const {
  const auto found = prices.find(name);
  return found == prices.end() ? std::optional<double>{} : found->second;
}
std::optional<merlin_timing::Cycle> Model::cycles(const std::string &name, double units) const {
  const auto value = parameter(name);
  if (!value || !std::isfinite(units) || units < 0) return {};
  const double cost = std::ceil(*value * units);
  if (!std::isfinite(cost) || cost >= double(std::numeric_limits<merlin_timing::Cycle>::max())) return {};
  return static_cast<merlin_timing::Cycle>(cost);
}
std::optional<merlin_timing::ResourceId> Model::resource(const std::string &name) const {
  const auto it = resource_names.find(name);
  return it == resource_names.end() ? std::optional<merlin_timing::ResourceId>{} : it->second;
}
std::string Model::domain_json() const {
  std::ostringstream out; out << '{';
  bool first = true;
  for (const auto &entry : domain) {
    if (!first) out << ',';
    first = false; out << json_string(entry.first) << ':' << json_string(entry.second);
  }
  out << '}'; return out.str();
}
} // namespace spike_timing
