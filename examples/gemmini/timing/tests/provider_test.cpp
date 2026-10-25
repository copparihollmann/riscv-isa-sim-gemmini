#include "provider.hpp"
#include <cassert>
#include <iostream>

namespace G = gemmini_annotated_spike;
using merlin_timing::Engine;
using merlin_timing::Event;
using merlin_timing::ValueId;

std::uint64_t packet(std::uint32_t address, std::uint32_t rows, std::uint32_t cols) {
  return address | (std::uint64_t(cols) << 32) | (std::uint64_t(rows) << 48);
}
G::HardwareConfig hardware() { return {4, 64, 32, 1, 4, 32, true, true, 0}; }
G::ResourceBindings resources() { return {0, 1, 2, 3, 4, 5}; }
G::Parameters prices() {
  G::Parameters result;
  for (const auto *kind : {"config", "preload", "flush", "counter", "fence", "load", "store", "pool_store",
                          "normalize1", "normalize2", "normalize3", "normalize4", "normalize5", "normalize6", "normalize7", "compute_ws", "compute_os", "compute_ws_relu", "compute_os_relu",
                          "store_act1", "store_act2", "store_act3", "store_act4", "pool_store_act1"}) {
    result[std::string(kind) + ".latency_cycles"] = 1;
    result[std::string(kind) + ".occupancy_cycles"] = 1;
    for (const auto *field : {"latency_per_byte_cycles", "occupancy_per_byte_cycles",
                             "latency_per_mac_cycles", "occupancy_per_mac_cycles"})
      result[std::string(kind) + "." + field] = 1;
  }
  result["dma.read_bytes_per_cycle"] = 8;
  result["dma.write_bytes_per_cycle"] = 8;
  return result;
}
Engine engine() { return Engine(128, {{0, 1, 4}, {1, 1, 4}, {2, 1, 4}, {3, 1, 4}, {4, 1, 4}, {5, 1, 4}}); }
void load_config(G::TargetObserver &p, unsigned id = 0, unsigned stride = 32,
                 unsigned block = 4, bool shrunk = false, unsigned pixels = 1) {
  p.observe_command(0, 0, 1 | (id << 3) | (std::uint64_t(shrunk) << 2) |
                    (std::uint64_t(pixels) << 8) | (std::uint64_t(block) << 16), stride);
}
void store_config(G::TargetObserver &p, std::uint64_t more = 0, unsigned stride = 32) {
  p.observe_command(0, 0, 2 | more, stride);
}
void execute_config(G::TargetObserver &p, bool ws = true, unsigned a_stride = 1,
                    unsigned c_stride = 1, bool a_transpose = false, bool b_transpose = false) {
  p.observe_command(0, 0, std::uint64_t(ws) << 2 | std::uint64_t(a_stride) << 16 |
                    std::uint64_t(a_transpose) << 8 | std::uint64_t(b_transpose) << 9,
                    std::uint64_t(c_stride) << 48);
}

void movement() {
  auto e = engine(); G::TargetObserver p(e, hardware(), prices(), resources());
  load_config(p);
  auto moved = p.observe_command(17, 2, 0x1000, packet(0, 2, 6));
  assert(moved.ready && p.last_pc() == 17);
  assert(p.counters().requested_read_bytes == 12 && p.counters().local_write_bytes == 12);
  assert(p.transfers().size() == 1 && p.transfers()[0].row_stride == 32);
  load_config(p, 1);
  p.observe_command(0, 1, 0x2000, packet(0x80000000, 2, 4));
  assert(p.counters().requested_read_bytes == 44);
  load_config(p, 2, 8, 4, true);
  auto third = p.observe_command(0, 14, 0x3000, packet(0xc0000000, 2, 4));
  assert(third.ready && p.last_legal() && p.counters().requested_read_bytes == 52);
  assert(p.counters().local_read_bytes == 32);
  p.observe_command(0, 2, 0, packet(16, 4, 4));
  assert(p.transfers().empty() && p.counters().requested_read_bytes == 52);
  assert(p.counters().zero_fill_elements == 16);
  assert(e.report().complete);
}

