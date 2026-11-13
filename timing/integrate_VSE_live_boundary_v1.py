#!/usr/bin/env python3
"""Apply the finite test-only boundary hooks to its new private source only."""
from pathlib import Path
R=Path(__file__).resolve().parents[1];S=R/'pipeline/riscv-isa-sim-VSE-live-boundary-v1'
def edit(name,old,new):
 p=S/name;s=p.read_text();assert s.count(old)==1,(name,old[:100]);p.write_text(s.replace(old,new))
def main():
 edit('riscv/iris_timing_adapter.h','#pragma once\n','#pragma once\n#include "../../../timing/vse_live_boundary_v1.hpp"\n')
 edit('riscv/iris_timing_adapter.h','    bool empirical_scalar_fadd=false;','    bool empirical_scalar_fadd=false;\n    bool vse_boundary_test=false;unsigned vse_boundary_hart=0;Cycle vse_boundary_ack=0;')
 edit('riscv/iris_timing_adapter.h','  struct Pending {','  struct VseBoundaryCommand;\n  std::array<std::shared_ptr<VseBoundaryCommand>,2>vse_boundary_commands_{};\n  std::array<iris::vse_boundary::OrderedStores,2>vse_boundary_ledgers_{};\n  uint64_t vse_boundary_serial_=0,vse_boundary_commands_total_=0,vse_boundary_completed_total_=0,vse_boundary_requests_total_=0,vse_boundary_ACKs_total_=0,vse_boundary_releases_total_=0;\n  bool vse_boundary_live(unsigned)const;\n  void vse_boundary_environment()const;\n  void vse_boundary_step(unsigned);\n  void vse_boundary_schedule(unsigned);\n  void vse_boundary_tick(unsigned);\n  void vse_boundary_ack(unsigned,const std::shared_ptr<VseBoundaryCommand>&,unsigned,uint64_t);\n  void vse_boundary_totals(std::ostream&)const;\n  struct Pending {')
 edit('riscv/iris_timing_adapter.cc','      } else if(key=="empirical_vadd_eg"&&f.size()==2){','''      } else if(key=="experimental_vse_boundary"){
        if(f.size()==2&&f[1]=="source-System-v6-production-v1")throw std::runtime_error("IRIS_VSE_BOUNDARY_SYSTEM_BACKEND_UNAVAILABLE");
        if(f.size()!=5||!singleton.insert(key).second||f[1]!="SYNTHETIC-DIRECTED-TEST-ONLY-v1"||f[4]!="core_edges")throw std::runtime_error("IRIS_VSE_BOUNDARY_EXPLICIT_SYNTHETIC_TEST_SELECTOR_REQUIRED");
        const auto h=number(f[2]),ack=number(f[3]);if(h>=2||ack<1||ack>10000)throw std::runtime_error("IRIS_VSE_BOUNDARY_TEST_GEOMETRY_OR_ACK_OUTSIDE_SCOPE");p.vse_boundary_test=true;p.vse_boundary_hart=h;p.vse_boundary_ack=ack;
      } else if(key=="empirical_vadd_eg"&&f.size()==2){''')
 edit('riscv/iris_timing_adapter.cc','  if(p.empirical_vadd_eg&&','  if(p.vse_boundary_test&&(!p.empirical||!p.private_forwarded_values||!p.shuttle_pure_pipeline||!p.source_counter_clock))throw std::runtime_error("IRIS_VSE_BOUNDARY_REQUIRES_EMPIRICAL_PRIVATE_SOURCE_COUNTER_FRONT");\n  if(p.empirical_vadd_eg&&')
 edit('riscv/iris_timing_adapter.cc','  if(profile_.empirical_vadd_eg)for(unsigned h=0;h<2;++h){','  if(profile_.vse_boundary_test)for(unsigned h=0;h<2;++h){clock_.configure_resource("test.VSE.tick"+std::to_string(h),1);clock_.configure_resource("test.VSE.ACK"+std::to_string(h),16);}\n  if(profile_.empirical_vadd_eg)for(unsigned h=0;h<2;++h){')
 edit('riscv/iris_timing_adapter.cc','advance(before,now);if(profile_.empirical_opu_entry)','advance(before,now);if(profile_.vse_boundary_test)vse_boundary_environment();if(profile_.empirical_opu_entry)')
 edit('riscv/iris_timing_adapter.cc','void iris_timing_adapter::issue(unsigned hart, reg_t pc, const insn_fetch_t& fetch) {','void iris_timing_adapter::issue(unsigned hart, reg_t pc, const insn_fetch_t& fetch) {\n  if(profile_.vse_boundary_test&&vse_boundary_live(hart))throw iris_timing_wait{};')
 edit('riscv/iris_timing_adapter.cc','    try { cores_[hart]->step(1); }','    try { if(profile_.vse_boundary_test)vse_boundary_step(hart);else cores_[hart]->step(1); }')
 edit('riscv/iris_timing_adapter.cc','    if (blocked_[hart]||empirical_branch_recovery_[hart]) continue;','    if (blocked_[hart]||empirical_branch_recovery_[hart]) continue;\n    if(profile_.vse_boundary_test&&vse_boundary_live(hart))continue;')
 edit('riscv/iris_timing_adapter.cc','#include "iris_opu_fence.inc"','#include "iris_opu_fence.inc"\n#include "iris_vse_live_boundary.inc"')
 edit('riscv/iris_empirical_features.inc','void iris_timing_adapter::empirical_write_totals(std::ostream&out)const{','void iris_timing_adapter::empirical_write_totals(std::ostream&out)const{\n vse_boundary_totals(out);')
 edit('riscv/mmu.h','  bool iris_execute_trigger_enabled() const { return check_triggers_fetch; }','''  bool iris_execute_trigger_enabled() const { return check_triggers_fetch; }
  using iris_vse_boundary_capture_fn=void(*)(void*,reg_t,uint32_t,const std::array<uint8_t,4>&);
  void iris_begin_vse_boundary_capture(void*owner,iris_vse_boundary_capture_fn fn){if(iris_vse_boundary_capture_||!owner||!fn)throw std::logic_error("IRIS_VSE_BOUNDARY_NESTED_OR_INVALID_CAPTURE");iris_vse_boundary_owner_=owner;iris_vse_boundary_capture_=fn;}
  void iris_end_vse_boundary_capture(){iris_vse_boundary_capture_=nullptr;iris_vse_boundary_owner_=nullptr;}''')
 edit('riscv/mmu.h','    MMU_OBSERVE_STORE(addr, val, sizeof(T));','''    if(iris_vse_boundary_capture_){
      if(sizeof(T)!=4||xlate_flags.is_special_access()||!iris_pipeline_store_permitted(addr,4))throw std::runtime_error("IRIS_VSE_BOUNDARY_CAPTURE_HANDLER_ACCESS_REFUSED");
      uint32_t bits=0;std::memcpy(&bits,&val,std::min(sizeof(T),sizeof(bits)));std::array<uint8_t,4>known;known.fill(255);if(known_input)std::copy_n(known_input,4,known.begin());
      iris_vse_boundary_capture_(iris_vse_boundary_owner_,addr,bits,known);return;
    }
    MMU_OBSERVE_STORE(addr, val, sizeof(T));''')
 edit('riscv/mmu.h','  mmu_t(simif_t* sim, endianness_t endianness, processor_t* proc, reg_t cache_blocksz);','  mmu_t(simif_t* sim, endianness_t endianness, processor_t* proc, reg_t cache_blocksz);')
 # Fields remain private; off-mode fast store behavior has one null check.
 edit('riscv/mmu.h','  bool mmio_store(reg_t paddr, size_t len, const uint8_t* bytes);','  bool mmio_store(reg_t paddr, size_t len, const uint8_t* bytes);\n  iris_vse_boundary_capture_fn iris_vse_boundary_capture_=nullptr;void*iris_vse_boundary_owner_=nullptr;')
if __name__=='__main__':main()
