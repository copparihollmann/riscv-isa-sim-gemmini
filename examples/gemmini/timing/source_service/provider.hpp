#ifndef GEMMINI_ANNOTATED_SPIKE_PROVIDER_HPP
#define GEMMINI_ANNOTATED_SPIKE_PROVIDER_HPP

// Observation only. Encodings and state transitions follow public libgemmini
// Receiver source is selected by the target profile; no kernel library is included.
#include <merlin_timing/engine.hpp>

#include "reader_packets.hpp"
#include "readout_geometry.hpp"
#include "writer_packets.hpp"
#include <array>
#include <cmath>
#include <functional>
#include <limits>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace gemmini_annotated_spike {
using merlin_timing::Cycle;
using merlin_timing::Demand;
using merlin_timing::Engine;
using merlin_timing::Event;
using merlin_timing::ResourceId;
using merlin_timing::Result;
using merlin_timing::ValueId;
using merlin_timing::View;
using Parameters = std::map<std::string, double>;

// Explicit selected-RTL service relation, never a missing-price fallback.
// AccumulatorScale's ReLU mux precedes the same elastic scale pipeline used
// without activation. Pool addresses, transfers and dependencies remain those
// of the observed pool_store_act1 command. Missing base terms remain UNKNOWN.
inline void apply_pool_relu_shared_pipeline(Parameters &parameters) {
  constexpr const char *fields[] = {"latency_cycles", "occupancy_cycles", "latency_per_byte_cycles",
      "occupancy_per_byte_cycles", "latency_per_mac_cycles", "occupancy_per_mac_cycles"};
  for (const auto *field : fields)
    if (parameters.count(std::string("pool_store_act1.") + field))
      throw std::invalid_argument("pool ReLU shared pipeline conflicts with explicit prices");
  for (const auto *field : fields) {
    const auto base = parameters.find(std::string("pool_store.") + field);
    if (base != parameters.end()) parameters.emplace(std::string("pool_store_act1.") + field, base->second);
  }
}

// Canonical observable class vocabulary. Diagnostics deliberately have no
// hardware price schema; they describe unsupported/unconfigured commands.
inline constexpr const char *priced_primitive_classes[] = {
    "config", "preload", "flush", "counter", "fence", "load", "store", "pool_store",
    "normalize1", "normalize2", "normalize3", "normalize4", "normalize5", "normalize6", "normalize7",
    "compute_ws", "compute_os", "compute_ws_relu", "compute_os_relu",
    "store_act1", "store_act2", "store_act3", "store_act4", "pool_store_act1"};
inline constexpr const char *diagnostic_primitive_classes[] = {"unknown", "compute"};

inline bool registered_primitive_class(const std::string &name) {
  for (const auto *entry : priced_primitive_classes) if (name == entry) return true;
  for (const auto *entry : diagnostic_primitive_classes) if (name == entry) return true;
  return false;
}

struct HardwareConfig {
  std::uint32_t dim, scratchpad_rows, accumulator_rows;
  std::uint32_t element_bytes, accumulator_bytes;
  std::uint32_t address_bits;
  bool first_layer_optimizations;
  bool full_width_accumulator_readout;
  std::optional<std::uint8_t> reset_accumulator_activation;
  // Absent retains legacy profiles; explicit false forbids CONFIG_NORM.
  std::optional<bool> normalizations = std::nullopt;
  // Selected first-data pipeline before full-width ACC StreamWriter requests.
  std::optional<Cycle> accumulator_readout_arrival = std::nullopt;
  bool accumulator_streamed_readout = false;
  bool scratchpad_row_loads = false;
  bool scratchpad_packet_loads = false;
  bool accumulator_readout_packet_geometry=false;
  std::uint32_t writer_beat_bytes=0,writer_max_request_bytes=0;
  bool accumulator_readout_full_packets=false;
  bool source_identity_ingress=false;
  bool wide_scratchpad_row_publication=false;
  std::uint32_t selected_mvin_cols_bits=0,selected_mvin_rows_bits=0;
  bool source_full_accumulator_load=false;
  bool source_masked_i8_readout=false;
};

// An absent binding is an unknown resource, never an assumed single-lane queue.
struct ResourceBindings {
  std::optional<ResourceId> config, load, store, execute, dma_read, dma_write;
};

struct Transfer {
  std::uint64_t address, rows, row_bytes, row_stride;
  bool write;
};

struct TransferEffects {
  std::vector<ValueId> reads, writes;
  std::vector<Demand> demands;
  std::optional<Cycle> minimum_latency;
};
using TransferHook = std::function<TransferEffects(View<Transfer>)>;
struct TransferPhase {
  Cycle arrival;
  std::vector<Demand> demands;
  std::vector<TransferEffects> rows{};
  std::uint64_t row_bytes=0;
  std::vector<Transfer> row_transfers{};
  TransferHook row_memory{};
  bool scratchpad_load = false;
  std::vector<ReaderPacket> reader_packets{};
  std::vector<ValueId> reader_destinations{};
  bool individual_row_publication=false;
  std::vector<std::vector<WriterPacket>> writer_packets{};
  bool full_accumulator_load=false;
  std::uint32_t full_accumulator_repeats=0;
};
// Explicit v2 timing-only hook; the v1 functional/count path stays unchanged.
using SubmitHook = std::function<Result(const std::string &, const Event &,
    std::optional<Cycle>, std::uint32_t, std::uint64_t, std::uint64_t,
    const std::optional<TransferPhase> &)>;