void pixel_expansion_and_zero_extents() {
  auto e = engine(); G::TargetObserver p(e, hardware(), prices(), resources());
  load_config(p, 0, 4, 4, false, 2);
  p.observe_command(0, 2, 0x1000, packet(1, 2, 2));
  assert(p.counters().requested_read_bytes == 4);
  assert(p.counters().local_write_bytes == 8);
  const auto before = p.counters().requested_read_bytes;
  assert(p.observe_command(0, 2, 0x1000, packet(0, 0, 2)).ready);
  assert(p.counters().requested_read_bytes == before);
  load_config(p, 0, 4, 4, false, 3);
  assert(!p.observe_command(0, 2, 0x1000, packet(2, 1, 2)).ready);
  assert(!p.last_legal() && p.unknown_semantics().count("pixel_column_bounds"));
}

void output_width_and_pooling() {
  auto e = engine(); G::TargetObserver p(e, hardware(), prices(), resources());
  store_config(p);
  assert(p.observe_command(0, 3, 0x1000, packet(0xa0000000, 2, 4)).ready);
  assert(p.counters().requested_write_bytes == 32);
  p.observe_command(0, 3, 0x2000, packet(0x80000000, 2, 4));
  assert(p.counters().requested_write_bytes == 40);
  const std::uint64_t fields = 2ull << 4 | 2ull << 6 | 1ull << 8 | 1ull << 10 |
                               7ull << 24 | 2ull << 32 | 3ull << 40 | 3ull << 48 | 5ull << 56;
  store_config(p, fields, 8);
  p.observe_command(0, 3, 0x4000, packet(0x80000000, 1, 2));
  assert(p.counters().requested_write_bytes == 52 && p.counters().pooled_outputs == 12);
  assert(p.transfers().size() == 2 && p.transfers()[1].address == 0x4038);
  assert(p.transfers()[0].rows == 3 && p.transfers()[0].row_bytes == 2);
  assert(p.transfers()[0].row_stride == 8 && e.report().complete);
}

void explicit_pool_relu_service_relation() {
  auto selected = prices();
  for (auto it = selected.begin(); it != selected.end();)
    if (it->first.find("pool_store_act1.") == 0) it = selected.erase(it); else ++it;
  const auto original = selected;
  const std::uint64_t fields = 2ull << 4 | 2ull << 6 | 1ull << 8 | 1ull << 10 |
                               7ull << 24 | 2ull << 32 | 3ull << 40 | 3ull << 48 | 5ull << 56;
  const auto run = [&](G::Parameters parameters, bool relu) {
    auto e = engine(); G::TargetObserver p(e, hardware(), parameters, resources());
    store_config(p, fields | (std::uint64_t(relu) << 2), 8);
    auto result = p.observe_command(0, 3, 0x4000, packet(0x80000000, 1, 2));
    assert(p.counters().pooled_outputs == 12 && p.counters().requested_write_bytes == 12);
    assert(p.primitive_classes().count(relu ? "pool_store_act1" : "pool_store"));
    return result.ready;
  };
  assert(!run(original, true)); // Legacy selected model retains UNKNOWN.
  G::apply_pool_relu_shared_pipeline(selected);
  assert(run(selected, true) == run(original, false));
  assert(run(selected, true));
  for (const auto &entry : original) assert(selected.at(entry.first) == entry.second);
  bool rejected = false;
  try { G::apply_pool_relu_shared_pipeline(selected); }
  catch (const std::invalid_argument &) { rejected = true; }
  assert(rejected); // Explicit class prices and relation cannot coexist.
  auto missing = original;
  missing.erase("pool_store.latency_cycles");
  G::apply_pool_relu_shared_pipeline(missing);
  assert(!run(missing, true)); // Relation does not invent a missing base price.
}

