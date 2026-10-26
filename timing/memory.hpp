#ifndef SPIKE_TIMING_MEMORY_HPP
#define SPIKE_TIMING_MEMORY_HPP
#include "model.hpp"
#include "provider.hpp"
#include "write_transaction.hpp"
#include "read_allocation.hpp"
#include "merlin_timing/memory_milestones.hpp"
#include "merlin_timing/cache_response_timeline.hpp"
#include <map>
#include <unordered_map>
#include <set>
#include <tuple>

namespace spike_timing {
class MemorySystem {
public:
  MemorySystem(const Model &, merlin_timing::Engine &,
               std::function<merlin_timing::ValueId(std::size_t)> allocate,
               std::function<void(const std::string &, std::uint64_t)> feature,
               std::function<void(const std::string &)> unresolved);
  SharedEffects access(const std::vector<MemoryEffect> &, const std::string &path);
  bool write_transaction(const WriteTransactionV1 &, WriteTransactionEffectsV1 &);
  bool write_transaction(const WriteTransactionV1 &, WriteTransactionEffectsV2 &);
  bool write_packet(const FullWritePacketV3 &, WriteTransactionEffectsV2 &);
  bool write_transaction(const WriteTransactionV1 &, WriteTransactionEffectsV4 &);
  bool write_packet(const FullWritePacketV3 &, WriteTransactionEffectsV4 &);
  bool write_transaction(const WriteTransactionV1 &, WriteTransactionEffectsV5 &);
  bool write_packet(const FullWritePacketV3 &, WriteTransactionEffectsV5 &);
  bool write_transaction(const WriteTransactionV1 &,WriteTransactionEffectsV6 &);
  bool write_packet(const FullWritePacketV3 &,WriteTransactionEffectsV6 &);
  bool write_packet(const MaskedWritePacketV8 &,WriteTransactionEffectsV6 &);
  bool write_packet(const MaskedWritePacketV8 &,MaskedWriteEffectsV9 &);
  bool take_read_allocations(ReadAllocationEffectsV7&);
  std::optional<std::vector<std::uint64_t>>cpu_read_admission_lines(const std::vector<MemoryEffect>&,const std::string&)const;
  bool source_read_allocations_selected()const{return read_allocations_selected_;}
  void cpu_data_completed(std::optional<merlin_timing::Cycle>,bool atomic);
  bool private_client_busy()const{return !victim_clients_.empty();}
  bool victim_client_released(const VictimProbeV6&,merlin_timing::Cycle);
  void instruction_fence();
  void bootstrap_primary_elf(const std::string &);
  const std::string &bootstrap_report() const { return bootstrap_report_; }
  bool last_observation(const merlin_timing::MemoryRequestIdentityV1 &,
                        merlin_timing::MemoryMilestonesV2 &) const;
  bool last_observation(const merlin_timing::MemoryRequestIdentityV1 &request,
                        merlin_timing::MemoryMilestonesV1 &out) const {
    merlin_timing::MemoryMilestonesV2 extended;
    if(!last_observation(request,extended))return false;
    out=static_cast<const merlin_timing::MemoryMilestonesV1 &>(extended);return true;
  }
  bool admit_response_epoch(const merlin_timing::MemoryResponseEpochV1 &);
  void source_full_fence(merlin_timing::Cycle,bool close_typed_write_epoch=true);
  void source_report();
  std::size_t pending_tokens() const { return tokens_.size(); }
private:
  const Model &model_;
  merlin_timing::Engine &engine_;
  std::function<merlin_timing::ValueId(std::size_t)> allocate_;
  std::function<void(const std::string &, std::uint64_t)> feature_;
  std::function<void(const std::string &)> unresolved_;
  std::map<std::string, std::unique_ptr<merlin_timing::SetAssociativeCache>> caches_;
  std::map<std::string, std::uint64_t> lines_;
  struct ProbeService {
    merlin_timing::ResourceId resource;
    std::uint64_t beat_bytes;
    merlin_timing::Cycle lookup, dirty_enter, data_pipeline, metadata;
    // Optional completion pipeline; never extends probe-controller occupancy.
    std::optional<merlin_timing::Cycle> write_response_pipeline;
  };
  std::map<std::string, ProbeService> probe_service_;
  std::map<std::string, merlin_timing::ValueId> cache_tokens_;
  std::map<std::string, std::vector<std::string>> paths_;
  std::set<std::string> noncoherent_private_;
  std::unordered_map<std::uint64_t, merlin_timing::ValueId> tokens_;
  std::vector<merlin_timing::ValueId> free_;
  std::set<merlin_timing::ValueId> building_;
  std::uint64_t granule_ = 0;
  bool allocated_ = false;
  bool separate_coherence_transactions_ = false;
  std::string bootstrap_report_="null";
  struct FetchRefill {
    merlin_timing::CacheResponseSpec response;
    merlin_timing::Cycle request_accept_cycles;
  };
  std::optional<FetchRefill> fetch_refill_;
  struct DeviceReadPipeline {
    std::string cache;
    merlin_timing::Cycle scalar_lookup, stages;
  };
  std::optional<DeviceReadPipeline> device_read_pipeline_;
  std::optional<DeviceReadPipeline> device_write_request_pipeline_;
  bool typed_write_request_=false;
  bool typed_single_private_probe_=false,typed_probe_epoch_=false;
  bool typed_full_packet_epoch_=false;
  std::set<merlin_timing::ValueId>typed_full_packet_slots_;
  bool typed_cold_write_selected_=false;
  bool typed_dirty_victim_selected_=false,typed_private_victim_selected_=false,typed_private_dirty_=false,typed_private_original_dirty_=false;
  std::string victim_private_cache_,victim_source_identity_;
  bool read_allocations_selected_=false;
  std::string read_allocation_cache_;
  ReadAllocationEffectsV7 last_read_allocations_;
  std::optional<merlin_timing::Cycle>cpu_data_ready_=merlin_timing::Cycle{0};
  bool cpu_data_miss_=false,cpu_atomic_seen_=false;
  std::map<std::pair<std::uint64_t,std::uint64_t>,merlin_timing::Cycle>victim_clients_;
  WriteMissV4 *typed_cold_miss_=nullptr;
  std::vector<merlin_timing::ValueId>*typed_release_writes_=nullptr;
  bool write_transaction_owned(const WriteTransactionV1 &,WriteTransactionEffectsV1 &,std::optional<WriteProbeV2>*);
  bool write_source_owned(const WriteTransactionV1 &,const WriteUsefulBytes &,WriteTransactionEffectsV1 &,std::optional<WriteProbeV2>*,bool full_packet=false,std::optional<WriteMissV4>*miss=nullptr,std::vector<merlin_timing::ValueId>*release_writes=nullptr,std::optional<VictimProbeV6>*victim=nullptr);

