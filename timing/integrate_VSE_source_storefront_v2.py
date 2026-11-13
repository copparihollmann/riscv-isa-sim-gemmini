#!/usr/bin/env python3
"""New e24 child hooks, preserving original synthetic mode and all OFF behavior."""
from pathlib import Path
R=Path(__file__).resolve().parents[1];S=R/'pipeline/riscv-isa-sim-VSE-source-storefront-v2'
def edit(name,old,new):
 p=S/name;s=p.read_text();assert s.count(old)==1,(name,old[:100]);p.write_text(s.replace(old,new))
def main():
 edit('riscv/iris_timing_adapter.h','    bool vse_boundary_test=false;','    bool vse_source_storefront=false;\n    bool vse_boundary_test=false;')
 edit('riscv/iris_timing_adapter.h','  struct VseBoundaryCommand;','''  struct VseSourceRuntime;
  std::array<std::shared_ptr<VseSourceRuntime>,2>vse_source_runtime_{};
  void vse_source_schedule(unsigned);
  void vse_source_step(unsigned,Cycle,bool);
  void vse_source_idle_advance(Cycle);
  bool vse_source_transport_drained(unsigned)const;
  void vse_source_totals(std::ostream&)const;
  struct VseBoundaryCommand;''')
 edit('riscv/iris_timing_adapter.cc','f[1]!="SYNTHETIC-DIRECTED-TEST-ONLY-v1"','(f[1]!="SYNTHETIC-DIRECTED-TEST-ONLY-v1"&&f[1]!="SOURCE-STOREFRONT-SYNTHETIC-D-ONLY-v2")')
 edit('riscv/iris_timing_adapter.cc','p.vse_boundary_test=true;p.vse_boundary_hart=h;','p.vse_boundary_test=true;p.vse_source_storefront=f[1]=="SOURCE-STOREFRONT-SYNTHETIC-D-ONLY-v2";p.vse_boundary_hart=h;')
 edit('riscv/iris_timing_adapter.cc','  if(p.vse_boundary_test&&','  if(p.vse_source_storefront&&(p.base_hz!=500000000ULL||p.harts[p.vse_boundary_hart].divider!=1||p.max_cycles>UINT64_MAX/2))throw std::runtime_error("IRIS_VSE_SOURCE_REQUIRES_BASE500MHZ_HART500MHZ_MASTER1GHZ");\n  if(p.vse_boundary_test&&')
 edit('riscv/iris_timing_adapter.cc','advance(before,now);if(profile_.vse_boundary_test)','advance(before,now);if(profile_.vse_source_storefront)vse_source_idle_advance(now);if(profile_.vse_boundary_test)')
 edit('riscv/iris_timing_adapter.cc','#include "iris_vse_live_boundary.inc"','#include "iris_vse_live_boundary.inc"\n#include "iris_vse_source_storefront.inc"')
 edit('riscv/iris_vse_live_boundary.inc','void iris_timing_adapter::vse_boundary_schedule(unsigned h){','void iris_timing_adapter::vse_boundary_schedule(unsigned h){\n if(profile_.vse_source_storefront){vse_source_schedule(h);return;}')
 edit('riscv/iris_vse_live_boundary.inc','   if(c->cache_owner){empirical_cache_->complete','   if(profile_.vse_source_storefront&&!vse_source_transport_drained(h))throw std::logic_error("IRIS_VSE_SOURCE_FINAL_SIQ_RELEASE_WITH_TRANSPORT_OWNER");\n   if(c->cache_owner){empirical_cache_->complete')
 edit('riscv/iris_empirical_features.inc',' vse_boundary_totals(out);',' vse_boundary_totals(out);vse_source_totals(out);')
if __name__=='__main__':main()