void selected_accumulator_arrival() {
  auto e=engine(); auto h=hardware(); h.accumulator_readout_arrival=8;
  std::optional<G::TransferPhase> observed;
  std::optional<G::Cycle> latency;
  G::TargetObserver p(e,h,prices(),resources(),0,
      [](auto){return G::TransferEffects{{},{},{{5,1,160}},160};},
      [&](const auto &kind,const auto &event,auto,auto,auto,auto,const auto &phase){
        if(kind=="store") {observed=phase;latency=event.latency;}
        return merlin_timing::Result{0,0,0,merlin_timing::UnknownReason::none};
      });
  store_config(p,0,16);
  p.observe_command(0,3,0x1000,packet(0xa0000000,4,4));
  assert(observed && observed->arrival==8 && observed->demands.size()==1 && latency==168);
  p.observe_command(0,3,0x1000,packet(0x80000000,4,4));
  assert(!observed && latency==160); // Narrow/scaled forms stay on old path.
  p.observe_command(0,3,0x1000,packet(0xa0000000,4,3));
  assert(!observed); // Partial row remains outside selected first-data contract.
  auto stream_engine=engine();h.accumulator_streamed_readout=true;
  unsigned calls=0;
  G::TargetObserver stream(stream_engine,h,prices(),resources(),0,
      [&](auto transfers) {
        assert(transfers.size==1 && transfers[0].rows==1 && transfers[0].row_bytes==16);
        assert(transfers[0].address==0x1000+16*calls++);
        return G::TransferEffects{{},{},{{5,1,4}},4};
      },[&](const auto &kind,const auto &,auto,auto,auto,auto,const auto &phase) {
        if(kind=="store") {
          assert(calls==0 && phase && phase->rows.empty() && phase->row_transfers.size()==4);
          for(const auto &row:phase->row_transfers)phase->row_memory({&row,1});
        }
        return merlin_timing::Result{0,0,0,merlin_timing::UnknownReason::none};
      });
  store_config(stream,0,16);
  stream.observe_command(0,3,0x1000,packet(0xa0000000,4,4));assert(calls==4);
  for(bool enabled:{false,true}) for(unsigned stride:{8,16,24,32,64}) {
    auto se=engine();h.accumulator_streamed_strided_rows=enabled;
    std::optional<G::TransferPhase> seen;
    G::TargetObserver strided(se,h,prices(),resources(),0,
        [](auto){return G::TransferEffects{{},{},{},0};},
        [&](const auto &kind,const auto &,auto,auto,auto,auto,const auto &phase) {
          if(kind=="store")seen=phase;
          return merlin_timing::Result{0,0,0,merlin_timing::UnknownReason::none};
        });
    store_config(strided,0,stride);
    strided.observe_command(0,3,0x1000,packet(0xa0000000,4,4));
    const bool admitted=stride==16 || (enabled && stride>=16 && stride%16==0);
    assert(bool(seen)==admitted);
    if(admitted) {
      assert(seen->row_transfers.size()==4);
      for(unsigned i=0;i<4;++i) {
        const auto &row=seen->row_transfers[i];
        assert(row.address==0x1000+i*stride && row.row_bytes==16 && row.rows==1);
      }
    }
  }
}

void selected_partial_raw_arrival_and_mask_refusal() {
  for(unsigned width:{1,2,3,4,8,16}) for(unsigned address:{4096,4100})
      for(unsigned stride:{8,16,32,64}) for(bool enabled:{false,true}) {
    auto h=hardware();h.dim=16;h.accumulator_readout_arrival=8;
    h.accumulator_streamed_readout=true;h.accumulator_streamed_strided_rows=true;
    h.accumulator_streamed_partial_raw_rows=enabled;
    h.writer_beat_bytes=16;h.writer_max_request_bytes=64;
    auto e=engine();std::optional<G::TransferPhase> observed;
    G::TargetObserver observer(e,h,prices(),resources(),0,
        [](auto){return G::TransferEffects{{},{},{},0};},
        [&](const auto &kind,const auto &,auto,auto,auto,auto,const auto &phase) {
          if(kind=="store")observed=phase;
          return merlin_timing::Result{0,0,0,merlin_timing::UnknownReason::none};
        });
    store_config(observer,0,stride);
    observer.observe_command(0,3,address,packet(0xa0000000,2,width));
    const auto bytes=width*4;
    const bool raw=(width==16 || (enabled && (width==4 || width==8)));
    const bool streamed=raw && address%bytes==0 && stride>=bytes && stride%bytes==0;
    assert(bool(observed && !observed->row_transfers.empty())==streamed);
    if(streamed) {
      assert(observed->row_transfers.size()==2 && observed->row_bytes==bytes);
      assert(observed->row_transfers[0].address==address);
      assert(observed->row_transfers[1].address==address+stride);
      assert(observed->row_transfers[1].row_bytes==bytes);
    }
  }
  for(bool refuse:{false,true}) for(bool full:{false,true}) for(unsigned width:{1,4,16}) {
    auto h=hardware();h.dim=16;h.refuse_masked_write_approximation=refuse;
    h.writer_beat_bytes=16;h.writer_max_request_bytes=64;
    auto e=engine();G::TargetObserver observer(e,h,prices(),resources());
    const auto bytes=width*(full?4:1);store_config(observer,0,bytes);
    auto r=observer.observe_command(0,3,4096,packet(full?0xa0000000:0x80000000,2,width));
    const bool known=!refuse || bytes>=16;
    assert(bool(r.ready)==known);
    if(!known)assert(observer.unknown_timing().count("memory:masked_or_nonuniform_write_timing_unmodeled"));
  }
}

