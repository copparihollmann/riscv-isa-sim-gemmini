#pragma once
#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>
namespace iris::saturn_storefront {
struct Bits {std::array<std::uint64_t,4>limbs{};bool operator==(const Bits&)const=default;};
struct Input {Bits value,known;bool operator==(const Input&)const=default;};
struct Field {std::string_view name;unsigned width;};
struct Owner {
  unsigned hart=0,tag=0;std::uint64_t epoch=0,command=0,generation=0,pc=0;std::uint32_t raw=0;
  bool operator==(const Owner&)const=default;
};
struct Calendar {unsigned period_master_ticks,phase_master_ticks;};
struct Domain {std::uint64_t base,bytes;};
enum class Phase {VMURequest,TileA,TileD,VMUResponse};
struct Receipt {
  Owner owner;Phase phase;bool load;unsigned source,mask;
  std::uint64_t source_edge,master_tick,address;
  std::array<std::uint8_t,16>data{},known{};
};
struct Outputs {std::vector<Bits>words;bool protocol_qualified=false;};
// Source transport only, with explicit external definedness/ownership. This
// class is not VMU/SIFQ/ROB, a cache, or a native arena initialization proof.
class Model {
 public:
  Model(unsigned hart,unsigned seed,std::vector<std::string>source_args,Calendar,std::vector<Domain>);
  ~Model();
  Model(const Model&)=delete;Model&operator=(const Model&)=delete;
  void evaluate_control(std::span<const Input>,std::optional<Owner>load={},std::optional<Owner>store={});
  Outputs sample()const;
  void prepare(std::uint64_t master_tick);
  void commit();
  std::span<const Receipt>last_receipts()const;
  bool drained()const;
  unsigned owned_requests()const;
  std::uint64_t reset_epoch()const;
  std::uint64_t committed_source_edges()const;
  static std::span<const Field>input_fields();
  static std::span<const Field>output_fields();
  static unsigned input_index(std::string_view);
  static unsigned output_index(std::string_view);
  static const char*raw_source_identity();
 private:struct Impl;std::unique_ptr<Impl>impl_;
};
Input concrete(unsigned width,std::uint64_t low=0);
}
