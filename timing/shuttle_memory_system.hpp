#pragma once
#include "serial_memory_system.hpp"
#include <memory>
namespace iris::shuttle_system {
using Bits=fabric::Bits;
using Input=fabric::Input;
using Field=fabric::Field;
using ClockEdges=memory_system::ClockEdges;
// Both actual Shuttle memory tiles use the source uncore edge. Rocket retains
// its independent core edge; Bringup and Serial edges remain explicit.
class System {
 public:
  explicit System(unsigned seed=1,std::vector<std::string>args={},serial_memory::AssertionPolicy=serial_memory::AssertionPolicy::SourceAlways);
  ~System();
  System(const System&)=delete;
  System&operator=(const System&)=delete;
  void evaluate(std::span<const Input>);
  std::vector<Bits>sample()const;
  void commit(ClockEdges);
  static std::span<const Field>input_fields();
  static std::span<const Field>output_fields();
  static unsigned external_input_index(std::string_view component,std::string_view field);
  static unsigned output_index(std::string_view component,std::string_view field);
  unsigned last_settle_iterations()const;
  bool concretized_unknown_replay_timing()const;
  static const char*source_identity();
 private:struct Impl;std::unique_ptr<Impl>impl_;
};
}