void persistent_weights_and_hazards() {
  auto e = engine(); G::TargetObserver p(e, hardware(), prices(), resources());
  load_config(p); execute_config(p);
  p.observe_command(0, 6, packet(8, 2, 3), packet(0x80000000, 2, 3));
  const auto compute = p.observe_command(0, 4, packet(0, 2, 4), packet(0xffffffff, 0, 0));
  assert(compute.ready && p.counters().useful_shape_macs == 12);
  const auto independent = p.observe_command(0, 2, 0x1000, packet(32, 2, 4));
  assert(independent.start && *independent.start < *compute.ready);
  const auto alias = p.observe_command(0, 2, 0x2000, packet(0, 2, 4));
  assert(alias.start && *alias.start >= *compute.ready);
  p.observe_command(0, 6, packet(20, 1, 1), packet(0x80000004, 2, 3));
  assert(p.observe_command(0, 5, packet(0, 2, 4), packet(0xffffffff, 0, 0)).ready);
  assert(p.counters().useful_shape_macs == 24 && p.counters().nominal_padded_macs == 128);
  const auto frontier = e.report().modeled_makespan;
  const auto fence = p.observe_fence();
  assert(fence.start && *fence.start >= frontier && e.report().complete);
}

void configuration_hazard_and_transpose() {
  auto e = engine(); G::TargetObserver p(e, hardware(), prices(), resources());
  load_config(p);
  const auto pending = p.observe_command(0, 2, 0x1000, packet(0, 4, 4));
  const auto cfg = p.observe_command(0, 0, 1 | 4ull << 16, 0);
  assert(cfg.start && pending.ready && *cfg.start >= *pending.ready);
  execute_config(p, true, 2, 2, true, false);
  p.observe_command(0, 6, packet(16, 3, 2), packet(0x80000000, 2, 2));
  assert(p.observe_command(0, 4, packet(0, 2, 3), packet(0xffffffff, 0, 0)).ready);
  assert(p.counters().useful_shape_macs == 12);
  assert(p.counters().local_read_bytes == 12);
}

void shared_memory_bridge() {
  auto e = engine();
  const ValueId line = 120;
  Event host_write; host_write.writes = {&line, 1}; host_write.latency = 50;
  e.submit(host_write);
  unsigned calls = 0;
  G::TransferHook memory = [&](merlin_timing::View<G::Transfer> transfers) {
    ++calls; assert(transfers.size == 1 && transfers[0].row_bytes == 4);
    G::TransferEffects effects;
    (transfers[0].write ? effects.writes : effects.reads).push_back(line);
    effects.demands.push_back({4, 1, 7}); effects.minimum_latency = 7;
    return effects;
  };
  G::TargetObserver p(e, hardware(), prices(), resources(), 0, memory);
  load_config(p); store_config(p);
  const auto loaded = p.observe_command(0, 2, 0x1000, packet(0, 1, 4));
  assert(loaded.start && *loaded.start >= 50);
  const auto stored = p.observe_command(0, 3, 0x1000, packet(0, 1, 4));
  Event host_read; host_read.reads = {&line, 1}; host_read.latency = 1;
  const auto after = e.submit(host_read);
  assert(after.start && stored.ready && *after.start >= *stored.ready);
  assert(calls == 2);
  for (const auto &resource : e.report().resources)
    if (resource.id == 4) assert(resource.reservations == 2); // no standalone DMA double charge
}