struct Counters {
  std::array<std::uint64_t, 128> commands{};
  std::uint64_t commands_total = 0, fences = 0;
  std::uint64_t requested_read_bytes = 0, requested_write_bytes = 0;
  std::uint64_t local_read_bytes = 0, local_write_bytes = 0;
  std::uint64_t nominal_padded_macs = 0, useful_shape_macs = 0;
  std::uint64_t zero_fill_elements = 0, pooled_outputs = 0;
  std::uint64_t semantic_unknown_events = 0, illegal_events = 0;
  std::uint64_t load_packet_per_row_publication=0, load_packet_command_publication=0;
  std::uint64_t load_row_stream_publication=0, load_aggregate_publication=0, load_unsupported_publication=0;
  bool accounting_overflow = false;
};

class TargetObserver {
public:
  static std::size_t required_tokens(const HardwareConfig &h) {
    if (h.address_bits != 32 || h.dim == 0 || h.dim > 65535 ||
        h.scratchpad_rows == 0 || h.accumulator_rows == 0 ||
        h.scratchpad_rows > 0x20000000u || h.accumulator_rows > 0x4000000u ||
        h.element_bytes == 0 || h.accumulator_bytes == 0 || h.element_bytes > 8 || h.accumulator_bytes > 8 ||
        (h.reset_accumulator_activation && *h.reset_accumulator_activation > 4))
      throw std::invalid_argument("unsupported or invalid target geometry");
    const std::uint64_t count = std::uint64_t(h.scratchpad_rows) + h.accumulator_rows + 11;
    if (count > std::numeric_limits<std::size_t>::max())
      throw std::overflow_error("target token count exceeds host index range");
    return static_cast<std::size_t>(count);
  }

  TargetObserver(Engine &engine, HardwareConfig hardware, Parameters parameters,
                 ResourceBindings resources, ValueId token_base = 0,
                 TransferHook transfer_hook = {}, SubmitHook submit_hook = {})
      : engine_(engine), h_(hardware), parameters_(std::move(parameters)), resources_(resources),
        base_(token_base), transfer_hook_(std::move(transfer_hook)), submit_hook_(std::move(submit_hook)),
        accumulator_activation_(h_.reset_accumulator_activation),
        accumulator_not_softmax_(accumulator_activation_ && *accumulator_activation_ != 4) {
    if (required_tokens(h_) - 1 > std::numeric_limits<ValueId>::max() - base_)
      throw std::overflow_error("target token range overflows");
    // Bounds are checked before observation, not halfway through a guest run.
    engine_.ready(base_ + required_tokens(h_) - 1);
  }

  Result observe_command(std::uint64_t pc, std::uint32_t funct, std::uint64_t rs1,
                         std::uint64_t rs2, Cycle earliest = 0) {
    begin(pc, earliest);
    funct_ = funct; rs1_ = rs1; rs2_ = rs2;
    add(counters_.commands_total, 1);
    if (funct < counters_.commands.size()) add(counters_.commands[funct], 1);
    if ((funct >= 8 && funct <= 13) || (funct >= 15 && funct <= 21)) {
      fail("fsm_instruction", true);
      invalidate_all();
      return submit("unknown", {}, 0, 0);
    }
    switch (funct) {
    case 0: return configure(rs1, rs2);
    case 1: return load(rs1, rs2, 1);
    case 2: return load(rs1, rs2, 0);
    case 14: return load(rs1, rs2, 2);
    case 3: return store(rs1, rs2);
    case 4: return compute(rs1, rs2, true);
    case 5: return compute(rs1, rs2, false);
    case 6:
      preload_ = {packet(rs1), packet(rs2), true};
      writes_.push_back(state(5));
      return submit("preload", resources_.execute, 0, 0);
    case 7:
      // libgemmini FLUSH performs no functional reset or local-memory clear.
      return submit("flush", resources_.config, 0, 0);
    case 126:
      return submit("counter", resources_.config, 0, 0);
    case 127: return fence();
    default:
      fail("unknown_funct", true);
      invalidate_all();
      return submit("unknown", {}, 0, 0);
    }
  }

  Result observe_fence(Cycle earliest = 0) {
    begin(0, earliest);
    return fence();
  }

  const Counters &counters() const { return counters_; }
  const std::map<std::string, std::uint64_t> &unknown_semantics() const { return semantic_reasons_; }
  const std::map<std::string, std::uint64_t> &unknown_timing() const { return timing_reasons_; }
  const std::vector<Transfer> &transfers() const { return transfers_; }
  const std::map<std::string, std::uint64_t> &primitive_classes() const { return primitive_classes_; }
  std::uint64_t last_pc() const { return pc_; }
  bool last_semantics_known() const { return semantic_known_; }
  bool last_legal() const { return legal_; }

private:
  struct Packet { std::uint32_t address, rows, cols; };
  struct LoadState {
    std::uint64_t stride = 0;
    std::uint32_t block_stride = 0, pixels = 1;
    bool shrunk = false, valid = false;
    std::uint32_t scale = 0;
  };
  struct ExecuteState {
    std::uint32_t a_stride = 0, c_stride = 0;
    bool ws = false, a_transpose = false, b_transpose = false, valid = false;
    std::optional<std::uint8_t> activation;
  };
  struct StoreState {
    std::uint64_t stride = 0;
    std::uint32_t pool_stride = 0, pool_size = 0, out_dim = 0;
    std::uint32_t porows = 0, pocols = 0, orows = 0, ocols = 0, upad = 0, lpad = 0;
    bool valid = false;
  };
  struct PreloadState { Packet source{}, output{}; bool valid = false; };
  struct NormalizationState { bool mean = false, invstd = false, max = false, invsum = false; };

