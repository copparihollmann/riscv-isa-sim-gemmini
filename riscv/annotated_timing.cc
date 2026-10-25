#include "../timing/observer.hpp"
#include "cpu_decode.hpp"
#include "immutable_elf_suffix.hpp"
#include "memory.hpp"
#include <merlin_timing/posted_engine_stage.hpp>
#include "model.hpp"
#include "counter_taint.hpp"
#include "event_trace.hpp"
#include "scoped_resources.hpp"
#include "fp_operand_timing.hpp"
#include "../timing/integer_divider_timing.hpp"
#include "processor.h"
#include <dlfcn.h>
#include <array>
#include <cmath>
#include <fstream>
#include <filesystem>
#include <cstdio>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>

#if __has_include("timing_build_identity.h")
#include "timing_build_identity.h"
#endif
#ifndef SPIKE_TIMING_SOURCE_SHA256
#define SPIKE_TIMING_SOURCE_SHA256 "unbound"
#endif

namespace spike_timing {
namespace {
Session *active = nullptr;
using merlin_timing::Cycle;
using merlin_timing::ValueId;
using merlin_timing::Demand;
using merlin_timing::Event;
template<class T> merlin_timing::View<T> view(const std::vector<T> &values) {
  return {values.data(), values.size()};
}
std::optional<Cycle> sum(std::optional<Cycle> a, std::optional<Cycle> b) {
  if (!a || !b || *b > std::numeric_limits<Cycle>::max() - *a) return {};
  return *a + *b;
}
std::string cycle_json(std::optional<Cycle> value) {
  return value ? std::to_string(*value) : "null";
}
struct CounterWindow {
  std::uint64_t begin_pc, end_pc, instructions;
  std::optional<Cycle> cycles;
  std::map<std::string, std::uint64_t> features;
  std::set<std::string> unresolved;
  bool timing_complete;
  std::set<std::string> count_unresolved;
};
} // namespace

class Session::Impl {
public:
  struct CpuCost {
    std::optional<Cycle> latency, occupancy;
    std::optional<merlin_timing::ResourceId> resource;
  };
  Model model;
  std::map<std::string, CpuCost> cpu_costs;
  std::optional<merlin_timing::ResourceId> issue_resource;
  std::optional<Cycle> issue_cost, branch_taken, branch_not_taken;
  merlin_timing::Engine engine;
  std::unique_ptr<EventTrace> event_trace;
  std::unique_ptr<ScopedResources> scoped_resources;
  std::string report_path, elf_digest, input_digest;
  std::map<std::string, std::uint64_t> features;
  std::set<std::string> unresolved;
  std::set<std::string> count_unresolved;
  CounterMemoryTaint counter_memory;
  std::unique_ptr<MemorySystem> memory;
  merlin_timing::MemoryMilestoneQueryV2 memory_milestone_query;
  merlin_timing::MemoryMilestoneQueryV1 memory_milestone_query_v1;
  merlin_timing::MemoryResponseEpochServiceV1 memory_response_epoch_service;
  WriteTransactionServiceV1 write_transaction_service;
  WriteTransactionServiceV2 write_transaction_service_v2;
  FullWritePacketServiceV3 full_write_packet_service_v3;
  ColdWriteServiceV4 cold_write_service_v4;
  ColdWriteServiceV5 cold_write_service_v5;
  ColdWriteServiceV6 cold_write_service_v6;
  ReadAllocationServiceV7 read_allocation_service_v7;
  SubmitReadAllocationsV7 submit_read_allocations_v7=nullptr;
  std::unique_ptr<Services> services;
  std::unique_ptr<TargetProvider> target;
  std::unique_ptr<merlin_timing::PostedTimeline> posted_timeline;
  ObserveProviderFeatures target_features = nullptr;
  merlin_timing::ObserveInstructionContextV1 target_context = nullptr;
  merlin_timing::ObserveImmutableInstructionSuffixV1 target_suffix = nullptr;
  std::unique_ptr<ImmutableElfSuffix> primary_instructions;
  ValueId next_token = 67;
  std::optional<Cycle> pending_flags = Cycle{0};
  std::array<bool,64> time_dependent{};
  bool temporal_rounding = false, temporal_flags = false;
  std::uint64_t instructions = 0, aborted_instructions = 0;
  std::uint64_t pc = 0, bits = 0, first_counter_pc = 0, first_counter_instruction = 0;
  unsigned accelerator_depth = 0;
  bool in_instruction = false, finished = false, counter_pending = false;
  bool access_overflow = false, command_pending = false, trapped = false;
  bool fp_special = false;
  std::array<std::uint64_t, 4> command{};
  std::vector<MemoryEffect> accesses;
  std::function<unsigned(std::uint64_t, std::size_t)> memory_kind;
  std::vector<CounterWindow> windows;
  std::vector<std::string> library_digests;
  bool isa_checked = false;
  bool stop_after_selected_scope = false, accounting_stopped = false;
  std::uint64_t accounted_instructions = 0;
  std::optional<Cycle> first_counter;
  std::map<std::string, std::uint64_t> first_counter_features;