void unknowns_and_no_fsm() {
  auto e = engine(); auto missing = prices(); missing.erase("load.latency_per_byte_cycles");
  G::TargetObserver p(e, hardware(), missing, resources()); load_config(p);
  assert(!p.observe_command(0, 2, 0x1000, packet(0, 1, 4)).ready);
  assert(!e.report().complete && p.unknown_timing().count("price:load.latency_per_byte_cycles"));
  for (unsigned funct : {8, 9, 13, 15, 16, 21}) {
    auto target_engine = engine(); G::TargetObserver target(target_engine, hardware(), prices(), resources());
    assert(!target.observe_command(0, funct, 0, 0).ready);
    assert(target.counters().illegal_events == 1 && target.unknown_semantics().count("fsm_instruction"));
  }
  auto no_resource_engine = engine(); G::TargetObserver no_resource(no_resource_engine, hardware(), prices(), {});
  assert(!no_resource.observe_command(0, 7, 0, 0).ready);
  assert(no_resource.unknown_timing().count("resource_binding"));
}

void illegal_bounds_and_normalization() {
  auto e = engine(); G::TargetObserver p(e, hardware(), prices(), resources());
  store_config(p);
  assert(!p.observe_command(0, 3, 0x1000, packet(0, 65535, 65535)).ready);
  assert(p.counters().illegal_events == 1);
  auto n = engine(); G::TargetObserver norm(n, hardware(), prices(), resources());
  store_config(norm); norm.observe_command(0, 0, 3 | 1ull << 17, 0);
  assert(norm.observe_command(0, 3, 0x2000, packet(0x84000000, 2, 6)).ready);
  assert(norm.transfers().empty() && norm.counters().requested_write_bytes == 0);
  assert(norm.counters().local_read_bytes == 48);
  auto d = engine(); G::TargetObserver overflow(d, hardware(), prices(), resources());
  load_config(overflow);
  assert(!overflow.observe_command(0, 2, std::numeric_limits<std::uint64_t>::max() - 1, packet(0, 2, 4)).ready);
  assert(overflow.unknown_semantics().count("dram_address_overflow"));
}