  Engine &engine_;
  HardwareConfig h_;
  Parameters parameters_;
  ResourceBindings resources_;
  ValueId base_;
  TransferHook transfer_hook_;
  SubmitHook submit_hook_;
  std::uint32_t funct_ = 127;
  std::uint64_t rs1_ = 0, rs2_ = 0;
  std::array<LoadState, 3> loads_{};
  ExecuteState execute_;
  StoreState store_;
  PreloadState preload_;
  Packet pe_weights_{};
  bool pe_shape_known_ = true;
  std::optional<std::uint8_t> accumulator_activation_, norm_stat_;
  bool accumulator_not_softmax_;
  std::array<NormalizationState, 4> normalization_{};
  bool qb_qc_known_ = false, qln2_known_ = false, qln2_inv_known_ = false;
  Counters counters_;
  std::map<std::string, std::uint64_t> semantic_reasons_, timing_reasons_;
  std::map<std::string, std::uint64_t> primitive_classes_;
  std::vector<ValueId> reads_, writes_;
  std::vector<Demand> demands_;
  std::vector<Transfer> transfers_;
  std::uint64_t pc_ = 0;
  Cycle earliest_ = 0;
  bool semantic_known_ = true, legal_ = true, timing_known_ = true, row_aborted_ = false;
  std::uint64_t event_reads_ = 0, event_writes_ = 0;

