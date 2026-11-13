#pragma once
#include <array>
#include <cstdint>
#include <memory>
#include <span>
#include <string_view>
#include "opu_sequencer_schema.hpp"
namespace iris::opu {
struct SequencerField { std::string_view name; unsigned width; };
struct SequencerInputs { std::array<std::uint64_t,sequencer_input_count> values{}; };
struct SequencerOutputs {
 std::array<std::uint64_t,sequencer_output_count> values{};
 // False means uninitialized or outside the qualified valid-payload scope.
 // A caller must not consume those physical payload bits as a known value.
 std::array<bool,sequencer_output_count> defined{};
};
// Exact saved OuterProductSequencer + PipeScheduler. No VRF data, dispatcher,
// array arithmetic, or automatic issue/dispatch edge is invented by this cut.
class IrisOPUSequencer {
 public:
 explicit IrisOPUSequencer(std::uint32_t random_seed);
 ~IrisOPUSequencer();
 IrisOPUSequencer(IrisOPUSequencer&&) noexcept;
 IrisOPUSequencer& operator=(IrisOPUSequencer&&) noexcept;
 IrisOPUSequencer(const IrisOPUSequencer&)=delete;
 IrisOPUSequencer& operator=(const IrisOPUSequencer&)=delete;
 // Explicit physical reset is required. Re-evaluation adds no edge and may
 // update VRF readiness/hazards before a global scheduler commits the edge.
 void evaluate(const SequencerInputs&);
 SequencerOutputs sample() const;
 void commit();
 SequencerOutputs step(const SequencerInputs&);
 std::uint64_t edges()const;
 static std::span<const SequencerField> input_fields();
 static std::span<const SequencerField> output_fields();
 static const char* source_identity();
 private: struct Impl; std::unique_ptr<Impl> impl_;
};
}
