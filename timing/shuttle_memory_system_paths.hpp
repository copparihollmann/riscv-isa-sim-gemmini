#pragma once
#include <array>
#include <cstdint>
#include <string_view>
#include <memory>
#include <span>
#include <vector>
namespace iris::shuttle_memory {
struct Bits{std::array<std::uint64_t,4>limbs{};constexpr Bits()=default;constexpr Bits(std::uint64_t v):limbs{v,0,0,0}{};bool operator==(const Bits&)const=default;};
struct Field{std::string_view name;unsigned width;};
enum class Path {Tile,PRCI,Uncore};
// Original saved tile memory logic, synchronous PRCI buffers and SBUS coupler.
// This interface has physical pins and a supplied source edge, never a delay.
class Paths {
 public:
  explicit Paths(Path,unsigned seed=1);
  ~Paths();
  Paths(const Paths&)=delete;
  Paths&operator=(const Paths&)=delete;
  void evaluate(std::span<const Bits>);
  std::vector<Bits>sample()const;
  void validate_commit()const;
  void commit();
  std::span<const Field>input_fields()const;
  std::span<const Field>output_fields()const;
  Path component()const;
  std::uint64_t edges()const;
  static const char*source_identity();
 private:struct Impl;std::unique_ptr<Impl>impl_;
};
}