  static Packet packet(std::uint64_t value) {
    return {std::uint32_t(value), std::uint32_t(value >> 48), std::uint32_t((value >> 32) & 65535)};
  }
  Packet clipped(Packet value) const {
    value.rows = std::min(value.rows, h_.dim);
    value.cols = std::min(value.cols, h_.dim);
    return value;
  }
  ValueId state(std::uint32_t offset) const {
    return base_ + h_.scratchpad_rows + h_.accumulator_rows + offset;
  }
  void begin(std::uint64_t pc, Cycle earliest) {
    pc_ = pc; earliest_ = earliest;
    funct_ = 127; rs1_ = rs2_ = 0;
    reads_.clear(); writes_.clear(); demands_.clear(); transfers_.clear();
    event_reads_ = event_writes_ = 0;
    semantic_known_ = legal_ = timing_known_ = true;
    row_aborted_ = false;
  }
  void add(std::uint64_t &where, std::uint64_t amount) {
    if (amount > std::numeric_limits<std::uint64_t>::max() - where) {
      counters_.accounting_overflow = true;
      timing_known_ = false;
    } else where += amount;
  }
  void fail(const std::string &reason, bool illegal = false) {
    if (semantic_known_) add(counters_.semantic_unknown_events, 1);
    if (illegal && legal_) add(counters_.illegal_events, 1);
    semantic_known_ = false;
    legal_ = legal_ && !illegal;
    add(semantic_reasons_[reason], 1);
  }
  void missing(const std::string &reason) {
    timing_known_ = false;
    add(timing_reasons_[reason], 1);
  }
  void invalidate_all() {
    for (auto &load : loads_) load.valid = false;
    execute_.valid = store_.valid = preload_.valid = false;
    accumulator_activation_.reset(); norm_stat_.reset();
    accumulator_not_softmax_ = false;
    normalization_ = {};
    qb_qc_known_ = qln2_known_ = qln2_inv_known_ = false;
    pe_shape_known_ = false;
    for (std::size_t i = 0; i < required_tokens(h_); ++i) writes_.push_back(base_ + i);
  }
  bool row(bool accumulator, std::uint64_t address, bool write, std::uint64_t bytes) {
    if (!bytes) return true;
    if (row_aborted_) return false;
    if (reads_.size() + writes_.size() >= 1048576) {
      fail("observer_row_work_budget"); row_aborted_ = true; return false;
    }
    if (address >= (accumulator ? h_.accumulator_rows : h_.scratchpad_rows)) {
      fail("local_address_bounds", true); row_aborted_ = true; return false;
    }
    const auto token = base_ + (accumulator ? h_.scratchpad_rows : 0) + address;
    (write ? writes_ : reads_).push_back(token);
    add(write ? event_writes_ : event_reads_, bytes);
    return true;
  }
  void rows(Packet value, bool write, bool accumulator, std::uint64_t stride = 1) {
    if (value.address == 0xffffffffu || !value.rows || !value.cols) return;
    if (value.cols > h_.dim || value.rows > h_.dim) {
      fail("compute_packet_extent", true); row_aborted_ = true; return;
    }
    const auto base = std::uint64_t(value.address & 0x1fffffffu);
    for (std::uint32_t i = 0; i < value.rows; ++i)
      if (!row(accumulator, base + i * stride, write,
               std::uint64_t(value.cols) * (accumulator ? h_.accumulator_bytes : h_.element_bytes))) return;
  }
  std::optional<Cycle> priced(const std::string &key, std::uint64_t bytes, std::uint64_t macs) {
    long double value = 0;
    for (const auto &term : std::array<std::pair<std::string, std::uint64_t>, 3>{{
          {key + "_cycles", 1}, {key + "_per_byte_cycles", bytes}, {key + "_per_mac_cycles", macs}}}) {
      if (!term.second) continue;
      const auto found = parameters_.find(term.first);
      if (found == parameters_.end() || !std::isfinite(found->second) || found->second < 0) {
        missing("price:" + term.first); return {};
      }
      value += static_cast<long double>(found->second) * term.second;
    }
    value = std::ceil(value);
    if (value >= std::ldexp(1.0L, 64)) { missing("cycle_overflow"); return {}; }
    return static_cast<Cycle>(value);
  }
  std::optional<Cycle> dma_time(bool write, std::uint64_t bytes) {
    const auto key = write ? "dma.write_bytes_per_cycle" : "dma.read_bytes_per_cycle";
    const auto found = parameters_.find(key);
    if (found == parameters_.end() || !std::isfinite(found->second) || found->second <= 0) {
      missing(std::string("price:") + key); return {};
    }
    const auto value = std::ceil(static_cast<long double>(bytes) / found->second);
    if (value >= std::ldexp(1.0L, 64)) { missing("cycle_overflow"); return {}; }
    return static_cast<Cycle>(value);
  }
  void demand(std::optional<ResourceId> resource, std::optional<Cycle> occupancy) {
    if (!resource) { missing("resource_binding"); return; }
    for (auto &old : demands_) if (old.resource == *resource) {
      // Aliased bindings mean the same physical reservation. Hold its longest
      // interval; a caller needing serial subphases must supply a larger price.
      if (!old.occupancy || !occupancy) old.occupancy.reset();
      else old.occupancy = std::max(*old.occupancy, *occupancy);
      return;
    }
    demands_.push_back({*resource, 1, occupancy});
  }
  Result unknown_transfer(const std::string &kind) {
    add(counters_.load_unsupported_publication,1);
    missing("unsupported_pitched_load_packet_geometry");
    return submit(kind,resources_.load,0,0);
  }
  Result submit(const std::string &kind, std::optional<ResourceId> resource,
                std::uint64_t bytes, std::uint64_t macs, Cycle arrival = 0, bool row_load = false, bool packet_load = false) {
    add(primitive_classes_[kind], 1);
    auto latency = priced(kind + ".latency", bytes, macs);
    const auto occupancy = priced(kind + ".occupancy", bytes, macs);
    std::optional<TransferPhase> phase;
    if (!submit_hook_) demand(resource, occupancy);
    if (!transfers_.empty() && transfer_hook_) {
      // Preserve per-row transfers rather than dividing aggregate latency.
      // Observe memory lazily when each row reaches the writer: its dependency
      // tokens are scheduled before a subsequent row can recycle them.
      TransferEffects effects;
      const bool streamed = arrival && submit_hook_ && h_.accumulator_streamed_readout &&
          transfers_.size()==1 && ((h_.source_masked_i8_readout && bool(one_beat_writer_rows(
          transfers_[0].address,transfers_[0].rows,transfers_[0].row_bytes,transfers_[0].row_stride))) || (h_.accumulator_readout_packet_geometry ?
          (h_.accumulator_readout_full_packets ? bool(full_writer_rows(transfers_[0].address,transfers_[0].rows,
              transfers_[0].row_bytes,transfers_[0].row_stride,h_.writer_beat_bytes,h_.writer_max_request_bytes)) :
          single_full_row_transactions(transfers_[0].address,transfers_[0].rows,
              transfers_[0].row_bytes,transfers_[0].row_stride,h_.writer_beat_bytes,h_.writer_max_request_bytes)) :
          transfers_[0].row_bytes==std::uint64_t(h_.dim)*h_.accumulator_bytes &&
          transfers_[0].address%transfers_[0].row_bytes==0));
      if(packet_load) {
        if(transfers_.size()!=1 || transfers_[0].write)return unknown_transfer(kind);
        phase=TransferPhase{0,{}};phase->row_bytes=transfers_[0].row_bytes;
        const bool full_accumulator=(std::uint32_t(rs2_)>>31)&1;
        phase->scratchpad_load=!full_accumulator;phase->full_accumulator_load=full_accumulator;phase->row_memory=transfer_hook_;
        if(full_accumulator && transfers_[0].rows==1)
          phase->full_accumulator_repeats=std::uint32_t((rs2_>>48)&65535)-1;
        phase->individual_row_publication=full_accumulator || (h_.wide_scratchpad_row_publication && transfers_[0].row_bytes>h_.dim);
        phase->reader_destinations=writes_; // original block-major physical row mapping, before token sorting
        phase->reader_packets=reader_packets(transfers_[0].address,transfers_[0].rows,
            transfers_[0].row_bytes,full_accumulator && transfers_[0].rows==1 && transfers_[0].row_stride==0 ?
              transfers_[0].row_bytes : transfers_[0].row_stride,16,64,
            full_accumulator ? 64 : h_.wide_scratchpad_row_publication ? (std::uint64_t{1}<<h_.selected_mvin_cols_bits)-1 : 16,
            full_accumulator ? 64 : 16);
        if(phase->reader_packets.empty())return unknown_transfer(kind);
        add(phase->individual_row_publication ? counters_.load_packet_per_row_publication :
            counters_.load_packet_command_publication,1);
        for(const auto &p:phase->reader_packets)
          phase->row_transfers.push_back({p.address,1,p.bytes,p.bytes,false});
        effects.minimum_latency=0;
      } else if(streamed || row_load) {
        phase=TransferPhase{arrival,{}};phase->row_bytes=transfers_[0].row_bytes;
        phase->scratchpad_load=row_load;
        phase->row_memory=transfer_hook_;
        if(streamed && h_.source_masked_i8_readout && one_beat_writer_rows(
            transfers_[0].address,transfers_[0].rows,transfers_[0].row_bytes,transfers_[0].row_stride)){
          phase->writer_packets=*one_beat_writer_rows(transfers_[0].address,transfers_[0].rows,
              transfers_[0].row_bytes,transfers_[0].row_stride);
        }else if(streamed && h_.accumulator_readout_full_packets && !single_full_row_transactions(
            transfers_[0].address,transfers_[0].rows,transfers_[0].row_bytes,transfers_[0].row_stride,
            h_.writer_beat_bytes,h_.writer_max_request_bytes)) {
          const auto packets=full_writer_rows(transfers_[0].address,transfers_[0].rows,
              transfers_[0].row_bytes,transfers_[0].row_stride,h_.writer_beat_bytes,h_.writer_max_request_bytes);
          if(!packets)throw std::logic_error("writer packet predicate changed during command");
          phase->writer_packets=*packets;
        }
        for(std::uint64_t r=0;r<transfers_[0].rows;++r) {
          auto row=transfers_[0];row.address+=r*row.row_stride;row.rows=1;
          phase->row_transfers.push_back(row);
        }
        // Local priced service remains a floor. Row memory service is applied
        // later at its actual streamed arrival, not in this scalar latency.
        effects.minimum_latency=0;
      } else effects=transfer_hook_({transfers_.data(), transfers_.size()});
      reads_.insert(reads_.end(), effects.reads.begin(), effects.reads.end());
      writes_.insert(writes_.end(), effects.writes.begin(), effects.writes.end());
      if (arrival && submit_hook_ && !streamed) phase = TransferPhase{arrival, effects.demands};
      for (const auto &effect : effects.demands) {
        if (effect.units != 1) throw std::invalid_argument("target transfer hook requires unit demands");
        if (!phase) demand(effect.resource, effect.occupancy);
      }
      if (!effects.minimum_latency) missing("external_transfer_latency");
      else if (arrival > std::numeric_limits<Cycle>::max() - *effects.minimum_latency)
        missing("external_transfer_arrival_overflow");
      else if (latency && !streamed && !row_load) latency = std::max(*latency, *effects.minimum_latency + arrival);
    } else if (!transfers_.empty()) {
      bool write = transfers_.front().write;
      std::uint64_t payload = 0;
      for (const auto &transfer : transfers_) add(payload, transfer.rows * transfer.row_bytes);
      const auto duration = dma_time(write, payload);
      demand(write ? resources_.dma_write : resources_.dma_read, duration);
      if (latency && duration) latency = std::max(*latency, *duration);
    }
    if (!semantic_known_ || !timing_known_ || counters_.accounting_overflow) latency.reset();
    for (auto *list : {&reads_, &writes_}) {
      std::sort(list->begin(), list->end());
      list->erase(std::unique(list->begin(), list->end()), list->end());
    }
    add(counters_.local_read_bytes, event_reads_);
    add(counters_.local_write_bytes, event_writes_);
    Event event{earliest_, {reads_.data(), reads_.size()}, {writes_.data(), writes_.size()},
                {demands_.data(), demands_.size()}, latency};
    event.hold_reads_until_ready = true;
    return submit_hook_ ? submit_hook_(kind, event, occupancy, funct_, rs1_, rs2_, phase) : engine_.submit(event);
  }
  Result configure(std::uint64_t rs1, std::uint64_t rs2) {
    const auto kind = rs1 & 3;
    if (kind == 0) {
      reads_.push_back(state(3));
      const bool ws = (rs1 >> 2) & 1, at = (rs1 >> 8) & 1, bt = (rs1 >> 9) & 1;
      if ((ws && at && bt) || (!ws && !at && bt) || std::uint32_t(rs2) >= 32)
        fail("execute_configuration_legality", true);
      if (!(rs1 & 128)) {
        execute_.ws = ws; execute_.a_transpose = at; execute_.b_transpose = bt;
        const auto act = std::uint8_t((rs1 >> 3) & 3);
        execute_.activation = act ? std::optional<std::uint8_t>(act) : accumulator_not_softmax_ ?
          std::optional<std::uint8_t>(0) :
          accumulator_activation_ ? std::optional<std::uint8_t>(*accumulator_activation_ == 4 ? 4 : 0) :
          std::nullopt;
        execute_.valid = true;
      }
      execute_.a_stride = (rs1 >> 16) & 65535;
      execute_.c_stride = (rs2 >> 48) & 65535;
      writes_.push_back(state(4));
    } else if (kind == 1) {
      const auto id = (rs1 >> 3) & 3;
      if (id >= loads_.size()) fail("load_state_id", true);
      else {
        auto &load = loads_[id];
        load = {rs2, std::uint32_t((rs1 >> 16) & 65535), std::uint32_t((rs1 >> 8) & 255),
                bool((rs1 >> 2) & 1), true, std::uint32_t(rs1 >> 32)};
        if (!load.pixels) load.pixels = 1;
        if (!h_.first_layer_optimizations && load.pixels > 1) fail("pixel_extension_unavailable", true);
        writes_.push_back(state(id));
      }
    } else if (kind == 2) {
      store_ = {std::uint32_t(rs2), std::uint32_t((rs1 >> 4) & 3), std::uint32_t((rs1 >> 6) & 3),
                std::uint32_t((rs1 >> 24) & 255), std::uint32_t((rs1 >> 32) & 255),
                std::uint32_t((rs1 >> 40) & 255), std::uint32_t((rs1 >> 48) & 255),
                std::uint32_t((rs1 >> 56) & 255), std::uint32_t((rs1 >> 8) & 3),
                std::uint32_t((rs1 >> 10) & 3), true};
      const auto act = std::uint8_t((rs1 >> 2) & 3);
      if (act) { accumulator_activation_ = act; accumulator_not_softmax_ = true; }
      else if (accumulator_not_softmax_) accumulator_activation_ = 0;
      writes_.push_back(state(3));
    } else {
      if (h_.normalizations == std::optional<bool>{false}) {
        // Selected no-normalization RTL routes this command as a store, not
        // a harmless configuration. Refuse a valid timing interpretation.
        fail("normalization_feature_disabled", true);
        return submit("config", resources_.config, 0, 0);
      }
      const auto id = std::uint8_t((rs1 >> 8) & 255);
      if (id >= 4) fail("normalization_state_id", true);
      else norm_stat_ = id;
      if (!(rs1 & (1ull << 17))) {
        qb_qc_known_ = true;
        if (rs1 & (1ull << 18)) qln2_inv_known_ = true;
        else qln2_known_ = true;
        const auto msb = std::uint8_t((rs1 >> 16) & 1);
        if (accumulator_activation_) {
          accumulator_activation_ = std::uint8_t(*accumulator_activation_ | (msb << 2));
          if (*accumulator_activation_ > 4) fail("normalization_activation", true);
        }
        if (msb) accumulator_not_softmax_ = false;
      }
      writes_.push_back(state(3));
      for (std::uint32_t i = 0; i < 4; ++i) writes_.push_back(state(7 + i));
    }
    return submit("config", resources_.config, 0, 0);
  }
  void transfer(std::uint64_t address, std::uint64_t nrows, std::uint64_t bytes,
                std::uint64_t stride, bool write) {
    if (!nrows || !bytes) return;
    if (address > std::numeric_limits<std::uint64_t>::max() - bytes + 1 ||
        (nrows - 1 && stride > (std::numeric_limits<std::uint64_t>::max() - address - bytes + 1) / (nrows - 1))) {
      fail("dram_address_overflow", true); return;
    }
    transfers_.push_back({address, nrows, bytes, stride, write});
    add(write ? counters_.requested_write_bytes : counters_.requested_read_bytes, nrows * bytes);
  }
  Result load(std::uint64_t dram, std::uint64_t encoded, std::size_t id) {
    reads_.push_back(state(id));
    if (!loads_[id].valid) {
      fail("unconfigured_load"); invalidate_all();
      return submit("load", resources_.load, 0, 0);
    }
    const auto &load = loads_[id];
    const auto p = packet(encoded);
    const bool accumulator = (p.address >> 31) & 1, accumulate = (p.address >> 30) & 1;
    const auto base = std::uint64_t(p.address & 0x1fffffffu);
    const auto width = accumulator && !load.shrunk ? h_.accumulator_bytes : h_.element_bytes;
    const auto capacity = accumulator ? h_.accumulator_rows : h_.scratchpad_rows;
    const auto blocks = (std::uint64_t(p.cols) + h_.dim - 1) / h_.dim;
    if (p.rows && blocks && base + p.rows - 1 + (blocks - 1) * load.block_stride >= capacity) {
      fail("load_address_bounds", true);
      return submit("load", resources_.load, 0, 0);
    }
    for (std::uint64_t block = 0; block < blocks && !row_aborted_; ++block) {
      const auto columns = std::min<std::uint64_t>(h_.dim, p.cols - block * h_.dim);
      for (std::uint32_t i = 0; i < p.rows && !row_aborted_; ++i) {
        const auto address = base + i + block * load.block_stride;
        const auto pixels = std::min<std::uint64_t>(load.pixels, address + 1);
        if (columns + (pixels - 1) * p.cols > h_.dim) {
          fail("pixel_column_bounds", true); row_aborted_ = true; break;
        }
        for (std::uint64_t pixel = 0; pixel < pixels && !row_aborted_; ++pixel) {
          const auto local_bytes = columns * (accumulator ? h_.accumulator_bytes : h_.element_bytes);
          if (accumulator && accumulate) row(true, address - pixel, false, local_bytes);
          row(accumulator, address - pixel, true, local_bytes);
        }
      }
    }
    const bool full_accumulator_packet=h_.source_full_accumulator_load && submit_hook_ && transfer_hook_ &&
        dram && accumulator && !accumulate && !load.shrunk && load.pixels==1 &&
        h_.dim==16 && h_.accumulator_bytes==4 && p.cols && p.cols<=16 && p.rows && p.rows<=16 &&
        (load.stride==0 || load.stride>=std::uint64_t(p.cols)*4);
    // LoadController.actual_rows_read is ONE for a nonzero source and stride0.
    // Its scaler input register repeats that fetched row; there are not rows
    // separate DMA requests/cache lookups for this original bias broadcast.
    if (dram) transfer(dram, full_accumulator_packet&&load.stride==0 ? 1 : p.rows,
        std::uint64_t(p.cols) * width, load.stride, false);
    else add(counters_.zero_fill_elements, std::uint64_t(p.rows) * p.cols);
    const bool row_load = !h_.source_identity_ingress && h_.scratchpad_row_loads && submit_hook_ && transfer_hook_ &&
        dram && !accumulator && !load.shrunk && load.scale==0x3f800000u && load.pixels==1 &&
        h_.dim==16 && h_.element_bytes==1 && p.cols==16 && p.rows && p.rows<=16 &&
        dram%16==0 && load.stride && load.stride%16==0;
    const auto packet_max_columns=h_.wide_scratchpad_row_publication ?
        (std::uint64_t{1}<<h_.selected_mvin_cols_bits)-1 : std::uint64_t{16};
    if(h_.wide_scratchpad_row_publication && dram && !accumulator && !load.shrunk &&
        load.scale==0x3f800000u && load.pixels==1 &&
        (p.cols>packet_max_columns || p.rows>h_.dim))return unknown_transfer("load");
    const bool packet_load=full_accumulator_packet || (!row_load && h_.scratchpad_packet_loads && submit_hook_ && transfer_hook_ &&
        dram && !accumulator && !load.shrunk && load.scale==0x3f800000u && load.pixels==1 &&
        h_.dim==16 && h_.element_bytes==1 && p.cols && p.cols<=packet_max_columns && p.rows && p.rows<=16 &&
        load.stride>=p.cols);
    if(!packet_load)add(row_load ? counters_.load_row_stream_publication : counters_.load_aggregate_publication,1);
    return submit("load", resources_.load, event_reads_ + event_writes_, 0, 0,row_load,packet_load);
  }
  Result store(std::uint64_t dram, std::uint64_t encoded) {
    reads_.push_back(state(3));
    if (!store_.valid) {
      fail("unconfigured_store"); invalidate_all();
      return submit("store", resources_.store, 0, 0);
    }
    const auto p = packet(encoded);
    const bool acc = (p.address >> 31) & 1, full = (p.address >> 29) & 1;
    const auto base = std::uint64_t(p.address & 0x3ffffffu);
    const auto norm = (p.address >> 26) & 7;
    if (full && acc && !h_.full_width_accumulator_readout) fail("full_width_readout_unavailable", true);
    const bool normalizing = !store_.pool_stride && p.rows && p.cols;
    const bool readout = normalizing && acc && !norm;
    const bool pooled = store_.pool_stride && store_.porows && store_.pocols && p.cols;
    if (acc && (readout || pooled) && !accumulator_activation_) fail("unconfigured_accumulator_activation");
    if (normalizing) {
      if (norm_stat_) {
        reads_.push_back(state(7 + *norm_stat_)); writes_.push_back(state(7 + *norm_stat_));
      } else if (norm || (readout && accumulator_activation_ &&
                        (*accumulator_activation_ == 2 || *accumulator_activation_ == 4)))
        fail("unconfigured_normalization");
      if ((norm == 6 || norm == 7 || (readout && accumulator_activation_ && *accumulator_activation_ == 4)) &&
          !(qb_qc_known_ && qln2_known_ && qln2_inv_known_)) fail("unconfigured_exponential_constants");
      if (readout && accumulator_activation_ && *accumulator_activation_ == 3 && !qb_qc_known_)
        fail("unconfigured_gelu_constants");
      if (norm_stat_) {
        auto &bank = normalization_[*norm_stat_];
        if ((norm == 3 || norm == 4 || (readout && accumulator_activation_ && *accumulator_activation_ == 2)) &&
            !bank.mean) fail("uninitialized_normalization_mean");
        if (readout && accumulator_activation_ && *accumulator_activation_ == 2 && !bank.invstd)
          fail("uninitialized_normalization_invstd");
        if (readout && accumulator_activation_ && *accumulator_activation_ == 4 && !(bank.max && bank.invsum))
          fail("uninitialized_softmax_statistics");
        if (norm == 2) bank.mean = true;
        if (norm == 4 && bank.mean) bank.invstd = true;
        if ((norm == 6 || norm == 7) && qb_qc_known_ && qln2_known_ && qln2_inv_known_) bank.max = true;
        if (norm == 7 && qb_qc_known_ && qln2_known_ && qln2_inv_known_) bank.invsum = true;
      }
    }
    if (store_.pool_stride) {
      if (p.cols > h_.dim) fail("pool_channel_extent", true);
      for (std::uint32_t y = 0; y < store_.porows && !row_aborted_; ++y) {
        for (std::uint32_t x = 0; x < store_.pocols && !row_aborted_; ++x)
          for (std::uint32_t wy = 0; wy < store_.pool_size && !row_aborted_; ++wy)
            for (std::uint32_t wx = 0; wx < store_.pool_size && !row_aborted_; ++wx) {
              const auto iy = std::int64_t(y * store_.pool_stride + wy) - store_.upad;
              const auto ix = std::int64_t(x * store_.pool_stride + wx) - store_.lpad;
              if (iy >= 0 && ix >= 0 && iy < store_.orows && ix < store_.ocols)
                row(acc, base + std::uint64_t(iy) * store_.ocols + ix, false,
                    std::uint64_t(p.cols) * (acc ? h_.accumulator_bytes : h_.element_bytes));
            }
        const auto offset = y * std::uint64_t(store_.out_dim) * store_.stride;
        if (offset > std::numeric_limits<std::uint64_t>::max() - dram) {
          fail("dram_address_overflow", true); break;
        }
        transfer(dram + offset, store_.pocols,
                 std::uint64_t(p.cols) * h_.element_bytes, store_.stride, true);
      }
      add(counters_.pooled_outputs, std::uint64_t(store_.porows) * store_.pocols * p.cols);
    } else {
      const auto blocks = (std::uint64_t(p.cols) + h_.dim - 1) / h_.dim;
      for (std::uint64_t block = 0; block < blocks && !row_aborted_; ++block) {
        const auto columns = std::min<std::uint64_t>(h_.dim, p.cols - block * h_.dim);
        for (std::uint32_t i = 0; i < p.rows && !row_aborted_; ++i) {
          const auto address = base + block * h_.dim + i;
          if (norm) row(true, address, false, columns * h_.accumulator_bytes);
          else row(acc, address, false, columns * (acc ? h_.accumulator_bytes : h_.element_bytes));
        }
      }
      if (!norm) transfer(dram, p.rows, std::uint64_t(p.cols) * (acc && full ? h_.accumulator_bytes : h_.element_bytes),
                          store_.stride, true);
    }
    // Non-RESET normalization consumes accumulator data but writes no DRAM.
    // Its arithmetic is outside this primitive timing domain until priced.
    std::string kind = norm && !store_.pool_stride ? "normalize" + std::to_string(norm) :
                       store_.pool_stride ? "pool_store" : "store";
    if (acc && accumulator_activation_ && *accumulator_activation_ &&
        ((!norm && !store_.pool_stride) || (store_.pool_stride && *accumulator_activation_ == 1)))
      kind += "_act" + std::to_string(*accumulator_activation_);
    // Full-width data still traverses AccumulatorScale's selected elastic
    // pipeline. StreamWriter req.valid requires writeData.valid. Preserve
    // other readout forms until their separate normalization/pooling paths
    // have a source-bound arrival contract.
    Cycle arrival=0;
    if(h_.accumulator_readout_packet_geometry && h_.accumulator_streamed_readout &&
       acc && !norm && !store_.pool_stride) {
      const auto width=std::uint64_t(p.cols)*(full?h_.accumulator_bytes:h_.element_bytes);
      if(p.cols<=h_.dim && p.rows<=h_.dim && ((h_.source_masked_i8_readout && !full &&
          bool(one_beat_writer_rows(dram,p.rows,width,store_.stride))) || (h_.accumulator_readout_full_packets ?
          bool(full_writer_rows(dram,p.rows,width,store_.stride,h_.writer_beat_bytes,h_.writer_max_request_bytes)) :
          single_full_row_transactions(dram,p.rows,width,store_.stride,h_.writer_beat_bytes,h_.writer_max_request_bytes)))) {
        if(h_.accumulator_readout_arrival)arrival=*h_.accumulator_readout_arrival;
        else missing("accumulator_readout_arrival_unspecified");
      } else missing("unsupported_masked_or_multitransaction_accumulator_readout");
    } else arrival=acc && full && !norm && !store_.pool_stride &&
        p.cols==h_.dim && p.rows && p.rows<=h_.dim &&
        store_.stride==std::uint64_t(h_.dim)*h_.accumulator_bytes ?
        h_.accumulator_readout_arrival.value_or(0):0;
    return submit(kind, resources_.store, event_reads_ + event_writes_, 0, arrival);
  }
  Result compute(std::uint64_t rs1, std::uint64_t rs2, bool preloaded) {
    reads_.push_back(state(4)); reads_.push_back(state(5));
    if (!execute_.valid || !preload_.valid) {
      fail("unconfigured_execute_or_preload"); invalidate_all();
      return submit("compute", resources_.execute, 0, 0);
    }
    auto a = clipped(packet(rs1)), b = clipped(packet(rs2));
    if (a.address == 0xffffffffu) fail("undefined_functional_discard_a");
    if (a.address != 0xffffffffu && a.address >= h_.scratchpad_rows) fail("compute_a_address", true);
    if (b.address != 0xffffffffu && b.address >= h_.scratchpad_rows) fail("compute_b_address", true);
    if (execute_.a_transpose) std::swap(a.rows, a.cols);
    rows(a, false, false, execute_.a_stride);
    if (execute_.ws || !execute_.b_transpose) rows(b, false, false);
    else { std::swap(b.rows, b.cols); rows(b, false, false); }
    if (preloaded) {
      auto source = clipped(preload_.source);
      if (source.address != 0xffffffffu && source.address >= h_.scratchpad_rows) fail("preload_source_address", true);
      if (execute_.ws && execute_.b_transpose) std::swap(source.rows, source.cols);
      rows(source, false, false);
      pe_weights_ = clipped(preload_.source);
      if (pe_weights_.address == 0xffffffffu) pe_weights_.rows = pe_weights_.cols = 0;
      pe_shape_known_ = true;
      writes_.push_back(state(6));
    } else {
      reads_.push_back(state(6));
      if (execute_.ws && !pe_shape_known_) fail("unknown_persistent_weight_shape");
    }
    if (!execute_.ws) {
      writes_.push_back(state(6));
      if (pe_shape_known_) {
        // OS updates the persistent PE matrix. A later WS accumulated command
        // can consume it; retain the bounding shape across dataflow changes.
        pe_weights_.rows = std::max(pe_weights_.rows, clipped(packet(rs1)).rows);
        pe_weights_.cols = std::max(pe_weights_.cols, clipped(packet(rs2)).cols);
      }
    }
    const auto output = preload_.output;
    const bool acc = (output.address >> 31) & 1, accumulate = (output.address >> 30) & 1;
    if (acc && accumulate) rows(output, false, true, execute_.c_stride);
    rows(output, true, acc, execute_.c_stride);
    const auto a_shape = clipped(packet(rs1)), b_shape = clipped(packet(rs2));
    const auto k = std::min<std::uint32_t>(a_shape.cols, execute_.ws ? pe_weights_.rows : b_shape.rows);
    const auto n = execute_.ws ? pe_weights_.cols : b_shape.cols;
    add(counters_.useful_shape_macs, std::uint64_t(a_shape.rows) * k * n);
    const auto nominal = std::uint64_t(h_.dim) * h_.dim * h_.dim;
    add(counters_.nominal_padded_macs, nominal);
    std::string kind = execute_.ws ? "compute_ws" : "compute_os";
    if (!acc && output.address != 0xffffffffu) {
      // A zero activation field selects NONE or SOFTMAX from accumulator
      // state; public apply_activation_sys treats both as identity.
      if (execute_.activation && *execute_.activation == 1) kind += "_relu";
    }
    return submit(kind, resources_.execute,
                  event_reads_ + event_writes_, nominal);
  }
  Result fence() {
    add(counters_.fences, 1);
    if (!submit_hook_) {
      const auto barrier = engine_.barrier();
      if (barrier) earliest_ = std::max(earliest_, *barrier);
      else missing("prior_work_unknown_at_fence");
    }
    return submit("fence", resources_.config, 0, 0);
  }
};
} // namespace gemmini_annotated_spike
#endif