  Impl(const std::string &path, const std::string &output, const std::string &elf,
       const std::string &input, const std::vector<std::string> &libraries,
       std::function<unsigned(std::uint64_t, std::size_t)> classify,
       const std::string &scope_binding, const std::string &event_trace_path)
      : model(path), engine(model.max_values, model.resources), report_path(output),
        elf_digest(sha256_file(elf)), input_digest(input), counter_memory(model.max_memory_entries),
        memory_kind(std::move(classify)) {
    model.bind_scope(scope_binding, elf_digest, input_digest);
    stop_after_selected_scope = model.document.get<bool>("diagnostics.stop_after_selected_scope.enabled", false);
    if (stop_after_selected_scope && !model.scope_pc_pair)
      throw std::invalid_argument("stopping accounting requires an exact selected counter-PC scope");
    if (!event_trace_path.empty()) {
      if (!model.scope_pc_pair) throw std::invalid_argument("event trace requires an exact counter PC scope");
      event_trace = std::make_unique<EventTrace>(event_trace_path);
      event_trace->header(model.digest, elf_digest, model.scope_binding_digest);
    }
    if (model.document.get<bool>("diagnostics.scoped_resources.enabled", false)) {
      if (!model.scope_pc_pair) throw std::invalid_argument("scoped resources require an exact counter PC scope");
      scoped_resources=std::make_unique<ScopedResources>(model.resources);
      if (const auto pairs=model.document.get_child_optional("diagnostics.scoped_resources.pairs"))
        for (const auto& entry:*pairs) scoped_resources->pair(entry.second.get<uint32_t>("left"),entry.second.get<uint32_t>("right"));
    }
    for (const auto *name : cpu_feature_classes) {
      add_feature(name, 0);
      const std::string kind(name);
      if (kind.compare(0, 7, "cpu.fp_") == 0 || kind == "cpu.int_to_fp")
        for (const auto width : {32, 64}) add_feature(kind + ".f" + std::to_string(width), 0);
    }
    for (const auto *name : {"cpu.fp_convert.f32_to_f64", "cpu.fp_convert.f64_to_f32",
                             "cpu.branch_taken", "cpu.branch_not_taken"}) add_feature(name, 0);
    if (model.fp_operand_timing)
      for (const auto *name : {"cpu.fp_divide", "cpu.fp_sqrt"})
        for (const auto width : {32, 64})
          for (const auto *path : {".normal", ".special"})
            add_feature(std::string(name) + ".f" + std::to_string(width) + path, 0);
    issue_resource = model.resource("cpu.issue");
    issue_cost = model.cycles("cpu.issue_cycles");
    branch_taken = model.cycles("cpu.branch.taken_penalty_cycles");
    branch_not_taken = model.cycles("cpu.branch.not_taken_penalty_cycles");
    if (input_digest.empty()) unsafe("external input identity is unspecified");
    else if (!is_digest(input_digest)) throw std::invalid_argument("invalid input SHA-256");
    if (model.domain.at("feature_engine_sha256") != SPIKE_TIMING_SOURCE_SHA256)
      unsafe("feature engine source identity differs from selected profile");
    for (const auto &library : libraries) library_digests.push_back(sha256_file(library));
    std::vector<std::string> expected_libraries;
    if (const auto expected = model.document.get_child_optional("libraries"))
      for (const auto &entry : *expected) {
        if (!is_digest(entry.second.data())) throw std::invalid_argument("invalid library digest");
        expected_libraries.push_back(entry.second.data());
      }
    if (library_digests != expected_libraries)
      unsafe("loaded functional or timing libraries differ from selected profile");
    auto allocate = [this](std::size_t count) { return allocate_tokens(count); };
    auto feature = [this](const std::string &name, std::uint64_t count) { add_feature(name, count); };
    auto missing = [this](const std::string &reason) { unknown(reason); };
    memory = std::make_unique<MemorySystem>(model, engine, allocate, feature, missing);
    memory->bootstrap_primary_elf(elf);
    services = std::make_unique<Services>(Services{
      engine,
      [this](const std::string &name) {
        const auto price_prefix = std::string("parameters.");
        if (name.compare(0, price_prefix.size(), price_prefix) == 0)
          return model.parameter(name.substr(price_prefix.size()));
        return model.number(name);
      },
      [this](const std::string &name) {
        const auto id = model.resource(name);
        if (!id) throw std::invalid_argument("missing explicit target resource: " + name);
        return *id;
      }, allocate,
      [this](const std::vector<MemoryEffect> &effects) {
        for (const auto &effect : effects) if (effect.bytes && memory_kind(effect.address, effect.bytes) != 1) {
          unsafe("device transfer outside stable RAM is unsupported"); return SharedEffects{};
        }
        for (const auto &effect : effects) {
          if (!effect.write && counter_memory.read(effect.address, effect.bytes))
            unsafe("device input depends on architectural counters");
          if (effect.write) counter_memory.write(effect.address, effect.bytes, false);
        }
        return memory->access(effects, "device");
      },
      feature, missing,
    });
    const bool use_posted=model.document.get<bool>("diagnostics.posted_source_timeline.enabled",false);
    if(use_posted){
      if(!model.scope_pc_pair || !stop_after_selected_scope)
        throw std::invalid_argument("posted timeline requires exact selected ROI and accounting stop");
      // Software custody/dispatch guards only, NEVER hardware queue depths.
      // Defaults remain unchanged; larger public ROIs select explicit bounds.
      const auto guard=[this](const char*name,std::uint64_t fallback,std::uint64_t maximum){
        const auto value=model.document.get<std::uint64_t>(std::string("diagnostics.posted_source_timeline.")+name,fallback);
        if(!value||value>maximum)throw std::invalid_argument("invalid posted software guard");return value;
      };
      posted_timeline=std::make_unique<merlin_timing::PostedTimeline>(merlin_timing::PostedTimeline::Spec{
        65536,static_cast<std::size_t>(guard("completion_token_budget",1048576,16777216)),
        guard("dispatch_budget",8000000,64000000)});
    }
    const auto factory = reinterpret_cast<CreateProvider>(dlsym(RTLD_DEFAULT, "spike_timing_create_provider_v1"));
    if (factory) {
      if(posted_timeline){
        using PostedFactory=TargetProvider*(*)(Services*,merlin_timing::PostedTimeline*);
        const auto posted_factory=reinterpret_cast<PostedFactory>(dlsym(RTLD_DEFAULT,"spike_timing_create_posted_provider_v1"));
        if(!posted_factory)throw std::invalid_argument("posted target factory absent");
        target.reset(posted_factory(services.get(),posted_timeline.get()));
      }else target.reset(factory(services.get()));
      if (!target) throw std::runtime_error("timing provider factory returned no provider");
      if(event_trace && posted_timeline){
        using HasOrigins=bool(*)(const TargetProvider*);
        const auto has_origins=reinterpret_cast<HasOrigins>(dlsym(RTLD_DEFAULT,"spike_timing_provider_stage_origins_v1"));
        if(!has_origins||!has_origins(target.get()))
          throw std::invalid_argument("posted event trace requires explicit original actor custody");
      }
      const auto install_memory_v1=reinterpret_cast<merlin_timing::InstallMemoryMilestoneQueryV1>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_memory_milestones_v1"));
      if(install_memory_v1) {
        memory_milestone_query_v1.opaque=memory.get();
        memory_milestone_query_v1.last_observation=[](void *opaque,
            const merlin_timing::MemoryRequestIdentityV1 *request,
            merlin_timing::MemoryMilestonesV1 *out) {
          return opaque && request && out &&
              static_cast<MemorySystem *>(opaque)->last_observation(*request,*out);
        };
        install_memory_v1(target.get(),&memory_milestone_query_v1);
      }
      const auto install_memory=reinterpret_cast<merlin_timing::InstallMemoryMilestoneQueryV2>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_memory_milestones_v2"));
      if(install_memory) {
        memory_milestone_query.opaque=memory.get();
        memory_milestone_query.last_observation=[](void *opaque,
            const merlin_timing::MemoryRequestIdentityV1 *request,
            merlin_timing::MemoryMilestonesV2 *out) {
          return opaque && request && out &&
              static_cast<MemorySystem *>(opaque)->last_observation(*request,*out);
        };
        install_memory(target.get(),&memory_milestone_query);
      }
      const auto install_write=reinterpret_cast<InstallWriteTransactionServiceV1>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_write_transactions_v1"));
      if(install_write){
        write_transaction_service.opaque=this;
        write_transaction_service.admit=[](void*opaque,const WriteTransactionV1*request,WriteTransactionEffectsV1*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);const auto useful=one_beat_write_useful(*request);
          if(!useful||self->memory_kind(request->address,request->transaction_bytes)!=1){
            out->unavailable="typed write transaction outside stable RAM or invalid mask";return false;
          }
          const bool admitted=self->memory->write_transaction(*request,*out);
          if(admitted)self->counter_memory.write(useful->address,useful->bytes,false);
          return admitted;
        };
        install_write(target.get(),&write_transaction_service);
      }
      const auto install_write_v2=reinterpret_cast<InstallWriteTransactionServiceV2>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_write_transactions_v2"));
      if(install_write_v2){
        write_transaction_service_v2.opaque=this;
        write_transaction_service_v2.admit=[](void*opaque,const WriteTransactionV1*request,WriteTransactionEffectsV2*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);const auto useful=one_beat_write_useful(*request);
          if(!useful||self->memory_kind(request->address,request->transaction_bytes)!=1){
            out->base.unavailable="typed write transaction outside stable RAM or invalid mask";return false;
          }
          const bool admitted=self->memory->write_transaction(*request,*out);
          if(admitted)self->counter_memory.write(useful->address,useful->bytes,false);
          return admitted;
        };
        install_write_v2(target.get(),&write_transaction_service_v2);
      }
      const auto install_packet=reinterpret_cast<InstallFullWritePacketServiceV3>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_full_write_packets_v3"));
      if(install_packet){
        full_write_packet_service_v3.opaque=this;
        full_write_packet_service_v3.admit=[](void*opaque,const FullWritePacketV3*request,WriteTransactionEffectsV2*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);
          if(!full_write_packet_valid(*request)||self->memory_kind(request->address,request->transaction_bytes)!=1){
            out->base.unavailable="typed full packet outside stable RAM or invalid original geometry";return false;
          }
          const bool admitted=self->memory->write_packet(*request,*out);
          if(admitted)self->counter_memory.write(request->address,request->transaction_bytes,false);
          return admitted;
        };
        install_packet(target.get(),&full_write_packet_service_v3);
      }
      const auto install_cold=reinterpret_cast<InstallColdWriteServiceV4>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_cold_writes_v4"));
      if(install_cold){
        cold_write_service_v4.opaque=this;
        cold_write_service_v4.beat=[](void*opaque,const WriteTransactionV1*request,WriteTransactionEffectsV4*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);
          const auto useful=one_beat_write_useful(*request);
          if(!useful||self->memory_kind(request->address,request->transaction_bytes)!=1){out->resident.base.unavailable="cold write outside stable RAM or invalid mask";return false;}
          const auto admitted=self->memory->write_transaction(*request,*out);
          if(admitted)self->counter_memory.write(useful->address,useful->bytes,false);
          return admitted;
        };
        cold_write_service_v4.packet=[](void*opaque,const FullWritePacketV3*request,WriteTransactionEffectsV4*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);
          if(!full_write_packet_valid(*request)||self->memory_kind(request->address,request->transaction_bytes)!=1){out->resident.base.unavailable="cold full packet outside stable RAM or invalid geometry";return false;}
          const auto admitted=self->memory->write_packet(*request,*out);
          if(admitted)self->counter_memory.write(request->address,request->transaction_bytes,false);
          return admitted;
        };
        install_cold(target.get(),&cold_write_service_v4);
      }
      const auto install_cold_v5=reinterpret_cast<InstallColdWriteServiceV5>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_cold_writes_v5"));
      if(install_cold_v5){
        cold_write_service_v5.opaque=this;
        cold_write_service_v5.beat=[](void*opaque,const WriteTransactionV1*request,WriteTransactionEffectsV5*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);
          const auto useful=one_beat_write_useful(*request);
          if(!useful||self->memory_kind(request->address,request->transaction_bytes)!=1){out->resident.base.unavailable="cold write outside stable RAM or invalid mask";return false;}
          const auto admitted=self->memory->write_transaction(*request,*out);
          if(admitted)self->counter_memory.write(useful->address,useful->bytes,false);
          return admitted;
        };
        cold_write_service_v5.packet=[](void*opaque,const FullWritePacketV3*request,WriteTransactionEffectsV5*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);
          if(!full_write_packet_valid(*request)||self->memory_kind(request->address,request->transaction_bytes)!=1){out->resident.base.unavailable="cold full packet outside stable RAM or invalid geometry";return false;}
          const auto admitted=self->memory->write_packet(*request,*out);
          if(admitted)self->counter_memory.write(request->address,request->transaction_bytes,false);
          return admitted;
        };
        install_cold_v5(target.get(),&cold_write_service_v5);
      }
      const auto install_cold_v6=reinterpret_cast<InstallColdWriteServiceV6>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_cold_writes_v6"));
      if(install_cold_v6){
        cold_write_service_v6.opaque=this;
        cold_write_service_v6.beat=[](void*opaque,const WriteTransactionV1*request,WriteTransactionEffectsV6*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);
          const auto useful=one_beat_write_useful(*request);
          if(!useful||self->memory_kind(request->address,request->transaction_bytes)!=1){out->resident.base.unavailable="cold write outside stable RAM or invalid mask";return false;}
          const auto admitted=self->memory->write_transaction(*request,*out);
          if(admitted)self->counter_memory.write(useful->address,useful->bytes,false);
          return admitted;
        };
        cold_write_service_v6.packet=[](void*opaque,const FullWritePacketV3*request,WriteTransactionEffectsV6*out){
          if(!opaque||!request||!out)return false;
          auto self=static_cast<Impl*>(opaque);
          if(!full_write_packet_valid(*request)||self->memory_kind(request->address,request->transaction_bytes)!=1){out->resident.base.unavailable="cold full packet outside stable RAM or invalid geometry";return false;}
          const auto admitted=self->memory->write_packet(*request,*out);
          if(admitted)self->counter_memory.write(request->address,request->transaction_bytes,false);
          return admitted;
        };
        cold_write_service_v6.client_released=[](void*opaque,const VictimProbeV6*v,Cycle at){
          return opaque&&v&&static_cast<Impl*>(opaque)->memory->victim_client_released(*v,at);
        };
        install_cold_v6(target.get(),&cold_write_service_v6);
      }
      const auto install_read_allocations=reinterpret_cast<InstallReadAllocationServiceV7>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_read_allocations_v7"));
      submit_read_allocations_v7=reinterpret_cast<SubmitReadAllocationsV7>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_submit_read_allocations_v7"));
      if(memory->source_read_allocations_selected()&&(!posted_timeline||!install_read_allocations||!submit_read_allocations_v7))
        throw std::invalid_argument("source read allocation selection lacks ordinary posted provider intake");
      if(install_read_allocations){
        read_allocation_service_v7.opaque=memory.get();
        read_allocation_service_v7.take=[](void*opaque,ReadAllocationEffectsV7*out){
          return opaque&&out&&static_cast<MemorySystem*>(opaque)->take_read_allocations(*out);
        };
        read_allocation_service_v7.client_released=[](void*opaque,const VictimProbeV6*v,Cycle at){
          return opaque&&v&&static_cast<MemorySystem*>(opaque)->victim_client_released(*v,at);
        };
        install_read_allocations(target.get(),&read_allocation_service_v7);
      }
      const auto install_epochs=reinterpret_cast<merlin_timing::InstallMemoryResponseEpochServiceV1>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_memory_response_epochs_v1"));
      if(install_epochs) {
        memory_response_epoch_service.opaque=memory.get();
        memory_response_epoch_service.admit=[](void *opaque,const merlin_timing::MemoryResponseEpochV1 *epoch) {
          return opaque && epoch && static_cast<MemorySystem *>(opaque)->admit_response_epoch(*epoch);
        };
        install_epochs(target.get(),&memory_response_epoch_service);
      }
      target_features = reinterpret_cast<ObserveProviderFeatures>(
          dlsym(RTLD_DEFAULT, "spike_timing_provider_feature_observation_v1"));
      target_context=reinterpret_cast<merlin_timing::ObserveInstructionContextV1>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_instruction_context_v1"));
      target_suffix=reinterpret_cast<merlin_timing::ObserveImmutableInstructionSuffixV1>(
          dlsym(RTLD_DEFAULT,"spike_timing_provider_immutable_suffix_v1"));
      if(posted_timeline){target_context=nullptr;target_suffix=nullptr;}
      if(target_context && target_suffix)primary_instructions=std::make_unique<ImmutableElfSuffix>(elf);
      if(bool(target_context)!=bool(target_suffix))unsafe("provider instruction context/suffix transport is incomplete");
    }
    accesses.reserve(std::min<std::size_t>(model.max_accesses_per_instruction, 64));
    namespace fs = std::filesystem;
    if (fs::is_symlink(report_path)) throw std::invalid_argument("timing output must be an ordinary file");
    if (fs::exists(report_path)) {
      if (!fs::is_regular_file(report_path) || fs::equivalent(report_path, path) || fs::equivalent(report_path, elf))
        throw std::invalid_argument("timing output conflicts with an input or nonregular file");
      std::ifstream old(report_path); std::array<char,128> prefix{};
      old.read(prefix.data(),prefix.size());
      const std::string previous(prefix.data(), old.gcount());
      if (previous.find("merlin.annotated_spike_report.v1") == std::string::npos &&
          previous.find("merlin.annotated_spike_report.v2") == std::string::npos)
        throw std::invalid_argument("timing output would replace a nonreport file");
    }
    std::ofstream pending(report_path, std::ios::binary | std::ios::trunc);
    if (!pending || !(pending << "{\"schema\":\"merlin.annotated_spike_report.v2\",\"timing_complete\":false,\"status\":\"running\"}\n"))
      throw std::runtime_error("cannot initialize incomplete timing output");
  }
  CpuCost cpu_cost(const std::string &priced, const std::string &kind) {
    const auto cached = cpu_costs.find(priced);
    if (cached != cpu_costs.end()) return cached->second;
    if (cpu_costs.size() >= 128) throw std::runtime_error("CPU cost cache budget exceeded");
    CpuCost cost{model.cycles(priced + ".latency_cycles"), model.cycles(priced + ".occupancy_cycles"), {}};
    if (kind == "cpu.divide" && integer_divider_bound(model)) {
      cost.latency = IntegerDividerBound::latency;
      cost.occupancy = IntegerDividerBound::occupancy;
    }
    const auto resources = model.document.get_child_optional("cpu_execution_resources");
    if (resources) {
      const auto selected = resources->find(kind);
      if (selected != resources->not_found()) cost.resource = model.resource(selected->second.data());
    }
    if (!cost.latency || !cost.occupancy)
      unknown("CPU timing price is missing for " + priced);
    if (!cost.resource) { unknown("CPU execution resource mapping is unspecified"); cost.latency.reset(); }
    cpu_costs.emplace(priced, cost);
    return cost;
  }
  ValueId allocate_tokens(std::size_t count) {
    if (next_token > model.max_values || count > model.max_values - next_token)
      throw std::invalid_argument("timing scoreboard allocation budget exceeded");
    const auto first = next_token; next_token += count; return first;
  }
  void unknown(const std::string &reason) {
    if (unresolved.size() >= 256 && !unresolved.count(reason))
      throw std::runtime_error("timing diagnostic budget exceeded");
    unresolved.insert(reason);
  }
  void unsafe(const std::string &reason) {
    unknown(reason);
    count_unresolved.insert(reason);
  }
  std::set<std::string> feature_reasons() const {
    auto reasons = count_unresolved;
    if (target) {
      if (!target_features) reasons.insert("target provider has no feature observation interface");
      else {
        const auto status = target_features(target.get());
        reasons.insert(status.unresolved.begin(), status.unresolved.end());
        if (!status.complete) reasons.insert("target feature observation is incomplete");
      }
    }
    return reasons;
  }
  void add_feature(const std::string &name, std::uint64_t amount) {
    if (features.size() >= 512 && !features.count(name))
      throw std::runtime_error("timing feature budget exceeded");
    auto &value = features[name];
    if (amount > std::numeric_limits<std::uint64_t>::max() - value) {
      unsafe("feature counter overflow"); return;
    }
    value += amount;
  }
  void begin(processor_t *processor, std::uint64_t address, std::uint64_t instruction) {
    if (in_instruction) throw std::logic_error("nested architectural instruction observation");
    in_instruction = true;
    // Functional execution, instruction counting and traps continue. Only the
    // already closed timing account stops; prefix and selected ROI are intact.
    if (accounting_stopped) return;
    pc = address; bits = instruction;
    if (event_trace || scoped_resources) {
      engine.trace_sink([this](const merlin_timing::Trace &record) {
        if (scoped_resources) scoped_resources->record(record);
        if (event_trace && !event_trace->full() && windows.size() == model.scope_window &&
            (counter_pending || pc == model.scope_begin_pc))
          event_trace->record(record, pc, bits, decode_cpu(bits).kind, instructions);
        if(event_trace && posted_timeline && (std::string(record.action)=="submit_detached") && !record.event.origin)
          unknown("posted diagnostic stage lacks original actor custody");
      });
    }
    accesses.clear(); access_overflow = false; command_pending = false;
    const auto decoded = decode_cpu(bits);
    fp_special = false;
    if (model.fp_operand_timing && decoded.known &&
        (std::string(decoded.kind) == "cpu.fp_divide" || std::string(decoded.kind) == "cpu.fp_sqrt")) {
      const auto &a = processor->get_state()->FPR[(bits >> 15) & 31];
      const auto &b = processor->get_state()->FPR[(bits >> 20) & 31];
      fp_special = fp_divsqrt_special(std::string(decoded.kind) == "cpu.fp_sqrt", decoded.fp_width,
                                    a.v[0], a.v[1], b.v[0], b.v[1]);
    }
    if (decoded.custom) {
      const auto *state = processor->get_state();
      command = {pc, bits, state->XPR[(bits >> 15) & 31], state->XPR[(bits >> 20) & 31]};
      command_pending = true;
      accelerator_depth = 1;
    }
    if (!isa_checked) {
      isa_checked = true;
      const auto isa = processor->get_isa().get_isa_string();
      const auto split = isa.find('_');
      const auto base = isa.substr(4, split == std::string::npos ? split : split - 4);
      bool supported = isa.compare(0, 4, "rv64") == 0 && !base.empty() && base.find_first_not_of("imafdcb") == std::string::npos;
      std::istringstream extensions(split == std::string::npos ? "" : isa.substr(split + 1));
      std::string extension;
      while (std::getline(extensions, extension, '_'))
        if (extension != "zicsr" && extension != "zifencei" && extension != "zicntr" && extension != "zihpm" &&
            extension != "zba" && extension != "zbb" && extension != "zbs" && extension != "zfh") supported = false;
      // Enabled-but-unused half precision does not invalidate a scalar S/D
      // trace. Executed half forms still refuse in decode_cpu; B instructions
      // require exact encodings/operands and a separately priced class.
      if (!supported) unsafe("architectural extensions are outside the supported scalar timing domain");
      if (model.document.get<std::string>("cpu.isa", "") != isa)
        unsafe("architectural ISA differs from selected timing profile");
    }
    if (decoded.floating_register_operands &&
        (processor->get_isa().extension_enabled(EXT_ZFINX) ||
         processor->get_isa().extension_enabled(EXT_ZDINX)))
      unsafe("floating operands in integer registers are outside this timing domain");
    if (processor->get_state()->mstatus->read() & MSTATUS_MPRV)
      unsafe("effective data privilege translation is outside the baremetal timing domain");
    if (processor->get_xlen() != 64 || processor->get_state()->prv != 3)
      unsafe("timing profile currently requires single-hart RV64 baremetal execution");
  }
  void record_memory(std::uint64_t address, std::size_t bytes, access_type type) {
    if (accounting_stopped || !in_instruction || accelerator_depth || type == FETCH) return;
    if (accesses.size() >= model.max_accesses_per_instruction) {
      access_overflow = true; return;
    }
    const auto kind = memory_kind(address, bytes);
    if (!kind || (kind == 2 && type == STORE)) {
      unsafe("unmodeled MMIO or nonstable memory access"); access_overflow = true; return;
    }
    accesses.push_back({address, bytes, type == STORE, kind == 2});
  }
  merlin_timing::InstructionContextV1 instruction_context(merlin_timing::InstructionPhase phase,
                                                         std::uint64_t next_pc=0) {
    merlin_timing::InstructionContextV1 c;c.phase=phase;c.sequence=instructions;
    c.pc=pc;c.bits=bits;c.length=(bits&3)==3?4:2;c.next_pc=next_pc;
    std::copy(elf_digest.begin(),elf_digest.end(),c.primary_elf_sha256.begin());return c;
  }
  void observe_instruction_context(std::uint64_t next_pc) {
    if(!target_context || !target)return;
    const auto current=instruction_context(merlin_timing::InstructionPhase::committed,next_pc);
    target_context(target.get(),&current);
    if(!target_suffix || !primary_instructions || !decode_cpu(bits).custom)return;
    const auto observed=primary_instructions->instruction(pc);
    if(!observed || observed->bits!=bits || observed->length!=current.length ||
       current.pc>UINT64_MAX-current.length || current.next_pc!=current.pc+current.length ||
       !memory_kind(pc,current.length))return;
    merlin_timing::ImmutableInstructionSuffixV1 suffix;suffix.current=current;
    auto address=next_pc;
    for(std::size_t i=0;i<suffix.instructions.size();++i) {
      const auto instruction=primary_instructions->instruction(address);
      if(!instruction || !memory_kind(address,instruction->length))return;
      const auto decoded=decode_cpu(instruction->bits);
      if(!decoded.known || decoded.branch)return;
      suffix.instructions[i]=*instruction;suffix.count=i+1;
      if(instruction->bits==0x0ff0000full){target_suffix(target.get(),&suffix);return;}
      // No weaker fence, SYSTEM/CSR or unknown extended instruction is a
      // straight-line closing proof. Device-specific filtering stays provider-owned.
      if(decoded.fence || (instruction->bits&127)==0x73 || address>UINT64_MAX-instruction->length)return;
      address+=instruction->length;
    }
  }
  void abort_instruction(bool trap = true) noexcept {
    if (trap) { trapped = true; if (in_instruction) ++aborted_instructions; }
    if(target_context && target && !accounting_stopped)try {
      const auto c=instruction_context(merlin_timing::InstructionPhase::aborted);
      target_context(target.get(),&c);
    }catch(...){trapped=true;}
    in_instruction = false; accelerator_depth = 0; command_pending = false; accesses.clear();
  }
  // Actual in-order source admission. While this instruction is pending no
  // later CPU request can arrive. Device callbacks may run, but a future bank
  // or memory effect is never committed before those chronological arrivals.
  merlin_timing::Result submit_cpu_stage(const Event &event,const char *actor,const std::vector<ValueId>&memory_writes={}) {
    if(!posted_timeline)return engine.submit(event);
    auto&q=*posted_timeline;auto done=q.token();if(!done){unknown(q.reason());return {};}
    merlin_timing::OwnedStage owned;owned.earliest=std::max(q.now(),engine.issue_frontier().value_or(0));
    owned.earliest=std::max(owned.earliest,event.earliest);owned.latency=event.latency;
    owned.reads.assign(event.reads.data,event.reads.data+event.reads.size);
    owned.writes.assign(event.writes.data,event.writes.data+event.writes.size);
    owned.retained_reads.assign(event.retained_reads.data,event.retained_reads.data+event.retained_reads.size);
    owned.demands.assign(event.demands.data,event.demands.data+event.demands.size);
    owned.origin=merlin_timing::StageOrigin{pc,bits,instructions,actor};
    if(model.document.get<bool>("diagnostics.posted_source_timeline.pending_memory_visibility",false))owned.deferred_writes=memory_writes;
    owned.hold_reads_until_ready=event.hold_reads_until_ready;owned.kind=merlin_timing::PostedTimeline::Kind::source_arrival;
    std::optional<merlin_timing::Result> accepted;
    merlin_timing::PostedEngineStage::post(q,engine,std::move(owned),{},*done,[&](const auto&r){accepted=r;});
    while(!accepted&&!q.progress().failed)if(!q.step(true)){q.fail("CPU admission dependency deadlock");break;}
    if(!accepted||q.progress().failed){unknown("posted_timeline:"+q.reason());return {};}
    engine.advance_issue(accepted->issue);return *accepted;
  }
  SharedEffects accepted_memory(const std::vector<MemoryEffect>&effects,const std::string&path){
    if(!posted_timeline)return memory->access(effects,path);
    // The caller is the only open in-order CPU source. Dispatch to its issue
    // lower bound BEFORE classifying native cache/TLB state; do not warm it at
    // a future device post. Equal-cycle ordering is explicit CPU-before-newly
    // posted target request, as in the committed instruction stream.
    auto&q=*posted_timeline;const auto at=std::max(q.now(),engine.issue_frontier().value_or(0));
    if(!q.advance(at,true)){unknown("posted_timeline:"+q.reason());return {};}
    if(path=="cpu_data"&&!effects.empty()){
      // A probe owns the real private controller until its registered
      // metadata completion. Wait its posted events before classifying any
      // later CPU cache access; never mutate tags at a future admission.
      while(memory->private_client_busy()&&!q.progress().failed)
        if(!q.step(true)){q.fail("private victim controller completion deadlock");break;}
      if(q.progress().failed){unknown("posted_timeline:"+q.reason());return {};}
      engine.advance_issue(q.now());
    }
    auto result=memory->access(effects,path);
    ReadAllocationEffectsV7 allocation;
    if(memory->take_read_allocations(allocation)){
      if(!allocation.unavailable.empty()||!submit_read_allocations_v7){
        unknown("ordinary CPU read allocation source intake unavailable:"+allocation.unavailable);result.latency.reset();return result;
      }
      std::optional<Cycle>ready;
      const merlin_timing::StageOrigin origin{pc,bits,instructions,path};
      const auto arrived=std::max(q.now(),engine.issue_frontier().value_or(0));
      if(!submit_read_allocations_v7(target.get(),&allocation,&origin,arrived,&ready,[](void*cookie,Cycle at){
          *static_cast<std::optional<Cycle>*>(cookie)=at;
        })){
        unknown("ordinary CPU read allocation source intake refused");result.latency.reset();return result;
      }
      while(!ready&&!q.progress().failed)if(!q.step(true)){q.fail("CPU allocation source dependency deadlock");break;}
      if(!ready||q.progress().failed){unknown("posted_timeline:"+q.reason());result.latency.reset();return result;}
      // The source consumer owns the original cache/DRAM effects and full
      // memory response. The CPU instruction still owns its register result
      // and execution cost; never re-charge the old aggregate memory effects.
      engine.advance_issue(*ready);return SharedEffects{{},{},{},Cycle{0}};
    }
    return result;
  }
  void finish_instruction(std::uint64_t next_pc, bool committed) {
    if (!committed) { abort_instruction(false); return; }
    if (!in_instruction) throw std::logic_error("instruction completion has no matching begin");
    in_instruction = false;
    if (instructions == std::numeric_limits<std::uint64_t>::max())
      throw std::overflow_error("executed instruction count overflow");
    ++instructions;
    if (accounting_stopped) return;
    accounted_instructions = instructions;
    observe_instruction_context(next_pc);
    auto decoded = decode_cpu(bits);
    add_feature(decoded.kind, 1);
    std::string priced_class = decoded.kind;
    if (decoded.fp_width) {
      priced_class += ".f";
      if (decoded.fp_source_width && decoded.fp_source_width != decoded.fp_width)
        priced_class += std::to_string(decoded.fp_source_width) + "_to_f";
      priced_class += std::to_string(decoded.fp_width);
      add_feature(priced_class, 1);
    }
    if (model.fp_operand_timing &&
        (std::string(decoded.kind) == "cpu.fp_divide" || std::string(decoded.kind) == "cpu.fp_sqrt")) {
      add_feature(priced_class + (fp_special ? ".special" : ".normal"), 1);
      if (fp_special) priced_class += ".special";
    }
    const auto csr_address = (bits >> 20) & 4095;
    const bool clock_csr = (bits & 127) == 0x73 && ((bits >> 12) & 7) &&
        ((csr_address >= 0xc00 && csr_address <= 0xc1f) ||
         (csr_address >= 0xb00 && csr_address <= 0xb1f));
    bool temporal = clock_csr;
    const auto csr_mode = (bits >> 12) & 7;
    if (clock_csr && (csr_mode == 1 || csr_mode == 5 || ((bits >> 15) & 31)))
      unsafe("writes to architectural performance counters are outside the timing trace contract");
    for (unsigned i=0; i<decoded.read_count; ++i) temporal = temporal || time_dependent[decoded.reads[i]];
    for (const auto &access : accesses)
      if (!access.write) temporal = temporal || counter_memory.read(access.address, access.bytes);
    if (decoded.reads_rounding_mode) temporal = temporal || temporal_rounding;
    if (decoded.reads_fflags) temporal = temporal || temporal_flags;
    if (decoded.writes_rounding_mode) temporal_rounding = temporal;
    if (decoded.writes_fflags) temporal_flags = temporal;
    if (decoded.accumulates_fflags) temporal_flags = temporal_flags || temporal;
    if (temporal && (bits & 127) == 0x73 && !clock_csr && csr_address > 3)
      unsafe("counter-derived architectural state is outside the timing trace contract");
    if (time_dependent[decoded.memory_address_register] && !accesses.empty())
      unsafe("counter-derived memory address is outside the timing trace contract");
    if (temporal && (decoded.branch || decoded.custom))
      unsafe("counter-derived control or accelerator operand is outside the timing trace contract");
    if (temporal && model.fp_operand_timing &&
        (std::string(decoded.kind) == "cpu.fp_divide" || std::string(decoded.kind) == "cpu.fp_sqrt"))
      unsafe("counter-derived FP timing class is outside the timing trace contract");
    // A harness may spill its opening cycle value for subtraction after the
    // window. Track those actual bytes instead of rejecting every such spill.
    // Loads propagate labels; control, address, device input and state uses
    // still refuse. Unlabelled overwrites remove only the bytes they replace.
    for (const auto &access : accesses)
      if (access.write) counter_memory.write(access.address, access.bytes, temporal);
    for (unsigned i=0; i<decoded.write_count; ++i) time_dependent[decoded.writes[i]] = temporal;
    if (!decoded.known) unsafe("unsupported CPU instruction semantics");
    if (access_overflow) unsafe("instruction memory observation budget exceeded");
    if (accelerator_depth && !(decoded.custom && accelerator_depth == 1)) {
      unsafe("accelerator observation begin/end is incomplete"); accelerator_depth = 0;
    }
    accelerator_depth = 0;
    if (decoded.fence) {
      if (target) target->fence(engine.issue_frontier().value_or(0));
      engine.barrier();
      // Timing's conservative barrier does not manufacture an architectural
      // full-domain fence proof for the optional masked-write source epoch.
      const bool full_domains=!decoded.icache_fence && ((bits>>20)&255)==255 && ((bits>>28)&15)==0;
      if(engine.issue_frontier())memory->source_full_fence(*engine.issue_frontier(),full_domains);
      if (decoded.icache_fence) memory->instruction_fence();
    }
    const auto instruction_bytes = (bits & 3) == 3 ? 4u : 2u;
    const auto instruction_space = memory_kind(pc, instruction_bytes);
    SharedEffects fetch;
    if (!instruction_space) unsafe("instruction fetch outside stable memory is unsupported");
    else fetch = accepted_memory({MemoryEffect{pc, instruction_bytes, false, instruction_space == 2}}, "cpu_fetch");
    const ValueId fetch_token = 64;
    const auto fetch_memory_writes=fetch.writes;
    fetch.writes.push_back(fetch_token);
    Event fetch_event{0, view(fetch.reads), view(fetch.writes), view(fetch.demands), fetch.latency, true};
    submit_cpu_stage(fetch_event,"cpu_fetch",fetch_memory_writes);

    if(posted_timeline && !accesses.empty()){
      auto at=std::max(posted_timeline->now(),engine.issue_frontier().value_or(0));
      if(const auto fetched=engine.ready(64))at=std::max(at,*fetched);else unknown("posted CPU fetch dependency unknown");
      for(unsigned i=0;i<decoded.read_count;++i){const auto ready=engine.ready(decoded.reads[i]);if(!ready){unknown("posted CPU memory operand unknown");break;}at=std::max(at,*ready);}
      if(!posted_timeline->advance(at,true))unknown("posted_timeline:"+posted_timeline->reason());
      engine.advance_issue(at);
    }
    auto data = accepted_memory(accesses, "cpu_data");
    std::vector<ValueId> reads(decoded.reads.begin(), decoded.reads.begin() + decoded.read_count);
    std::vector<ValueId> writes(decoded.writes.begin(), decoded.writes.begin() + decoded.write_count);
    std::vector<ValueId> retained_reads;
    if (decoded.custom) {
      // Keep the old destination live until command admission. The target
      // publishes its asynchronous result separately below.
      reads.insert(reads.end(), writes.begin(), writes.end());
      writes.clear();
    }
    constexpr ValueId rounding_mode = 65, flag_writes = 66;
    if (decoded.reads_rounding_mode) retained_reads.push_back(rounding_mode);
    if (decoded.writes_rounding_mode) writes.push_back(rounding_mode);
    if (decoded.reads_fflags || decoded.accumulates_fflags) retained_reads.push_back(flag_writes);
    if (decoded.writes_fflags) writes.push_back(flag_writes);
    reads.push_back(fetch_token);
    if (decoded.branch) writes.push_back(fetch_token);
    retained_reads.insert(retained_reads.end(), data.reads.begin(), data.reads.end());
    writes.insert(writes.end(), data.writes.begin(), data.writes.end());
    std::vector<Demand> demands = std::move(data.demands);
    const auto cost = cpu_cost(priced_class, decoded.kind);
    auto latency = cost.latency;
    if (issue_resource) demands.push_back({*issue_resource, 1, issue_cost});
    else { unknown("CPU issue resource is unspecified"); latency.reset(); }
    if (cost.resource) demands.push_back({*cost.resource, 1, cost.occupancy});
    latency = sum(latency, data.latency);
    if (decoded.branch) {
      const bool taken = next_pc != pc + instruction_bytes;
      add_feature(taken ? "cpu.branch_taken" : "cpu.branch_not_taken", 1);
      latency = sum(latency, taken ? branch_taken : branch_not_taken);
    }
    if (!decoded.known || access_overflow) latency.reset();
    Cycle earliest = 0;
    if (decoded.reads_fflags) {
      if (pending_flags) earliest = *pending_flags;
      else latency.reset();
    }
    Event event{earliest, view(reads), view(writes), view(demands), latency, false, view(retained_reads)};
    const auto cpu = submit_cpu_stage(event,decoded.kind,data.writes);
    if(!accesses.empty())memory->cpu_data_completed(cpu.ready,std::string(decoded.kind)==CpuKinds::atomic);
    if (decoded.accumulates_fflags)
      pending_flags = pending_flags && cpu.ready ?
          std::optional<Cycle>{std::max(*pending_flags, *cpu.ready)} : std::nullopt;
    if (decoded.writes_fflags) pending_flags = cpu.ready;
    if (decoded.custom) {
      if (!target || !command_pending) unsafe("custom instruction has no successful target observation");
      else {
        if (command[0] != pc || command[1] != bits)
          throw std::logic_error("target command does not match committed instruction");
        const auto result = target->command(pc, bits, command[2], command[3], cpu.issue.value_or(0));
        for (unsigned i = 0; i < decoded.write_count; ++i) {
          if (engine.issue_frontier()) engine.publish(decoded.writes[i], result.ready && cpu.ready ?
              std::optional<Cycle>{std::max(*result.ready, *cpu.ready)} : std::nullopt);
          else unknown("asynchronous result has unknown command admission");
        }
      }
    } else if (command_pending) unsafe("target command was attached to a non-custom instruction");
    if (decoded.counter_read && (!model.scope_pc_pair || pc == model.scope_begin_pc || pc == model.scope_end_pc)) {
      const bool opening = model.scope_pc_pair ? pc == model.scope_begin_pc : !counter_pending;
      if (opening) {
        if (counter_pending) unsafe("counter scope opened again before completion");
        counter_pending = true; first_counter = cpu.start;
        first_counter_pc = pc; first_counter_instruction = instructions;
        first_counter_features = features;
        if (scoped_resources && windows.size()==model.scope_window) scoped_resources->begin(cpu.start);
      } else {
        if (!counter_pending) { unsafe("counter scope closed without its opening boundary"); return; }
        if (windows.size() >= model.max_counter_windows)
          throw std::runtime_error("counter-window observation budget exceeded");
        std::optional<Cycle> elapsed;
        if (first_counter && cpu.start && *cpu.start >= *first_counter) elapsed = *cpu.start - *first_counter;
        std::map<std::string, std::uint64_t> scoped;
        const bool selected = model.document.get<std::string>("scope.kind") != "whole_program" &&
            model.scope_window == windows.size();
        if (selected) for (const auto &feature : features) {
          const auto before = first_counter_features.find(feature.first);
          const auto delta = feature.second - (before == first_counter_features.end() ? 0 : before->second);
          scoped.emplace(feature.first, delta);
        }
        if (scoped_resources && selected) scoped_resources->end(cpu.start);
        windows.push_back({first_counter_pc, pc, instructions - first_counter_instruction, elapsed, std::move(scoped),
                           selected ? unresolved : std::set<std::string>{}, engine.report().complete && !trapped,
                           selected ? feature_reasons() : std::set<std::string>{}});
        counter_pending = false;
        if (selected && stop_after_selected_scope) {
          accounting_stopped = true;
          engine.trace_sink({});
        }
      }
    }
  }
  std::string cold_write_report()const{
    const bool dirty=bool(model.document.get_child_optional("memory.device_write_miss_pipeline.dirty_victim"));
    const bool victim=bool(model.document.get_child_optional("memory.device_write_miss_pipeline.private_victim"));
    std::ostringstream o;
    o<<"{\"native_allocation\":\"one_actual_lookup_after_finite_admission_exact_preview\","
     <<"\"full_line\":\"AcquirePerm_without_data_fill\",\"subline\":\"AcquireBlock_eight_64bit_fill_beats\","
     <<"\"victims\":"<<json_string(victim?"source_bound_single_Dcache_rprobe_dirty_upgrade":dirty?"dirty_or_clean_without_private_client":"invalid_or_clean_without_private_client")
     <<",\"transport\":\"SourceA2_SourceC12_Cork2_SinkD2_SourceE2_finite\",\"demand_mshrs\":10,\"cork_sinks\":8,"
     <<"\"publication\":\"old_DRAM_at_ReleaseAck_distinct_new_SourceD_S4\","
     <<"\"acquire_order\":\"after_SourceC_request_capture_not_ReleaseAck\","
     <<"\"private_probe\":"<<json_string(victim?"directB_innerC2_SinkC1_registered_first_last_and_separate_SRAM_publication":"unsupported")
     <<",\"private_CPU_admission\":"<<json_string(victim?"prior_accepted_completion_bound_postgrant8_no_atomic_later_private_access_waits_actual_client_release":"legacy")
     <<",\"bounds\":[\"whole_fill_before_subline_SourceD\",\"same_set_serialized_through_publication_and_source_closure\",\"lower_memory_startup_remains_selected_uncertain_price\"],"
     <<"\"unsupported\":[\"cold_target_private_hit\",\"atomic_LRSC_private_state\",\"external_shared_service_before_actual_full_fence\",\"retry_or_denied_outer_response\"]}";
    return o.str();
  }
  void write_report(int exit_code, bool completed) {
    memory->source_report();
    if(target_context && target) {
      const auto c=instruction_context(merlin_timing::InstructionPhase::before_report);
      target_context(target.get(),&c);
    }
    if (finished) throw std::logic_error("timing report already finalized");
    finished = true;
    if (in_instruction) unsafe("instruction observation is unfinished");
    if (trapped) unsafe("trapping instruction timing and exception transition are unsupported");
    if (event_trace) event_trace->finish(completed && exit_code == 0);
    const auto observed = engine.report();
    if (counter_pending) unsafe("unmatched cycle counter boundary");
    std::optional<Cycle> estimate = observed.modeled_makespan;
    const auto scope_kind = model.document.get<std::string>("scope.kind");
    if (scope_kind == "counter_pair" || scope_kind == "counter_pc_pair") {
      const auto index = model.scope_window;
      if (index >= windows.size()) { unsafe("selected counter window was not executed"); estimate.reset(); }
      else estimate = windows[index].cycles;
    } else if (scope_kind != "whole_program") {
      unsafe("unsupported measurement boundary"); estimate.reset();
    }
    const bool scoped = scope_kind != "whole_program" && model.scope_window < windows.size();
    const auto scope_features = scoped ? &windows[model.scope_window].features : &features;
    const auto &scope_reasons = scoped ? windows[model.scope_window].unresolved : unresolved;
    const bool event_complete = scoped ? windows[model.scope_window].timing_complete : observed.complete;
    auto count_reasons = scoped ? windows[model.scope_window].count_unresolved : feature_reasons();
    const auto counted_instructions = scoped ? windows[model.scope_window].instructions : instructions;
    std::uint64_t cpu_total = 0;
    for (const auto *name : cpu_feature_classes) {
      const auto found = scope_features->find(name);
      if (found == scope_features->end() || found->second > std::numeric_limits<std::uint64_t>::max() - cpu_total)
        count_reasons.insert("primary CPU feature coverage is incomplete or overflows");
      else cpu_total += found->second;
    }
    if (cpu_total != counted_instructions) count_reasons.insert("CPU class counts do not cover every scoped instruction");
    if (!completed || exit_code != 0 || (!scoped && scope_kind != "whole_program") || trapped)
      count_reasons.insert("functional execution or selected observation scope is incomplete");
    const bool counts_complete = count_reasons.empty();
    const bool complete = completed && event_complete && scope_reasons.empty() && exit_code == 0 && estimate.has_value();
    const std::string estimated_json = complete ? std::to_string(estimate.value_or(0)) : "null";
    std::ostringstream out;
    out << "{\"schema\":\"merlin.annotated_spike_report.v2\",\"profile\":" << json_string(model.profile)
        << ",\"device_sha256\":" << json_string(model.device)
        << ",\"domain_sha256\":" << json_string(sha256_bytes(model.domain_json()))
        << ",\"domain\":" << model.domain_json()
        << ",\"model_sha256\":" << json_string(model.digest)
        << ",\"feature_engine_sha256\":" << json_string(SPIKE_TIMING_SOURCE_SHA256)
        << ",\"elf_sha256\":" << json_string(elf_digest)
        << ",\"input_sha256\":" << (input_digest.empty() ? "null" : json_string(input_digest))
        << ",\"scope_sha256\":" << json_string(model.scope)
        << ",\"functional_status\":" << json_string(exit_code == 0 && completed ? "PASS" : "FAIL")
        << ",\"functional_status_scope\":\"ELF exit status; independent numerical gate remains required\""
        << ",\"execution_completed\":" << (completed ? "true" : "false")
        << ",\"raw_functional_exit_code\":" << exit_code
        << ",\"timing_complete\":" << (complete ? "true" : "false")
        << ",\"estimated_cycles\":" << estimated_json
        << ",\"engine_qualification\":\"not_established\""
        << ",\"uncertainty\":{\"status\":\"unqualified\",\"interval_cycles\":null}"
        << ",\"memory_initial_state\":" << memory->bootstrap_report()
        << ",\"integer_divider_service\":" << (integer_divider_bound(model) ?
          "{\"mode\":\"provisional_component_service_bound\",\"latency_cycles\":67,"
          "\"occupancy_cycles\":68,\"response_ready\":\"assumed_immediate\","
          "\"scope\":\"MulDiv request acceptance to response availability and ready-state release\","
          "\"limitations\":\"No core writeback/arbitration or backpressure bound; whole-SoC estimate is not an upper bound\"}" : "null")
        << ",\"posted_source_timeline\":" << (posted_timeline ?
          (std::string("{\"enabled\":true,\"causal_dispatches\":")+std::to_string(posted_timeline->progress().dispatched)+
          ",\"pending\":"+std::to_string(posted_timeline->progress().pending)+
          ",\"software_token_budget\":"+std::to_string(posted_timeline->specification().tokens)+
          ",\"software_dispatch_budget\":"+std::to_string(posted_timeline->specification().dispatched)+
          ",\"memory_service\":"+json_string(model.number("target.scheduling.source_reader_memory_owned_cache_pipeline")==std::optional<double>{1}?
            "native_cache_stage_composition_with_aggregate_packet_ready_bound":"aggregate_packet_completion_bound")+
          ",\"read_allocation_service\":"+json_string(memory->source_read_allocations_selected()?
            "optional_V7_single_lookup_rprobe_release_acquire_source_response_with_native_CPU_ownership":"legacy_aggregate_read_allocation")+
          ",\"read_allocation_bounds\":"+(memory->source_read_allocations_selected()?
            std::string("[\"native_read_lookup_precedes_finite_pool_admission\",\"whole_fill_before_SourceD_read\",\"inner_D_external_backpressure_not_source_closed\",\"shared_SourceD_controller_conservatively_held_through_last_response_or_S4\"]"):std::string("[]"))+
          ",\"response_order\":\"provisional_ready_fifo\",\"reader_transport\":"+json_string(
            model.number("target.scheduling.source_reader_registered_path")==std::optional<double>{1}?
            "selected_registered_tlb_client_shared_buffers":"legacy_response_transport")+
          ",\"readout_service\":"+json_string(model.number("target.scheduling.source_full_raw_packet_readout")==std::optional<double>{1}?
            "source_i8_and_full_raw_finite_writer_conditional_source_d":
            model.number("target.scheduling.source_masked_i8_readout")==std::optional<double>{1}?
            "source_i8_frontend_finite_writer_conditional_masked_source_d_raw_fallback_bound":
            model.number("target.scheduling.source_aligned_i8_readout")==std::optional<double>{1}?
            "source_i8_frontend_finite_writer_raw_fallback_bound":"raw_aggregate_writer_bound")+
          ",\"accumulator_load_service\":"+json_string(model.number("target.scheduling.source_full_accumulator_load")==std::optional<double>{1}?
            "source_queue_register_overwrite_and_stride_zero_broadcast":"legacy_or_unsupported")+
          ",\"cold_write_service\":"+(model.number("target.scheduling.source_cold_write_misses")==std::optional<double>{1}?
            cold_write_report():std::string("null"))+
          ",\"qualification\":\"not_established\",\"limitations\":[\"general LLC/MSHR and lower memory response arbitration not source closed\",\"raw packet coverage requires original full-packet rows and admitted cache ownership\",\"typed write admission is conditional and does not imply broader coverage\"]}") : "null")
        << ",\"instructions\":" << instructions << ",\"aborted_instructions\":" << aborted_instructions
        << ",\"feature_observation\":{\"schema\":\"merlin.spike_feature_observation.v1\",\"complete\":"
        << (counts_complete ? "true" : "false") << ",\"scope_instructions\":" << counted_instructions
        << ",\"counted_cpu_instructions\":" << cpu_total << ",\"scope_kind\":" << json_string(scope_kind)
        << ",\"window_index\":" << (scoped ? std::to_string(model.scope_window) : "null")
        << ",\"primary_cpu_features\":[";
    bool first = true;
    for (const auto *name : cpu_feature_classes) {
      if (!first) out << ',';
      first = false; out << json_string(name);
    }
    out << "],\"unresolved\":["; first = true;
    for (const auto &reason : count_reasons) {
      if (!first) out << ',';
      first = false; out << json_string(reason);
    }
    out << "],\"qualification\":\"not_established\"}"
        << ",\"memory_dependency_entries\":" << memory->pending_tokens()
        << ",\"feature_counts\":{";
    first = true;
    for (const auto &feature : *scope_features) {
      if (!first) out << ',';
      first = false;
      out << json_string(feature.first) << ':' << feature.second;
    }
    out << "},\"loaded_library_sha256\":["; first = true;
    for (const auto &digest : library_digests) {
      if (!first) out << ',';
      first = false; out << json_string(digest);
    }
    out << "],\"unresolved\":["; first = true;
    for (const auto &reason : scope_reasons) {
      if (!first) out << ',';
      first = false; out << json_string(reason);
    }
    if (!event_complete) {
      if (!first) out << ',';
      out << "\"event timing or accounting is incomplete\"";
    }
    out << "],\"whole_trace_timing_complete\":" << (!accounting_stopped && observed.complete && unresolved.empty() ? "true" : "false")
        << ",\"timing_accounting\":{\"schema\":\"merlin.observer_accounting.v1\",\"policy\":"
        << json_string(stop_after_selected_scope ? "through_selected_counter_end" : "whole_trace")
        << ",\"stopped_after_selected_scope\":" << (accounting_stopped ? "true" : "false")
        << ",\"modeled_instructions\":" << accounted_instructions
        << ",\"architectural_instructions\":" << instructions
        << ",\"unmodeled_suffix_instructions\":" << instructions - accounted_instructions
        << ",\"functional_execution_stopped\":false}"
        << ",\"cycle_breakdown\":{\"scope\":\"whole_trace\",\"additive\":false,\"available\":"
        << (accounting_stopped ? "false" : "true")
        << ",\"reason\":" << (accounting_stopped ? json_string("whole-trace accounting stopped after the selected end; scoped capture is retained") : "null")
        << ",\"modeled_horizon\":" << (accounting_stopped ? "null" : std::to_string(observed.modeled_makespan))
        << ",\"resources\":["; first = true;
    if (!accounting_stopped) for (const auto &resource : observed.resources) {
      if (!first) out << ',';
      first = false;
      out << "{\"resource_id\":" << resource.id << ",\"reservations\":" << resource.reservations
          << ",\"busy_unit_cycles\":" << cycle_json(resource.busy_unit_cycles)
          << ",\"unknown_events\":" << resource.unknown_events
          << ",\"peak_queue_entries\":" << resource.peak_queue_entries << '}';
    }
    out << "]}";
    if (scoped_resources) {
      out << ",\"scoped_resource_activity\":{\"schema\":\"merlin.scoped_resource_activity.v1\",\"source_kind\":\"modeled\","
          << "\"unit\":\"model_cycles\",\"complete\":" << (complete && scoped_resources->complete() ? "true" : "false")
          << ",\"scope_sha256\":" << json_string(model.scope) << ",\"model_sha256\":" << json_string(model.digest)
          << ",\"elf_sha256\":" << json_string(elf_digest) << ",\"scope_binding_sha256\":" << json_string(model.scope_binding_digest)
          << ",\"begin_cycle\":" << cycle_json(scoped_resources->first()) << ",\"end_cycle\":" << cycle_json(scoped_resources->last())
          << ",\"resources\":["; first=true;
      for (const auto& r:scoped_resources->rows()) {
        if (!first) out << ','; first=false;
        std::string resource_name;
        for (const auto& entry:model.document.get_child("resources"))
          if (entry.second.get<uint32_t>("id")==r.id) resource_name=entry.second.get<std::string>("name");
        out << "{\"resource_id\":" << r.id << ",\"name\":" << json_string(resource_name) << ",\"capacity\":" << r.capacity
            << ",\"busy_unit_cycles\":" << r.busy << ",\"active_cycles\":" << r.active
            << ",\"queued_entry_cycles\":" << r.queued << ",\"queue_active_cycles\":" << r.queue_active
            << ",\"peak_active_units\":" << r.peak_units << ",\"peak_queue_entries\":" << r.peak_queue << '}';
      }
      out << "],\"overlaps\":["; first=true;
      for (const auto& pair:scoped_resources->pairs()) {
        if (!first) out << ','; first=false;
        out << "{\"left\":" << scoped_resources->rows()[pair.left].id << ",\"right\":" << scoped_resources->rows()[pair.right].id
            << ",\"active_cycles\":" << pair.active << '}';
      }
      out << "],\"meaning\":\"capacity reservations and generic start queues, not physical utilization or stalls\"}";
    }
    if (model.scope_pc_pair)
      out << ",\"scope_binding_sha256\":" << json_string(model.scope_binding_digest)
          << ",\"scope_binding\":{\"schema\":\"merlin.spike_scope_binding.v1\",\"elf_sha256\":" << json_string(elf_digest)
          << ",\"input_sha256\":" << json_string(input_digest) << ",\"scope_sha256\":" << json_string(model.scope)
          << ",\"begin_pc\":" << model.scope_begin_pc << ",\"end_pc\":" << model.scope_end_pc
          << ",\"occurrence\":" << model.scope_window << ",\"evidence_sha256\":" << json_string(model.scope_binding_evidence) << '}';
    out << ",\"counter_windows\":["; first = true;
    for (const auto &window : windows) {
      if (!first) out << ',';
      first = false;
      out << "{\"begin_pc\":" << window.begin_pc << ",\"end_pc\":" << window.end_pc
          << ",\"instructions\":" << window.instructions << ",\"estimated_cycles\":" << cycle_json(window.cycles) << '}';
    }
    out << "]}\n";
    const auto temporary = report_path + ".partial";
    if (std::filesystem::exists(temporary)) throw std::runtime_error("timing report temporary file already exists");
    std::ofstream file(temporary, std::ios::binary);
    if (!file || !(file << out.str())) throw std::runtime_error("cannot write timing report");
    file.close();
    if (!file || std::rename(temporary.c_str(), report_path.c_str()))
      throw std::runtime_error("cannot commit timing report");
  }
};