void configuration_and_mode_boundaries() {
  auto e = engine(); G::TargetObserver p(e, hardware(), prices(), resources());
  assert(!p.observe_command(0, 2, 0x1000, packet(0, 1, 4)).ready);
  assert(p.unknown_semantics().count("unconfigured_load"));
  auto m = engine(); G::TargetObserver modes(m, hardware(), prices(), resources());
  modes.observe_command(0, 0, 1ull << 16 | 1ull << 3, 1ull << 48); // OS, RELU
  modes.observe_command(0, 6, packet(0xffffffff, 0, 0), packet(32, 2, 2));
  assert(modes.observe_command(0, 4, packet(0, 2, 3), packet(8, 3, 2)).ready);
  assert(modes.primitive_classes().count("compute_os_relu"));
  execute_config(modes, true);
  modes.observe_command(0, 6, packet(0xffffffff, 0, 0), packet(0x80000000, 2, 2));
  assert(modes.observe_command(0, 5, packet(0, 2, 3), packet(0xffffffff, 0, 0)).ready);
  assert(modes.counters().useful_shape_macs == 20); // persistent OS result becomes WS weights
  load_config(modes);
  assert(modes.observe_command(0, 7, 0, 0).ready);
  assert(modes.observe_command(0, 2, 0x1000, packet(48, 1, 4)).ready); // FLUSH preserves configuration
  for (unsigned command = 1; command < 8; ++command) {
    auto n = engine(); G::TargetObserver normalization(n, hardware(), prices(), resources());
    store_config(normalization); normalization.observe_command(0, 0, 3 | 1ull << 17, 0);
    normalization.observe_command(0, 0, 3, 0);
    normalization.observe_command(0, 0, 3 | 1ull << 18, 0);
    if (command == 3 || command == 4)
      normalization.observe_command(0, 3, 0x2000, packet(0x88000000, 2, 6)); // MEAN produces the dependency
    assert(normalization.observe_command(0, 3, 0x2000, packet(0x80000000 | command << 26, 2, 6)).ready);
    assert(normalization.primitive_classes().count("normalize" + std::to_string(command)));
    assert(normalization.transfers().empty());
  }
  auto f = engine(); auto restricted = hardware(); restricted.full_width_accumulator_readout = false;
  G::TargetObserver narrow(f, restricted, prices(), resources()); store_config(narrow);
  assert(!narrow.observe_command(0, 3, 0x1000, packet(0xa0000000, 1, 1)).ready);
  assert(narrow.unknown_semantics().count("full_width_readout_unavailable"));
  auto a = engine(); auto uninitialized = hardware(); uninitialized.reset_accumulator_activation.reset();
  G::TargetObserver explicit_activation(a, uninitialized, prices(), resources());
  store_config(explicit_activation, 1ull << 2); store_config(explicit_activation);
  assert(explicit_activation.observe_command(0, 3, 0x1000, packet(0x80000000, 1, 1)).ready);
  auto clear_engine = engine();
  G::TargetObserver clear(clear_engine, uninitialized, prices(), resources());
  clear.observe_command(0, 0, 3, 0); // OR with zero cannot initialize or clear activation bits.
  store_config(clear);
  assert(!clear.observe_command(0, 3, 0x1000, packet(0x80000000, 1, 1)).ready);
  assert(clear.unknown_semantics().count("unconfigured_accumulator_activation"));
  auto sticky_engine = engine();
  G::TargetObserver sticky(sticky_engine, hardware(), prices(), resources());
  store_config(sticky);
  sticky.observe_command(0, 0, 3, 0);
  sticky.observe_command(0, 0, 3 | 1ull << 18, 0);
  sticky.observe_command(0, 3, 0x1000, packet(0x94000000, 1, 1)); // MAX
  sticky.observe_command(0, 3, 0x1000, packet(0x9c000000, 1, 1)); // INV_SUM_EXP
  sticky.observe_command(0, 0, 3 | 1ull << 16, 0); // NONE -> SOFTMAX
  sticky.observe_command(0, 0, 3, 0); // SOFTMAX OR zero remains SOFTMAX
  store_config(sticky); // Zero base activation also preserves SOFTMAX.
  assert(sticky.observe_command(0, 3, 0x1000, packet(0x80000000, 1, 1)).ready);
  assert(sticky.primitive_classes().count("store_act4"));
  auto missing_engine = engine();
  G::TargetObserver missing(missing_engine, hardware(), prices(), resources());
  store_config(missing, 2ull << 2);
  assert(!missing.observe_command(0, 3, 0x1000, packet(0x80000000, 1, 1)).ready);
  assert(missing.unknown_semantics().count("unconfigured_normalization"));
  auto bank_engine = engine();
  G::TargetObserver banks(bank_engine, hardware(), prices(), resources());
  store_config(banks); banks.observe_command(0, 0, 3 | 1ull << 17, 0);
  banks.observe_command(0, 3, 0x1000, packet(0x88000000, 1, 1)); // MEAN
  banks.observe_command(0, 3, 0x1000, packet(0x90000000, 1, 1)); // INV_STDDEV
  store_config(banks, 2ull << 2);
  const auto readout = banks.observe_command(0, 3, 0x1000, packet(0x80000000, 1, 1));
  assert(readout.ready && bank_engine.ready(64 + 32 + 7) == readout.ready);
}

void disabled_normalization_feature() {
  auto e=engine(); auto h=hardware(); h.normalizations=false;
  G::TargetObserver p(e,h,prices(),resources());
  store_config(p,1ull<<2); store_config(p);
  auto result=p.observe_command(0,0,3ull|(1ull<<17),0);
  assert(!result.ready && !p.last_legal());
  assert(p.unknown_semantics().count("normalization_feature_disabled"));
  auto enabled_engine=engine(); h.normalizations=true;
  G::TargetObserver enabled(enabled_engine,h,prices(),resources());
  assert(enabled.observe_command(0,0,3ull|(1ull<<17),0).ready);
}

