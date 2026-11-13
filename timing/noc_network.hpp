#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <span>
#include <string_view>
#include "noc_network_schema.hpp"
namespace iris::noc {
struct NetworkField {std::string_view name;unsigned width;};
struct NetworkInputs {std::array<std::uint64_t,network_input_count> values;};
struct NetworkOutputs {std::array<std::uint64_t,network_output_count> values;};
// Complete saved A/C/D and B/E fabrics, all14routers and26TLadaptors.
// Endpoint caches/memory/serialTL and tile CDCs are outside this boundary.
class IrisNoCNetwork {
 public:
 explicit IrisNoCNetwork(std::uint32_t random_seed);
 ~IrisNoCNetwork();
 IrisNoCNetwork(IrisNoCNetwork&&) noexcept;
 IrisNoCNetwork& operator=(IrisNoCNetwork&&) noexcept;
 IrisNoCNetwork(const IrisNoCNetwork&)=delete;
 IrisNoCNetwork& operator=(const IrisNoCNetwork&)=delete;
 // Hold clock low and settle all source combinational logic. May be repeated
 // with revised physical endpoint inputs while a global scheduler converges.
 // Does not advance an edge; construction does not assert implicit reset.
 void evaluate(const NetworkInputs&);
 // Sample the currently settled outputs; illegal before evaluate/after commit.
 NetworkOutputs sample()const;
 // Advance exactly one shared uncore edge using the last evaluated inputs.
 // Repeated commit without a fresh evaluate is refused. No link delay is added.
 void commit();
 // Convenience composition: evaluate -> sample -> commit, not a separate model.
 NetworkOutputs step(const NetworkInputs&);
 // Source/tool/API-bound snapshots only between committed edges. No internal
 // observed-state/eligibility injection or imported whole-RTL state is accepted.
 void save(const std::filesystem::path&)const;
 void restore(const std::filesystem::path&);
 std::uint64_t edges()const;
 static std::span<const NetworkField> input_fields();
 static std::span<const NetworkField> output_fields();
 static const char* source_identity();
 private:struct Impl;std::unique_ptr<Impl> impl_;
};
} // namespace iris::noc