Session::Session(const std::string &model, const std::string &report,
                 const std::string &elf, const std::string &input_digest,
                 const std::vector<std::string> &libraries,
                 std::function<unsigned(std::uint64_t, std::size_t)> memory_kind,
                 const std::string &scope_binding, const std::string &event_trace_path)
    : impl_(std::make_unique<Impl>(model, report, elf, input_digest, libraries, std::move(memory_kind), scope_binding, event_trace_path)) {
  if (active) throw std::logic_error("only one annotated session is supported");
  active = this;
}
Session::~Session() { if (active == this) active = nullptr; }
bool enabled() noexcept { return active != nullptr; }
void before(processor_t *p, std::uint64_t pc, std::uint64_t bits) { active->impl_->begin(p, pc, bits); }
void after(std::uint64_t pc, bool committed) { active->impl_->finish_instruction(pc, committed); }
void aborted() noexcept { if (active) active->impl_->abort_instruction(); }
bool Session::interested_in_range(std::uint64_t, std::uint64_t, access_type type) { return !impl_->accounting_stopped && type != FETCH; }
void Session::trace(std::uint64_t address, std::size_t bytes, access_type type) { impl_->record_memory(address, bytes, type); }
void Session::clean_invalidate(std::uint64_t, std::size_t, bool, bool) { impl_->unknown("cache-block maintenance semantics are unsupported"); }
void Session::finish(int exit_code, bool completed) { impl_->write_report(exit_code, completed); }
} // namespace spike_timing