  std::optional<merlin_timing::ValueId> token(std::uint64_t region);
  struct Lookup {
    std::uint64_t cache=0,line=0,slot=0,generation=0;
    bool hit=false,dirty_eviction=false;
    std::uint64_t set=0,line_bytes=0;
    std::optional<merlin_timing::Cycle> prior_fill_ready;
  };
  struct LastObservation {
    std::uint64_t address=0,bytes=0,sequence=0;
    bool valid=false,no_probe=false;
    std::optional<Lookup> lookup;
  } last_observation_;
  std::uint64_t observation_sequence_=0;
  std::map<std::string,std::vector<std::uint64_t>> cache_generations_;
  struct SharedObservation {std::uint64_t sequence;bool device,resident;};
  std::vector<SharedObservation> source_observations_;
  std::vector<merlin_timing::MemoryResponseEpochV1> source_epochs_;
  std::uint64_t source_fence_sequence_=0;
  std::optional<merlin_timing::Cycle> source_fence_clock_;
  bool source_history_overflow_=false;
  struct Walk {
    SharedEffects effects;
    std::vector<ReadAllocationV7>read_allocations;
    std::vector<ReadParentWritebackV11>parent_writebacks;
    std::set<merlin_timing::ValueId> reads, writes;
    using TransactionLine = std::tuple<std::string, std::uint64_t, bool>;
    std::map<TransactionLine, bool> visited;
    std::map<TransactionLine, std::map<std::uint64_t, std::uint64_t>> byte_coverage;
    bool coherence_transaction = false;
    bool cpu_fetch = false, suppress_cache_price = false, device=false, shared_lookup=false,coherence_probe=false,source_partition=false;
    std::vector<Lookup> device_lookups;
    std::map<std::string, std::uint64_t> boundary_bytes;
    std::map<std::string, merlin_timing::Cycle> probe_cycles, probe_responses;
    merlin_timing::Cycle latency = 0, bus = 0;
    bool complete = true;
  };
  void finish_walk(Walk&);
  void cache_access(std::uint64_t, std::uint64_t, bool,
                    const std::vector<std::string> &, std::size_t, Walk &);
  void coherent_access(std::uint64_t, bool, Walk &);
  void charge(Walk &, const std::string &, double units = 1, bool bus = false);
};
} // namespace spike_timing
#endif
