#pragma once
#include "iris_definedness.hpp"
#include <memory>
#include <optional>
#include <vector>
class processor_t;
// Private functional intents. No main CSR/VU shared_ptr is ever copied, and
// the oracle has no RAM/device service. Physical publication is caller-owned.
class iris_saturn_oracle {
 public:
  struct Image {
    std::vector<uint8_t> vrf,mrf;
    iris_definedness::Bytes vrf_known,mrf_known;
    std::vector<uint8_t> initialized;
    uint64_t vl,vlmax,vtype,mtype,vstart,vxrm,vma,vta,vsew,altfmt,widen,tm,tk;
    uint64_t vstart_known,vxrm_known;
    float lmul;bool vill;
  };
  struct Intent {
    uint64_t node,pc;uint32_t instruction;
    Image before,after;
    std::optional<iris_definedness::Value<uint64_t>> scalar;
  };
  explicit iris_saturn_oracle(processor_t&);
  ~iris_saturn_oracle();
  iris_saturn_oracle(const iris_saturn_oracle&)=delete;
  iris_saturn_oracle&operator=(const iris_saturn_oracle&)=delete;
  Intent preview(processor_t& real,uint64_t node,uint64_t pc,uint32_t raw,
       iris_definedness::Value<uint64_t> rs1,iris_definedness::Value<uint64_t> rs2);
  void rollback(const Image&);
 private:struct Impl;std::unique_ptr<Impl>impl_;
};