int main() {
  // Opt-in row producer eligibility is decoded from actual load configuration,
  // not a caller label. Partial, nonidentity, zero-fill and ACC retain legacy.
  for(unsigned variant=0;variant<6;++variant) {
    auto hw=hardware();hw.dim=16;hw.scratchpad_row_loads=true;
    auto e=engine();bool selected=false;unsigned memory_calls=0;
    G::TargetObserver p(e,hw,prices(),resources(),0,[&](merlin_timing::View<G::Transfer>) {
      ++memory_calls;return G::TransferEffects{{},{},{},merlin_timing::Cycle{1}};
    },[&](const std::string &kind,const Event &event,std::optional<merlin_timing::Cycle>,
        std::uint32_t,std::uint64_t,std::uint64_t,const std::optional<G::TransferPhase> &phase) {
      if(kind=="load")selected=phase && phase->scratchpad_load;
      return e.submit(event);
    });
    p.observe_command(0,0,1ull|(1ull<<8)|(16ull<<16)|
        (std::uint64_t(variant==1?0x40000000u:0x3f800000u)<<32),32);
    p.observe_command(0,2,variant==2?0:variant==3?4097:4096,
        packet(variant==4?0x80000000:0,2,variant==5?15:16));
    assert(selected==(variant==0));
    assert(memory_calls==(variant==0 || variant==2?0u:1u));
  }

  // Partial reads keep useful bytes distinct from whole-beat Get traffic.
  // Adjacent logical rows may request the same physical beat independently.
  for(unsigned variant=0;variant<5;++variant) {
    auto hw=hardware();hw.dim=16;hw.scratchpad_row_loads=true;
    hw.scratchpad_partial_row_loads=variant!=1;
    auto e=engine();std::optional<G::TransferPhase> captured;
    G::TargetObserver p(e,hw,prices(),resources(),0,[](merlin_timing::View<G::Transfer>) {
      return G::TransferEffects{{},{},{},merlin_timing::Cycle{1}};
    },[&](const std::string &kind,const Event &event,std::optional<merlin_timing::Cycle>,
        std::uint32_t,std::uint64_t,std::uint64_t,const std::optional<G::TransferPhase> &phase) {
      if(kind=="load")captured=phase;
      return e.submit(event);
    });
    const auto base=variant==2?4099u:4096u;
    const auto stride=variant==3?0u:4u;
    const auto columns=variant==4?17u:4u;
    p.observe_command(0,0,1ull|(1ull<<8)|(16ull<<16)|(0x3f800000ull<<32),stride);
    p.observe_command(0,2,base,packet(0,8,columns));
    if(variant) {assert(!captured);continue;}
    assert(captured && captured->scratchpad_load && captured->row_bytes==4);
    assert(captured->row_transfers.size()==8);
    for(unsigned i=0;i<8;++i) {
      const auto &t=captured->row_transfers[i];
      assert(t.address==4096+(i/4)*16 && t.row_bytes==16 && t.rows==1 && !t.write);
    }
    assert(p.counters().requested_read_bytes==32); // transport is 8*16 instead
  }

  selected_partial_raw_arrival_and_mask_refusal();
  disabled_normalization_feature();
  assert(G::registered_primitive_class("normalize7") && G::registered_primitive_class("unknown"));
  assert(!G::registered_primitive_class("normalize8") && !G::registered_primitive_class("store_act5"));
  movement(); pixel_expansion_and_zero_extents(); output_width_and_pooling(); explicit_pool_relu_service_relation(); selected_accumulator_arrival();
  persistent_weights_and_hazards(); configuration_hazard_and_transpose();
  shared_memory_bridge(); unknowns_and_no_fsm(); illegal_bounds_and_normalization();
  configuration_and_mode_boundaries();
  std::cout << "9 independent target observer controls passed\n";
}
