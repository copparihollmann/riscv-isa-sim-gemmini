#ifndef SPIKE_TIMING_INTEGER_DIVIDER_TIMING_HPP
#define SPIKE_TIMING_INTEGER_DIVIDER_TIMING_HPP
#include "model.hpp"
#include <set>
#include <stdexcept>

namespace spike_timing {
struct IntegerDividerBound {
  bool operand_sensitive=false;
  // Request accepted -> response valid. Count 0..64 inclusive, plus at most
  // one input-sign and one output-sign state. Early-out can only shorten this.
  static constexpr merlin_timing::Cycle latency = 65 + 1 + 1;
  // The done state cannot accept a request; assume resp.ready immediately.
  static constexpr merlin_timing::Cycle occupancy = latency + 1;
};
inline std::optional<IntegerDividerBound> integer_divider_bound(const Model &model) {
  const auto selected = model.document.get_child_optional("cpu.integer_divider_service");
  if (!selected) return {};
  const std::set<std::string> expected{"schema", "xlen", "div_unroll", "early_out",
      "early_out_granularity", "response_ready", "rtl_sha256", "source_sha256"};
  std::set<std::string> keys;
  for (const auto &entry : *selected) {
    if (!entry.second.empty()) throw std::invalid_argument("nested divider selection");
    keys.insert(entry.first);
  }
  const auto schema=selected->get<std::string>("schema");
  const bool operand=schema=="merlin.rocket_integer_divider_operand_service.v2";
  if (keys != expected || (!operand&&schema!=
      "merlin.rocket_integer_divider_service_bound.v1") ||
      selected->get<unsigned>("xlen") != 64 || selected->get<unsigned>("div_unroll") != 1 ||
      !selected->get<bool>("early_out") || selected->get<unsigned>("early_out_granularity") != 1 ||
      selected->get<std::string>("response_ready") != "assumed_immediate" ||
      !is_digest(selected->get<std::string>("rtl_sha256")) ||
      !is_digest(selected->get<std::string>("source_sha256")))
    throw std::invalid_argument("unsupported Rocket integer-divider bound configuration");
  if (model.parameter("cpu.divide.latency_cycles") || model.parameter("cpu.divide.occupancy_cycles"))
    throw std::invalid_argument("divider bound conflicts with explicit divider prices");
  const auto &mappings = model.document.get_child("cpu_execution_resources");
  const auto divide = mappings.find("cpu.divide"), multiply = mappings.find("cpu.multiply");
  if (divide == mappings.not_found() || multiply == mappings.not_found() ||
      divide->second.data() != multiply->second.data())
    throw std::invalid_argument("divider bound requires shared multiply/divide resource");
  const auto id = model.resource(divide->second.data());
  bool single = false;
  for (const auto &resource : model.resources)
    if (id && resource.id == *id) single = resource.capacity == 1 && resource.queue_capacity == 0;
  if (!single) throw std::invalid_argument("divider bound requires one unqueued MulDiv unit");
  return IntegerDividerBound{operand};
}
struct IntegerDividerService {
 merlin_timing::Cycle latency,occupancy;
 std::uint64_t lhs,rhs;bool half,signed_divide,remainder;
};
// Selected Multiplier.scala count/sign/early-out state machine, w=64,
// divUnroll=divEarlyOutGranularity=1. Count0 executes even with early-out;
// Log2(0) is0 and the complement/subtraction is exactly six bits wide.
inline IntegerDividerService integer_divider_service(std::uint64_t bits,std::uint64_t lhs,std::uint64_t rhs){
 const bool half=(bits&127)==0x3b,signed_op=!((bits>>12)&1),rem=(bits>>13)&1;
 const auto operand=[&](std::uint64_t x)->std::uint64_t{if(!half)return x;const auto low=std::uint32_t(x);return signed_op&&bool(low>>31)?std::uint64_t(low)|0xffffffff00000000ull:std::uint64_t(low);};
 auto a=operand(lhs),b=operand(rhs);const bool aneg=signed_op&&bool(a>>63),bneg=signed_op&&bool(b>>63);
 if(aneg)a=0-a;
 if(bneg)b=0-b;
 const auto msb=[](std::uint64_t x){unsigned n=0;while(x>>1){++n;x>>=1;}return n;};
 const unsigned pos=(~(msb(a)-msb(b)))&63;
 merlin_timing::Cycle latency=b&&pos?66-pos:65;
 if(aneg||bneg)++latency;
 // Div-by-zero clears neg_out for quotient, while a negative remainder
 // still traverses s_neg_output, including the signed MIN/-1 case.
 if(rem?aneg:((aneg!=bneg)&&b!=0))++latency;
 return {latency,latency+1,lhs,rhs,half,signed_op,rem};
}
} // namespace spike_timing
#endif
