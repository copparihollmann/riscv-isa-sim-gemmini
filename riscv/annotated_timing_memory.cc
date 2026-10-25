#include "../timing/memory.hpp"
#include "tsi_elf_bootstrap.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <iterator>
#include <set>

namespace spike_timing {
namespace {
using merlin_timing::Cycle;
bool add(Cycle &value, Cycle increment) {
  if (increment > std::numeric_limits<Cycle>::max() - value) return false;
  value += increment; return true;
}
std::size_t positive(const boost::property_tree::ptree &row, const char *key, std::size_t max) {
  const auto v = row.get<std::size_t>(key);
  if (!v || v > max) throw std::invalid_argument("cache geometry exceeds bounds");
  return v;
}
std::uint64_t cover(std::map<std::uint64_t, std::uint64_t> &ranges,
                    std::uint64_t begin, std::uint64_t end) {
  auto it = ranges.lower_bound(begin);
  if (it != ranges.begin() && std::prev(it)->second >= begin) --it;
  std::uint64_t covered = 0, left = begin, right = end;
  while (it != ranges.end() && it->first <= right) {
    left = std::min(left, it->first); right = std::max(right, it->second);
    covered += it->second - it->first; it = ranges.erase(it);
  }
  ranges.emplace(left, right);
  return right - left - covered;
}
} // namespace

MemorySystem::MemorySystem(const Model &model, merlin_timing::Engine &engine,
                           std::function<merlin_timing::ValueId(std::size_t)> allocate,
                           std::function<void(const std::string &, std::uint64_t)> feature,
                           std::function<void(const std::string &)> unresolved)
    : model_(model), engine_(engine), allocate_(std::move(allocate)),
      feature_(std::move(feature)), unresolved_(std::move(unresolved)) {
  for (const auto *name : {"modeled.dram_request_bytes", "modeled.writeback_bytes",
                           "modeled.coherence_probes", "modeled.coherence_writeback_bytes",
                           "modeled.immutable_requested_bytes"}) feature_(name, 0);
  for (const auto *path : {"cpu_fetch", "cpu_data", "device"}) {
    feature_(std::string(path) + ".requested_read_bytes", 0);
    feature_(std::string(path) + ".requested_write_bytes", 0);
  }
  if (const auto policy = model.document.get_optional<std::string>("memory.transaction_accounting")) {
    if (*policy != "coherence_request_separate_v1")
      throw std::invalid_argument("unsupported memory transaction accounting");
    separate_coherence_transactions_ = true;
  }
  if (const auto granule = model.number("memory.coherence_granule")) {
    if (*granule >= 1 && *granule <= (1 << 20) && std::floor(*granule) == *granule &&
        !(static_cast<std::uint64_t>(*granule) & (static_cast<std::uint64_t>(*granule) - 1)))
      granule_ = static_cast<std::uint64_t>(*granule);
  }
  if (const auto caches = model.document.get_child_optional("memory.caches")) {
    if (caches->size() > 16) throw std::invalid_argument("too many cache levels");
    for (const auto &entry : *caches) {
      const auto sets = positive(entry.second, "sets", 1 << 20);
      const auto ways = positive(entry.second, "ways", 1024);
      const auto line = positive(entry.second, "line_bytes", 1 << 20);
      if (line & (line - 1)) throw std::invalid_argument("cache line size must be a power of two");
      if (sets > (1 << 20) / ways) throw std::invalid_argument("cache entry budget exceeded");
      if (entry.second.get<std::string>("policy") != "write_back_write_allocate")
        throw std::invalid_argument("cache allocation policy is unsupported");
      std::optional<merlin_timing::ReadSteppedLfsrSpec> replacement;
      if(const auto r=entry.second.get_child_optional("replacement")) {
        if(r->size()!=6 || r->get<std::string>("schema")!="merlin.read_stepped_lfsr_replacement.v1" ||
           !is_digest(r->get<std::string>("source_receipt_sha256")))
          throw std::invalid_argument("cache replacement needs exact source-reviewed law");
        replacement=merlin_timing::ReadSteppedLfsrSpec{r->get<unsigned>("width"),r->get<unsigned>("selection_bits"),
            r->get<std::uint64_t>("feedback_mask"),r->get<std::uint64_t>("seed")};
      }
      caches_.emplace(entry.first, std::make_unique<merlin_timing::SetAssociativeCache>(
          merlin_timing::CacheSpec{sets, ways, line},replacement));
      feature_("modeled.cache." + entry.first + ".hits", 0);
      feature_("modeled.cache." + entry.first + ".misses", 0);
      lines_[entry.first] = line;
      cache_tokens_[entry.first] = allocate_(sets * ways);
      cache_generations_[entry.first].resize(sets*ways);
      if (const auto service = entry.second.get_child_optional("coherence_probe_service")) {
        const auto resource = model.resource(service->get<std::string>("resource"));
        const auto beat = positive(*service, "beat_bytes", 1 << 20);
        const auto cycles = [&](const char *field) {
          const auto value = service->get<std::uint64_t>(field);
          if (value > 4096) throw std::invalid_argument("private probe pipeline exceeds bound");
          return value;
        };
        const auto found = resource ? std::find_if(model.resources.begin(), model.resources.end(),
            [&](const auto &spec) { return spec.id == *resource && spec.capacity == 1; }) : model.resources.end();
        if (service->get<std::string>("schema") != "merlin.private_cache_probe_service.v1" ||
            !resource || found == model.resources.end() || beat > line || line % beat)
          throw std::invalid_argument("unsupported serialized private cache probe service");
        probe_service_.emplace(entry.first, ProbeService{*resource, beat,
            cycles("lookup_cycles"), cycles("dirty_enter_cycles"),
            cycles("data_pipeline_cycles"), cycles("metadata_cycles"), std::nullopt});
        if (const auto response = service->get_child_optional("write_response")) {
          // Source-backed wormhole predicate, with a separately identified
          // no-backpressure response pipeline. Public physical observations may
          // calibrate this pipeline; it is not a per-dirty/clean price.
          if (response->size()!=4 ||
              response->get<std::string>("schema")!="merlin.provisional_probe_write_response.v1" ||
              response->get<std::string>("scope")!="offset_zero_wormhole_no_backpressure" ||
              response->get<std::uint64_t>("block_bytes")!=line)
            throw std::invalid_argument("unsupported private probe write response");
          const auto pipeline=response->get<std::uint64_t>("pipeline_cycles");
          if (!pipeline || pipeline>4096)
            throw std::invalid_argument("probe response pipeline exceeds bound");
          probe_service_.at(entry.first).write_response_pipeline=pipeline;
          for (const auto *suffix:{"response_first_cycles","response_last_cycles",
                                  "response_completion_cycles","response_wormhole"})
            feature_("modeled.cache."+entry.first+"."+suffix,0);
        }
        feature_("modeled.cache." + entry.first + ".coherence_protocol_cycles", 0);
      }
      if (const auto service = entry.second.get_child_optional("byte_service")) {
        const auto price = model.parameter("memory." + entry.first + ".per_byte_cycles");
        const auto resource = model.resource(service->get<std::string>("resource"));
        if (service->get<std::string>("schema") != "merlin.cache_boundary_byte_service.v1" ||
            !price || *price <= 0 || !resource)
          throw std::invalid_argument("unsupported cache boundary byte service");
        feature_("modeled.cache." + entry.first + ".boundary_bytes", 0);
      }
    }
  }
  if (const auto paths = model.document.get_child_optional("memory.paths")) {
    for (const auto &entry : *paths) {
      if (entry.second.size() > 16) throw std::invalid_argument("cache path is too long");
      auto &path = paths_[entry.first];
      std::set<std::string> seen;
      for (const auto &level : entry.second) {
        const auto name = level.second.get_value<std::string>();
        if (!caches_.count(name) || !seen.insert(name).second)
          throw std::invalid_argument("unknown or cyclic cache path");
        path.push_back(name);
      }
    }
  }
  // Topology is explicit and source-bound: a Get/Hint-only instruction cache
  // is not an inclusive directory client and cannot produce ProbeAck. This
  // does not invalidate its contents or replace the separate FENCE.I path.
  if(const auto cache_roles=model.document.get_child_optional("memory.caches"))for(const auto&entry:*cache_roles){
    if(const auto role=entry.second.get_child_optional("coherence_role")){
      const auto kind=role->get<std::string>("kind");
      if(role->size()!=3||role->get<std::string>("schema")!="merlin.private_cache_coherence_role.v1"||
         !is_digest(role->get<std::string>("source_receipt_sha256"))||
         (kind!="probe_client"&&kind!="get_hint_noncoherent"))
        throw std::invalid_argument("private coherence role requires exact source topology");
      if(kind=="get_hint_noncoherent"){
        const auto fetch=paths_.find("cpu_fetch");
        if(fetch==paths_.end()||fetch->second.empty()||fetch->second.front()!=entry.first)
          throw std::invalid_argument("noncoherent instruction role must own the selected fetch cache");
        for(const auto*other:{"cpu_data","device"}){
          const auto path=paths_.find(other);
          if(path!=paths_.end()&&std::find(path->second.begin(),path->second.end(),entry.first)!=path->second.end())
            throw std::invalid_argument("noncoherent instruction cache cannot share a writable path");
        }
        noncoherent_private_.insert(entry.first);
      }
    }
  }
  if(const auto selected=model.document.get_child_optional("memory.device_read_pipeline")) {
    const auto &r=*selected;const auto cache=r.get<std::string>("cache");
    const auto found=paths_.find("device");
    if(r.size()!=8 || r.get<std::string>("schema")!="merlin.source_device_read_pipeline.v1" ||
       r.get<unsigned>("enabled")!=1 || !is_digest(r.get<std::string>("source_receipt_sha256")) ||
       found==paths_.end() || found->second!=std::vector<std::string>{cache} ||
       model.document.get_child_optional("memory.caches."+cache+".byte_service"))
      throw std::invalid_argument("unsupported device cache source-pipeline selection");
    const auto directory=positive(r,"directory_stages",16), plan=positive(r,"mshr_plan_stages",16),
               response=positive(r,"source_d_stages",16), scalar=positive(r,"scalar_lookup_cycles",16);
    if(model.cycles("memory."+cache+".hit_cycles")!=std::optional<Cycle>{scalar} ||
       model.cycles("memory."+cache+".miss_cycles")!=std::optional<Cycle>{scalar} || directory+plan+response<scalar)
      throw std::invalid_argument("device cache source pipeline must replace exact scalar lookup components");
    device_read_pipeline_=DeviceReadPipeline{cache,scalar,directory+plan+response};
    feature_("modeled.cache."+cache+".source_read_pipeline_applied",0);
    feature_("modeled.cache."+cache+".source_read_pipeline_extension_cycles",0);
  }
  if(const auto selected=model.document.get_child_optional("memory.device_write_request_pipeline")) {
    const auto&r=*selected;const auto cache=r.get<std::string>("cache");const auto found=paths_.find("device");
    if((r.size()!=7&&r.size()!=8)||r.get<std::string>("schema")!="merlin.source_device_write_request_pipeline.v1"||
       r.get<unsigned>("enabled")!=1||!is_digest(r.get<std::string>("source_receipt_sha256"))||
       found==paths_.end()||found->second!=std::vector<std::string>{cache}||
       model.document.get_child_optional("memory.caches."+cache+".byte_service"))
      throw std::invalid_argument("unsupported typed device write source pipeline");
    const auto directory=positive(r,"directory_stages",16),plan=positive(r,"mshr_plan_stages",16),scalar=positive(r,"scalar_lookup_cycles",16);
    if(directory!=1||plan!=1||scalar!=1||model.cycles("memory."+cache+".hit_cycles")!=std::optional<Cycle>{scalar})
      throw std::invalid_argument("typed write request must replace selected scalar Directory/MSHR components");
    device_write_request_pipeline_=DeviceReadPipeline{cache,scalar,directory+plan};
    if(const auto probe=r.get_child_optional("single_private_probe")){
      if(probe->size()!=8||probe->get<std::string>("schema")!="merlin.selected_probe_sinkc_handoff.v1"||
         probe->get<unsigned>("line_bytes")!=64||probe->get<unsigned>("beat_bytes")!=16||
         probe->get<unsigned>("sinkc_queue_stages")!=1||probe->get<unsigned>("mshr_response_register_stages")!=1||
         probe->get<unsigned>("banked_store_banks")!=8||probe->get<unsigned>("banked_store_write_bytes")!=8||
         !is_digest(probe->get<std::string>("source_receipt_sha256")))
        throw std::invalid_argument("single private probe needs exact selected SinkC/MSHR/banked-store source law");
      typed_single_private_probe_=true;
    }
    feature_("modeled.typed_write.client_transaction_bytes",0);feature_("modeled.typed_write.useful_bytes",0);
  }
  if(const auto selected=model.document.get_child_optional("memory.device_write_miss_pipeline")){
    const auto&r=*selected;
    if((r.size()<7||r.size()>9)||r.get<std::string>("schema")!="merlin.selected_cold_write_miss.v1"||
       r.get<unsigned>("enabled")!=1||!device_write_request_pipeline_||
       r.get<std::string>("cache")!=device_write_request_pipeline_->cache||
       r.get<unsigned>("line_bytes")!=64||r.get<unsigned>("outer_beat_bytes")!=8||
       r.get<unsigned>("demand_mshrs")!=10||!is_digest(r.get<std::string>("source_receipt_sha256"))||
       lines_.at(device_write_request_pipeline_->cache)!=64)
      throw std::invalid_argument("cold writes require exact selected SourceA/Cork/SinkD/10-demand-MSHR law");
    typed_cold_write_selected_=true;
    if(const auto dirty=r.get_child_optional("dirty_victim")){
      if(dirty->size()!=7||dirty->get<std::string>("schema")!="merlin.selected_sourcec_dirty_writeback.v1"||
         dirty->get<unsigned>("sourcec_read_pipeline_stages")!=2||dirty->get<unsigned>("sourcec_queue_entries")!=12||
         dirty->get<unsigned>("line_beats")!=8||dirty->get<unsigned>("outer_beat_bytes")!=8||
         dirty->get<std::string>("banked_store_priority")!="sinkc_sourcec_sinkd_sourcedw_sourcedr"||
         !is_digest(dirty->get<std::string>("source_receipt_sha256"))||granule_!=64)
        throw std::invalid_argument("dirty writeback needs selected SourceC/BankedStore/Cork source law and64-byte ownership granules");
      typed_dirty_victim_selected_=true;
    }
    if(const auto v=r.get_child_optional("private_victim")){
      const auto name=v->get<std::string>("private_cache");
      if(v->size()!=9||v->get<std::string>("schema")!="merlin.selected_private_victim_probe.v1"||
         !is_digest(v->get<std::string>("source_receipt_sha256"))||v->get<unsigned>("clients")!=1||
         v->get<unsigned>("line_bytes")!=64||v->get<unsigned>("inner_c_entries")!=2||
         v->get<unsigned>("sinkc_entries")!=1||v->get<unsigned>("postgrant_guard")!=8||
         v->get<std::string>("cpu_readiness")!="accepted_completion_upper_bound"||
         paths_.at("cpu_data")!=std::vector<std::string>{name,device_write_request_pipeline_->cache}||
         model.document.get<std::string>("memory.caches."+name+".coherence_role.kind","")!="probe_client"||
         !typed_dirty_victim_selected_||!probe_service_.count(name)||lines_.at(name)!=64)
        throw std::invalid_argument("victim probe requires selected single D-cache source topology and accepted CPU completion");
      typed_private_victim_selected_=true;victim_private_cache_=name;
      victim_source_identity_=v->get<std::string>("source_receipt_sha256");
    }
    for(const auto*name:{"permission_only","acquire_block","clean_victims","dirty_victims"})
      feature_(std::string("modeled.typed_write.cold.")+name,0);
  }
  if(const auto selected=model.document.get_child_optional("memory.source_read_allocations")){
    const auto&r=*selected;
    if(!device_write_request_pipeline_||!typed_private_victim_selected_||r.size()!=7||r.get<std::string>("schema")!="merlin.selected_source_read_allocations.v1"||
       r.get<unsigned>("enabled")!=1||r.get<std::string>("cache")!=device_write_request_pipeline_->cache||
       r.get<unsigned>("directory_stages")!=1||r.get<unsigned>("mshr_plan_stages")!=1||r.get<unsigned>("source_d_stages")!=2||
       !is_digest(r.get<std::string>("source_receipt_sha256"))||!typed_private_victim_selected_)
      throw std::invalid_argument("read allocations require explicit selected victim topology and Directory/MSHR/SourceD split");
    read_allocations_selected_=true;read_allocation_cache_=r.get<std::string>("cache");
  }
  if (const auto selected = model.document.get_child_optional("memory.fetch_refill_timeline")) {
    const auto &r=*selected;
    const auto found=paths_.find("cpu_fetch");
    if (r.size()!=8 || r.get<std::string>("schema")!="merlin.provisional_fetch_refill.v1" ||
        r.get<std::string>("assumptions")!="demand_only_immediate_replay_no_backpressure" ||
        found==paths_.end() || found->second.size()!=2)
      throw std::invalid_argument("unsupported provisional fetch refill selection");
    const auto &path=found->second;
    for (const auto *other : {"cpu_data","device"}) {
      const auto it=paths_.find(other);
      if (it!=paths_.end() && std::find(it->second.begin(),it->second.end(),path[0])!=it->second.end())
        throw std::invalid_argument("fetch refill requires a private first cache");
    }
    for (const auto &level:path)
      if (model.document.get_child_optional("memory.caches."+level+".byte_service"))
        throw std::invalid_argument("fetch refill cannot replace a separately priced byte-service path");
    const auto beat=positive(r,"beat_bytes",1<<20), line=lines_.at(path[0]);
    if (line%beat || line/beat>4096 || lines_.at(path[1])<line)
      throw std::invalid_argument("fetch refill line/beat geometry unsupported");
    const auto cycles=[&](const char *field) {
      const auto n=r.get<std::uint64_t>(field);
      if (n>4096) throw std::invalid_argument("fetch refill stage exceeds bound");
      return n;
    };
    const auto interval=cycles("beat_interval_cycles");
    if (!interval) throw std::invalid_argument("fetch response interval must be positive");
    fetch_refill_=FetchRefill{{static_cast<std::uint32_t>(line/beat),
        cycles("first_response_cycles"),interval,cycles("line_visible_after_last_cycles"),
        cycles("lookup_response_cycles")},cycles("request_accept_cycles")};
    for (const auto *name:{"applied","legacy_lower_miss","legacy_dirty_eviction","immutable",
                          "first_response_cycles","last_response_cycles","line_visible_cycles","lookup_response_cycles"})
      feature_(std::string("modeled.fetch_refill.")+name,0);
  }

}

void MemorySystem::bootstrap_primary_elf(const std::string &elf) {
  const auto selected=model_.document.get_child_optional("memory.initial_state");
  if(!selected)return;
  const auto &s=*selected;
  const bool source_directory=s.get<std::string>("schema")=="merlin.tsi_elf_cache_bootstrap.v2";
  if(s.size()!=(source_directory?8:7) ||
      (!source_directory && s.get<std::string>("schema")!="merlin.tsi_elf_cache_bootstrap.v1") ||
      s.get<std::string>("loader")!="elf64_le_riscv_exec_pt_load" ||
      s.get<std::string>("cache")!="l2" || s.get<unsigned>("chunk_align")!=4 ||
      s.get<unsigned>("chunk_max_size")!=1024 ||
      s.get<std::string>("replacement_scope")!=(source_directory?"serialized_tsi64_directory_reads":"one_loaded_line_per_set") ||
      !is_digest(s.get<std::string>("source_receipt_sha256")) || !caches_.count("l2"))
    throw std::invalid_argument("unsupported source-reviewed loader cache bootstrap");
  const auto replacement=model_.document.get_child_optional("memory.caches.l2.replacement");
  if(source_directory) {
    if(!replacement || replacement->get<unsigned>("width")!=16 || replacement->get<unsigned>("selection_bits")!=10 ||
       replacement->get<std::uint64_t>("feedback_mask")!=0xb400 || replacement->get<std::uint64_t>("seed")!=1 ||
       !is_digest(s.get<std::string>("directory_read_contract_sha256")))
      throw std::invalid_argument("TSI directory replay requires selected read-stepped16-bit replacement and ingress contract");
  } else if(replacement)throw std::invalid_argument("line-set bootstrap cannot substitute for directory event replay");
  try {
    const auto plan=tsi_elf_bootstrap(elf,model_.document.get<std::uint64_t>("memory.caches.l2.sets"),lines_.at("l2"),source_directory);
    // Selected loader writes complete before primary-program observation. No guest issue,
    // resource reservation or private-cache fill is synthesized here.
    if(source_directory) {
      for(const auto &event:plan.directory_reads){
        const auto result=caches_.at("l2")->access(event.address,event.write);
        if(!result.hit)++cache_generations_.at("l2").at(result.slot);
      }
    } else for(const auto line:plan.lines){
      const auto result=caches_.at("l2")->access(line*lines_.at("l2"),true);
      if(result.hit || result.evicted_line)throw std::logic_error("loader bootstrap unexpected replacement");
      ++cache_generations_.at("l2").at(result.slot);
    }
    const auto replacement_state=caches_.at("l2")->replacement_state();
    bootstrap_report_="{\"status\":\"applied\",\"execution_domain\":\"selected_gsim_tsi_no_loadmem\",\"scope\":\"before_guest_timing\",\"replacement_scope\":"+json_string(s.get<std::string>("replacement_scope"))+",\"source_receipt_sha256\":"+json_string(s.get<std::string>("source_receipt_sha256"))+",\"lines\":"+std::to_string(plan.lines.size())+",\"write_chunks\":"+std::to_string(plan.writes.size())+",\"written_bytes\":"+std::to_string(plan.bytes)+",\"resident_lines\":"+std::to_string(caches_.at("l2")->report().entries)+",\"directory_reads\":"+std::to_string(source_directory?plan.directory_reads.size():0)+",\"replacement_state\":"+(replacement_state?std::to_string(*replacement_state):"null")+"}";
    feature_("modeled.loader_bootstrap.directory_reads",source_directory?plan.directory_reads.size():0);
    feature_("modeled.loader_bootstrap.applied",1);
    feature_("modeled.loader_bootstrap.lines",plan.lines.size());
    feature_("modeled.loader_bootstrap.write_chunks",plan.writes.size());
    feature_("modeled.loader_bootstrap.written_bytes",plan.bytes);
  } catch(const std::invalid_argument &e) {
    bootstrap_report_="{\"status\":\"unsupported\",\"execution_domain\":\"selected_gsim_tsi_no_loadmem\",\"reason\":"+json_string(e.what())+"}";
    unresolved_(e.what());
    feature_("modeled.loader_bootstrap.unsupported",1);
  }
}

std::optional<merlin_timing::ValueId> MemorySystem::token(std::uint64_t region) {
  const auto old = tokens_.find(region);
  if (old != tokens_.end()) { building_.insert(old->second); return old->second; }
  if (!allocated_) {
    const auto base = allocate_(model_.max_memory_entries);
    free_.reserve(model_.max_memory_entries);
    for (std::size_t i = 0; i < model_.max_memory_entries; ++i) free_.push_back(base + i);
    allocated_ = true;
  }
  if (free_.empty()) {
    const auto frontier = engine_.issue_frontier();
    if (frontier) {
      for (auto it = tokens_.begin(); it != tokens_.end();) {
        const auto done = engine_.last_use(it->second);
        if (done && *done <= *frontier && !building_.count(it->second)) {
          engine_.reset(it->second); free_.push_back(it->second); it = tokens_.erase(it);
        } else ++it;
      }
    }
  }
  if (free_.empty()) {
    unresolved_("shared memory dependency capacity exceeded"); return {};
  }
  const auto result = free_.back(); free_.pop_back(); tokens_.emplace(region, result); building_.insert(result);
  return result;
}

void MemorySystem::charge(Walk &walk, const std::string &price, double units, bool bus) {
  const auto cost = model_.cycles(price, units);
  if (!cost || !add(walk.latency, *cost) || (bus && !add(walk.bus, *cost)))
    walk.complete = false;
}

void MemorySystem::cache_access(std::uint64_t address, std::uint64_t bytes, bool write,
                               const std::vector<std::string> &path, std::size_t level, Walk &walk) {
  if (!bytes) return;
  if (level == path.size()) {
    if (!granule_ || bytes - 1 > std::numeric_limits<std::uint64_t>::max() - address ||
        (bytes - 1) / granule_ + 1 > model_.max_memory_entries) {
      walk.complete = false; return;
    }
    const auto last_region = (address + bytes - 1) / granule_;
    for (auto region = address / granule_;; ++region) {
      if (const auto id = token(region)) (write ? walk.writes : walk.reads).insert(*id);
      else walk.complete = false;
      if (region == last_region) break;
    }
    charge(walk, "memory.dram_latency_cycles");
    charge(walk, "memory.dram_per_byte_cycles", bytes, true);
    feature_("modeled.dram_request_bytes", bytes);
    return;
  }
  const auto &name = path[level];
  const auto line_bytes = lines_.at(name);
  const auto last = (address + bytes - 1) / line_bytes;
  for (auto line = address / line_bytes;; ++line) {
    const auto key = std::make_tuple(name, line, walk.coherence_transaction);
    if (model_.document.get_child_optional("memory.caches." + name + ".byte_service")) {
      if (walk.byte_coverage.size() >= model_.max_memory_entries && !walk.byte_coverage.count(key)) {
        unresolved_("cache boundary byte coverage budget exceeded"); walk.complete = false; return;
      }
      // Each boundary sees exact requested intervals. A lower cache is visited
      // only when its parent misses or writes back; overlapping rows in one
      // architectural transaction consume their byte union once. Coherence
      // writebacks and device requests remain distinct when selected.
      const auto begin = std::max(address, line * line_bytes);
      const auto last_byte = std::min(address + bytes - 1, line * line_bytes + line_bytes - 1);
      if (last_byte == std::numeric_limits<std::uint64_t>::max()) {
        unresolved_("cache boundary byte interval overflows"); walk.complete = false; return;
      }
      walk.boundary_bytes[name] += cover(walk.byte_coverage[key], begin, last_byte + 1);
    }
    auto prior = walk.visited.find(key);
    if (prior != walk.visited.end() && !caches_.at(name)->probe(line * line_bytes).hit) {
      walk.visited.erase(prior); prior = walk.visited.end();
    }
    if (prior != walk.visited.end()) {
      // Preserve write state when an earlier effect read this line. It has
      // already been filled/priced in this architectural command.
      if (write && !prior->second) {
        const auto updated = caches_.at(name)->access(line * line_bytes, true);
        walk.writes.insert(cache_tokens_.at(name) + updated.slot);
        prior->second = true;
      }
    } else {
      if (walk.visited.size() >= model_.max_memory_entries) {
        unresolved_("single memory event exceeds cache transaction budget");
        walk.complete = false; return;
      }
      walk.visited.emplace(key, write);
      const auto device_path=paths_.find("device");
      if(device_path!=paths_.end() && device_path->second.size()==1 && name==device_path->second.front() &&
          !walk.coherence_transaction)walk.shared_lookup=true;
      std::optional<ReadAllocationV7>allocation;
      if(read_allocations_selected_&&!write&&name==read_allocation_cache_&&!typed_write_request_&&!walk.coherence_transaction){
        const auto preview=caches_.at(name)->preview_access(line*line_bytes);
        if(!preview.hit||!walk.coherence_probe){
          allocation.emplace();allocation->resident=preview.hit;auto&m=allocation->miss;m.line=line;m.slot=preview.slot;
          m.set=line%model_.document.get<std::uint64_t>("memory.caches."+name+".sets");
          m.generation=cache_generations_.at(name).at(preview.slot)+(preview.hit?0:1);m.evicted_line=preview.evicted_line;
          m.dirty_eviction=preview.dirty_eviction;m.acquire_block=!preview.hit;
          allocation->inner_acquire=(!walk.device&&!walk.cpu_fetch);
          allocation->inner_address=std::max(address,line*line_bytes);
          allocation->inner_bytes=std::min(address+bytes,(line+1)*line_bytes)-allocation->inner_address;
          if(preview.evicted_line){const auto p=caches_.at(victim_private_cache_)->probe(*preview.evicted_line*64);
            if(p.hit){
              if(!cpu_data_ready_||cpu_atomic_seen_){unresolved_("read allocation victim private readiness unsupported");walk.complete=false;return;}
              const auto generation=cache_generations_.at(name).at(preview.slot);
              if(!generation){unresolved_("read allocation original victim generation unavailable");walk.complete=false;return;}
              const auto ways=model_.document.get<std::uint64_t>("memory.caches."+name+".ways");
              allocation->victim=VictimProbeV6{*preview.evicted_line,m.set,preview.slot%ways,generation,
                cache_tokens_.at(victim_private_cache_)+*p.slot,preview.dirty_eviction,p.dirty,*cpu_data_ready_,victim_source_identity_};
              const auto&v=*allocation->victim;
              if(!victim_clients_.emplace(std::make_pair(v.private_slot,v.generation),v.client_ready).second){
                unresolved_("read allocation duplicates private controller ownership");walk.complete=false;return;}
              const auto invalidated=caches_.at(victim_private_cache_)->invalidate(v.line*64);
              if(!invalidated.hit||invalidated.dirty!=v.private_dirty)throw std::logic_error("read allocation victim identity changed");
              m.dirty_eviction|=p.dirty;
            }
          }
        }
      }
      const auto result = caches_.at(name)->access(line * line_bytes, write);
      if(typed_cold_miss_&&level==0&&walk.device&&write&&!walk.coherence_transaction){
        const auto&m=*typed_cold_miss_;
        if(result.hit||result.slot!=m.slot||result.evicted_line!=m.evicted_line||result.dirty_eviction!=(typed_private_dirty_?typed_private_original_dirty_:m.dirty_eviction))
          throw std::logic_error("cold write allocation changed after exact preview");
      }
      const auto slot = cache_tokens_.at(name) + result.slot;
      auto &generation=cache_generations_.at(name).at(result.slot);
      if(!result.hit) {
        if(generation==UINT64_MAX)throw std::overflow_error("cache observation generation overflow");
        ++generation;
      }
      if(walk.device && !walk.coherence_transaction && level==0) {
        const auto cache=std::distance(caches_.begin(),caches_.find(name))+1;
        walk.device_lookups.push_back(Lookup{std::uint64_t(cache),line,std::uint64_t(slot),generation,
                                           result.hit,result.dirty_eviction,line % model_.document.get<std::uint64_t>("memory.caches."+name+".sets"),line_bytes,engine_.ready(slot)});
      }
      // Cache hits depend on the outstanding fill. Replacement waits for
      // the prior slot's fill and readers through the engine's WAW/WAR rules.
      if (result.hit && !write) walk.reads.insert(slot); else walk.writes.insert(slot);
      feature_("modeled.cache." + name + (result.hit ? ".hits" : ".misses"), 1);
      // The optional legacy fetch approximation owns/suppresses both cache
      // lookup components. V7 instead captures the actual lower lookup and
      // supplies its SourceD response actor, so the two routes cannot compose:
      // subtracting a suppressed lower hit would invent a decomposition.
      const bool refill_candidate=fetch_refill_ && !read_allocations_selected_ &&
          walk.cpu_fetch && level==0 && !write && !result.hit;
      const bool lower_hit=refill_candidate && caches_.at(path[1])->probe(line*line_bytes).hit;
      const bool replace=refill_candidate && lower_hit && !result.dirty_eviction;
      if (refill_candidate && !replace)
        feature_(result.dirty_eviction ? "modeled.fetch_refill.legacy_dirty_eviction" :
                 "modeled.fetch_refill.legacy_lower_miss",1);
      if (!replace && !walk.suppress_cache_price) {
        charge(walk, "memory." + name + (result.hit ? ".hit_cycles" : ".miss_cycles"));
        if(device_read_pipeline_ && walk.device && !write && !walk.coherence_transaction &&
           level==0 && name==device_read_pipeline_->cache) {
          // Replace this lookup's scalar component HERE, before dependent
          // DRAM recursion and the later probe/response max joins. Adding at
          // the SharedEffects consumer would duplicate hidden coherent work.
          const auto extension=device_read_pipeline_->stages-device_read_pipeline_->scalar_lookup;
          if(!add(walk.latency,extension))walk.complete=false;
          feature_("modeled.cache."+name+".source_read_pipeline_applied",1);
          feature_("modeled.cache."+name+".source_read_pipeline_extension_cycles",extension);
        }
        if(typed_write_request_&&device_write_request_pipeline_&&walk.device&&write&&!walk.coherence_transaction&&
           level==0&&name==device_write_request_pipeline_->cache){
          const auto extension=device_write_request_pipeline_->stages-device_write_request_pipeline_->scalar_lookup;
          if(!add(walk.latency,extension))walk.complete=false;
        }
      }
      if (result.dirty_eviction||(typed_private_dirty_&&typed_cold_miss_&&level==0)||(allocation&&allocation->miss.dirty_eviction)) {
        feature_("modeled.writeback_bytes", line_bytes);
        const auto latency=walk.latency,bus=walk.bus;
        const auto previous_writes=(typed_release_writes_||allocation)?walk.writes:std::set<merlin_timing::ValueId>{};
        cache_access(*result.evicted_line * line_bytes, line_bytes, true, path, level + 1, walk);
        if(typed_cold_miss_&&level==0){typed_cold_miss_->release_latency=walk.latency-latency;typed_cold_miss_->release_bus=walk.bus-bus;}
        if(allocation){
          allocation->miss.release_latency=walk.latency-latency;allocation->miss.release_bus=walk.bus-bus;
          for(auto v:walk.writes)if(!previous_writes.count(v))allocation->miss.release_writes.push_back(v);
          for(auto v:allocation->miss.release_writes)walk.writes.erase(v);
        }
        if(typed_release_writes_&&level==0){
          for(auto v:walk.writes)if(!previous_writes.count(v))typed_release_writes_->push_back(v);
          for(auto v:*typed_release_writes_)walk.writes.erase(v);
        }
      }
      if (!result.hit&&!(typed_cold_miss_&&level==0&&!typed_cold_miss_->acquire_block)) {
        const auto prior_suppression=walk.suppress_cache_price;
        walk.suppress_cache_price=prior_suppression || replace;
        const auto latency=walk.latency,bus=walk.bus;
        cache_access(line * line_bytes, line_bytes, false, path, level + 1, walk);
        if(typed_cold_miss_&&level==0){typed_cold_miss_->fill_latency=walk.latency-latency;typed_cold_miss_->fill_bus=walk.bus-bus;}
        if(allocation){allocation->miss.fill_latency=walk.latency-latency;allocation->miss.fill_bus=walk.bus-bus;}
        walk.suppress_cache_price=prior_suppression;
      }
      if(allocation){
        const auto&m=allocation->miss;
        const auto lower=m.release_latency+m.fill_latency,byte_service=m.release_bus+m.fill_bus;
        const auto original=device_read_pipeline_&&walk.device&&!write&&level==0?std::optional<Cycle>{device_read_pipeline_->stages}:
          model_.cycles("memory."+name+(allocation->resident?".hit_cycles":".miss_cycles"));
        if(!original||walk.latency<lower+*original||walk.bus<byte_service||m.fill_latency<m.fill_bus||
           m.release_latency<m.release_bus||m.fill_bus>8||m.release_bus>8){
          unresolved_("read allocation source/lower decomposition unavailable");walk.complete=false;return;
        }
        // The consumer owns each ORIGINAL lower transaction and byte path.
        // Replace the single native LLC lookup here, before later joins, by
        // Directory1+MSHRplan1. SourceD read stages remain a separate actor.
        walk.latency=walk.latency-lower-*original+2;walk.bus-=byte_service;
        walk.read_allocations.push_back(std::move(*allocation));
        feature_("modeled.read_allocations.source_owned",1);
      }
      if (replace) {
        // Conditional demand-only approximation. Preserve the recursive cache
        // classification and slot dependencies, replacing—not adding to—the
        // old two-level scalar hit/miss price. Intermediate milestones remain
        // explicit features; this adapter does not claim modeled frontend/FQ
        // speculation or contention, nor independent timing qualification.
        const auto &service=*fetch_refill_;
        const auto timeline=merlin_timing::plan_cache_response(service.response,
            {service.request_accept_cycles,
             std::vector<std::optional<std::uint64_t>>(service.response.beats,0),0,false});
        if (!timeline.complete || !add(walk.latency,*timeline.lookup_response)) {
          walk.complete=false; unresolved_("provisional fetch response timeline is incomplete");
        } else {
          feature_("modeled.fetch_refill.applied",1);
          feature_("modeled.fetch_refill.first_response_cycles",timeline.accepted_beats.front());
          feature_("modeled.fetch_refill.last_response_cycles",timeline.accepted_beats.back());
          feature_("modeled.fetch_refill.line_visible_cycles",*timeline.line_visible);
          feature_("modeled.fetch_refill.lookup_response_cycles",*timeline.lookup_response);
        }
      }
    }
    if (line == last) break;
  }
}

void MemorySystem::coherent_access(std::uint64_t address, bool write, Walk &walk) {
  // This is an explicit timing policy, not a claim that Spike models a cache
  // coherence protocol. Profiles must opt in to writeback/invalidate snoops.
  if (model_.document.get<std::string>("memory.coherence_policy", "") != "writeback_invalidate") {
    unresolved_("device coherence timing policy is unspecified"); walk.complete = false; return;
  }
  const auto device = paths_.find("device");
  if (device == paths_.end()) { walk.complete = false; return; }
  for (const auto *cpu : {"cpu_data", "cpu_fetch"}) {
    const auto path = paths_.find(cpu);
    if (path == paths_.end()) continue;
    for (std::size_t level = 0; level < path->second.size(); ++level) {
      const auto &name = path->second[level];
      if (std::find(device->second.begin(), device->second.end(), name) != device->second.end()) continue;
      if(noncoherent_private_.count(name))continue;
      const auto probe = caches_.at(name)->invalidate(address);
      if (!probe.hit) continue;
    walk.coherence_probe=true;
      walk.writes.insert(cache_tokens_.at(name) + *probe.slot);
      if (const auto selected = probe_service_.find(name); selected != probe_service_.end()) {
        const auto &service = selected->second;
        // One private probe controller remains occupied through lookup, dirty
        // data response (or clean acknowledgement), and metadata update. The
        // selected stages are source-bound no-backpressure minima, not fitted
        // hit prices or a serialized global memory bandwidth assumption.
        const auto transfer = probe.dirty ? service.dirty_enter + service.data_pipeline +
            lines_.at(name) / service.beat_bytes : 1;
        const auto duration = service.lookup + transfer + service.metadata;
        const auto before=walk.probe_cycles[name];
        if (!add(walk.probe_cycles[name], duration)) walk.complete = false;
        if (write && service.write_response_pipeline) {
          // Inclusive-cache MSHR releases execution at the first C response
          // only for offset zero, otherwise at the last response. Its response
          // pipeline overlaps the remaining C beats and private metadata work.
          const auto first=service.lookup+(probe.dirty ? service.dirty_enter+service.data_pipeline : 0);
          const auto last=first+(probe.dirty ? lines_.at(name)/service.beat_bytes-1 : 0);
          const bool wormhole=address%lines_.at(name)==0;
          auto completion=before;
          if (!add(completion,wormhole?first:last) ||
              !add(completion,*service.write_response_pipeline)) walk.complete=false;
          else walk.probe_responses[name]=std::max(walk.probe_responses[name],completion);
          const auto prefix="modeled.cache."+name+".";
          feature_(prefix+"response_first_cycles",first);
          feature_(prefix+"response_last_cycles",last);
          feature_(prefix+"response_completion_cycles",(wormhole?first:last)+*service.write_response_pipeline);
          feature_(prefix+"response_wormhole",wormhole);
        }
        feature_("modeled.cache." + name + ".coherence_protocol_cycles", duration);
      }
      charge(walk, "memory.snoop_cycles");
      feature_("modeled.coherence_probes", 1);
      if (probe.dirty) {
        const auto bytes = lines_.at(name);
        feature_("modeled.coherence_writeback_bytes", bytes);
        // A dirty CPU writeback and the subsequent device transfer are two
        // transactions even when they touch identical byte addresses. Preserve
        // the existing cache/hazard state while separating their service work.
        const auto prior_transaction = walk.coherence_transaction;
        walk.coherence_transaction = separate_coherence_transactions_;
        cache_access(address / bytes * bytes, bytes, true, path->second, level + 1, walk);
        walk.coherence_transaction = prior_transaction;
      }
    }
  }
}

bool MemorySystem::write_transaction(const WriteTransactionV1&r,WriteTransactionEffectsV1&out){return write_transaction_owned(r,out,nullptr);}
bool MemorySystem::write_transaction(const WriteTransactionV1&r,WriteTransactionEffectsV2&out){out={};return write_transaction_owned(r,out.base,&out.probe);}
bool MemorySystem::write_transaction_owned(const WriteTransactionV1&r,WriteTransactionEffectsV1&out,std::optional<WriteProbeV2>*probe){
  out={};const auto useful=one_beat_write_useful(r);
  if(!useful||r.beat_bytes!=16){out.unavailable="typed write requires one contiguous selected16-byte client beat";return false;}
  if(typed_full_packet_epoch_){out.unavailable="mixed typed SourceD routes require actual full fence";return false;}
  return write_source_owned(r,*useful,out,probe);
}
bool MemorySystem::write_packet(const FullWritePacketV3&r,WriteTransactionEffectsV2&out){
  out={};if(!full_write_packet_valid(r)){out.base.unavailable="typed full packet requires aligned original16/32/64-byte PutFull";return false;}
  if(typed_probe_epoch_&&!typed_full_packet_epoch_){out.base.unavailable="mixed typed SourceD routes require actual full fence";return false;}
  WriteTransactionV1 request;request.address=r.address;request.transaction_bytes=r.transaction_bytes;
  request.beat_bytes=16;request.mask=0xffff;request.accepted=r.accepted;
  const bool admitted=write_source_owned(request,{r.address,r.transaction_bytes},out.base,&out.probe,true);
  if(admitted)typed_full_packet_epoch_=true;
  return admitted;
}
bool MemorySystem::write_transaction(const WriteTransactionV1&r,WriteTransactionEffectsV4&out){
  out={};const auto useful=one_beat_write_useful(r);
  if(!useful||r.beat_bytes!=16){out.resident.base.unavailable="typed write requires one contiguous selected16-byte client beat";return false;}
  if(typed_full_packet_epoch_){out.resident.base.unavailable="mixed typed SourceD routes require actual full fence";return false;}
  return write_source_owned(r,*useful,out.resident.base,&out.resident.probe,false,&out.miss);
}
bool MemorySystem::write_packet(const FullWritePacketV3&r,WriteTransactionEffectsV4&out){
  out={};if(!full_write_packet_valid(r)){out.resident.base.unavailable="typed full packet requires aligned original16/32/64-byte PutFull";return false;}
  if(typed_probe_epoch_&&!typed_full_packet_epoch_){out.resident.base.unavailable="mixed typed SourceD routes require actual full fence";return false;}
  WriteTransactionV1 request;request.address=r.address;request.transaction_bytes=r.transaction_bytes;
  request.beat_bytes=16;request.mask=0xffff;request.accepted=r.accepted;
  const auto admitted=write_source_owned(request,{r.address,r.transaction_bytes},out.resident.base,&out.resident.probe,true,&out.miss);
  if(admitted)typed_full_packet_epoch_=true;
  return admitted;
}
bool MemorySystem::write_transaction(const WriteTransactionV1&r,WriteTransactionEffectsV5&out){
  out={};const auto useful=one_beat_write_useful(r);
  if(!useful||r.beat_bytes!=16){out.resident.base.unavailable="typed write requires one contiguous selected16-byte client beat";return false;}
  if(typed_full_packet_epoch_){out.resident.base.unavailable="mixed typed SourceD routes require actual full fence";return false;}
  std::optional<WriteMissV4>miss;std::vector<merlin_timing::ValueId>writes;
  const auto admitted=write_source_owned(r,*useful,out.resident.base,&out.resident.probe,false,&miss,&writes);
  if(miss){out.miss.emplace();static_cast<WriteMissV4&>(*out.miss)=*miss;out.miss->release_writes=std::move(writes);}return admitted;
}
bool MemorySystem::write_packet(const FullWritePacketV3&r,WriteTransactionEffectsV5&out){
  out={};if(!full_write_packet_valid(r)){out.resident.base.unavailable="typed full packet requires aligned original16/32/64-byte PutFull";return false;}
  if(typed_probe_epoch_&&!typed_full_packet_epoch_){out.resident.base.unavailable="mixed typed SourceD routes require actual full fence";return false;}
  WriteTransactionV1 request;request.address=r.address;request.transaction_bytes=r.transaction_bytes;request.beat_bytes=16;request.mask=0xffff;request.accepted=r.accepted;
  std::optional<WriteMissV4>miss;std::vector<merlin_timing::ValueId>writes;
  const auto admitted=write_source_owned(request,{r.address,r.transaction_bytes},out.resident.base,&out.resident.probe,true,&miss,&writes);
  if(miss){out.miss.emplace();static_cast<WriteMissV4&>(*out.miss)=*miss;out.miss->release_writes=std::move(writes);}if(admitted)typed_full_packet_epoch_=true;return admitted;
}
void MemorySystem::cpu_data_completed(std::optional<Cycle>ready,bool atomic){
  cpu_atomic_seen_|=atomic;
  if(!ready){cpu_data_ready_.reset();return;}
  if(cpu_data_miss_){if(*ready>UINT64_MAX-8){cpu_data_ready_.reset();return;}*ready+=8;}
  if(cpu_data_ready_)cpu_data_ready_=std::max(*cpu_data_ready_,*ready);
}
bool MemorySystem::victim_client_released(const VictimProbeV6&v,Cycle at){
  const auto key=std::make_pair(v.private_slot,v.generation);const auto it=victim_clients_.find(key);
  if(it==victim_clients_.end()||at<it->second)return false;
  victim_clients_.erase(it);if(cpu_data_ready_)cpu_data_ready_=std::max(*cpu_data_ready_,at);return true;
}
bool MemorySystem::write_transaction(const WriteTransactionV1&r,WriteTransactionEffectsV6&out){
  out={};const auto useful=one_beat_write_useful(r);
  if(!useful||r.beat_bytes!=16){out.resident.base.unavailable="typed write requires selected16-byte client beat";return false;}
  if(typed_full_packet_epoch_){out.resident.base.unavailable="mixed typed SourceD routes require actual full fence";return false;}
  std::optional<WriteMissV4>miss;std::vector<merlin_timing::ValueId>writes;
  const auto ok=write_source_owned(r,*useful,out.resident.base,&out.resident.probe,false,&miss,&writes,&out.victim);
  if(miss){out.miss.emplace();static_cast<WriteMissV4&>(*out.miss)=*miss;out.miss->release_writes=std::move(writes);}return ok;
}
bool MemorySystem::write_packet(const FullWritePacketV3&r,WriteTransactionEffectsV6&out){
  out={};if(!full_write_packet_valid(r)){out.resident.base.unavailable="typed full packet requires aligned original16/32/64-byte PutFull";return false;}
  if(typed_probe_epoch_&&!typed_full_packet_epoch_){out.resident.base.unavailable="mixed typed SourceD routes require actual full fence";return false;}
  WriteTransactionV1 request;request.address=r.address;request.transaction_bytes=r.transaction_bytes;request.beat_bytes=16;request.mask=0xffff;request.accepted=r.accepted;
  std::optional<WriteMissV4>miss;std::vector<merlin_timing::ValueId>writes;
  const auto ok=write_source_owned(request,{r.address,r.transaction_bytes},out.resident.base,&out.resident.probe,true,&miss,&writes,&out.victim);
  if(miss){out.miss.emplace();static_cast<WriteMissV4&>(*out.miss)=*miss;out.miss->release_writes=std::move(writes);}if(ok)typed_full_packet_epoch_=true;return ok;
}
bool MemorySystem::write_source_owned(const WriteTransactionV1&r,const WriteUsefulBytes&useful,WriteTransactionEffectsV1&out,std::optional<WriteProbeV2>*probe,bool full_packet,std::optional<WriteMissV4>*miss,std::vector<merlin_timing::ValueId>*release_writes,std::optional<VictimProbeV6>*victim){
  out={};
  const auto deny=[&](const char*why){out.unavailable=why;return false;};
  if(!device_write_request_pipeline_)return deny("typed write Directory/MSHR owner not selected");
  const auto &name=device_write_request_pipeline_->cache;
  if(r.address/lines_.at(name)!=(r.address+r.transaction_bytes-1)/lines_.at(name))return deny("typed write crosses cache line");
  const auto preview=caches_.at(name)->preview_access(r.address);
  const bool cold=!preview.hit;
  if(cold&&(!miss||!typed_cold_write_selected_))return deny("typed write requires resident source-ready cache line");
  const auto slot=cache_tokens_.at(name)+preview.slot;
  const auto prior=engine_.ready(slot);
  // A later full packet may depend on an earlier admitted typed packet's
  // deferred publication. Its owning event still waits that exact slot token;
  // this is not permission to consume an unrelated pending cache fill.
  if((!prior||*prior>r.accepted)&&!((full_packet||miss)&&typed_full_packet_slots_.count(slot)))return deny("typed write cache line publication is pending");
  if(cold){
    if(preview.dirty_eviction&&(!release_writes||!typed_dirty_victim_selected_))return deny("cold write dirty victim outer-A/ReleaseAck timeline unsupported");
    if(!model_.cycles("memory.dram_latency_cycles")||!model_.cycles("memory.dram_per_byte_cycles",64)||!model_.resource("memory.shared"))
      return deny("cold write lower memory service is unspecified");
    // A tag eviction with a private client needs a shoot-down, not the
    // resident target-line probe law. Refuse before any RNG/tag mutation.
    for(const auto*cpu:{"cpu_data","cpu_fetch"})if(const auto path=paths_.find(cpu);path!=paths_.end())
      for(const auto&level:path->second)if(level!=name&&!noncoherent_private_.count(level)){
        const auto target_hit=caches_.at(level)->probe(r.address).hit;
        const auto victim_hit=preview.evicted_line&&caches_.at(level)->probe(*preview.evicted_line*64).hit;
        if(target_hit||victim_hit){
          if(target_hit||!victim||!typed_private_victim_selected_||level!=victim_private_cache_||*victim||
             !cpu_data_ready_||cpu_atomic_seen_||!typed_dirty_victim_selected_){
            feature_(std::string("modeled.typed_write.cold.denied_private_")+(target_hit?"target.":"victim.")+level,1);
            return deny("cold write allocation requires unsupported private-client victim shoot-down");
          }
          const auto p=caches_.at(level)->probe(*preview.evicted_line*64);
          const auto generation=cache_generations_.at(name).at(preview.slot);
          if(!generation)return deny("victim probe original Directory generation unavailable");
          const auto ways=model_.document.get<std::uint64_t>("memory.caches."+name+".ways");
          *victim=VictimProbeV6{*preview.evicted_line,*preview.evicted_line%model_.document.get<std::uint64_t>("memory.caches."+name+".sets"),preview.slot%ways,generation,
            cache_tokens_.at(level)+*p.slot,preview.dirty_eviction,p.dirty,*cpu_data_ready_,victim_source_identity_};
        }
      }
    miss->emplace();auto&m=**miss;m.line=r.address/64;
    m.set=m.line%model_.document.get<std::uint64_t>("memory.caches."+name+".sets");
    m.slot=preview.slot;m.generation=cache_generations_.at(name).at(preview.slot)+1;
    m.evicted_line=preview.evicted_line;m.dirty_eviction=preview.dirty_eviction||(victim&&*victim&&(**victim).private_dirty);
    m.acquire_block=!(full_packet&&r.transaction_bytes==64&&r.address%64==0);
  }
  std::set<std::string>private_hits;
  for(const auto*cpu:{"cpu_data","cpu_fetch"}){
    const auto path=paths_.find(cpu);if(path==paths_.end())continue;
    for(const auto&level:path->second){
      if(level==name||noncoherent_private_.count(level))continue;
      const auto private_hit=caches_.at(level)->probe(r.address);
      if(!private_hit.hit)continue;
      if(!probe||!typed_single_private_probe_||!private_hits.insert(level).second||private_hits.size()>1)
        return deny("typed write private-cache probe service not source closed");
      const auto service=probe_service_.find(level);
      if(service==probe_service_.end()||lines_.at(level)!=64||service->second.beat_bytes!=16||
         service->second.lookup!=2||service->second.dirty_enter!=1||service->second.data_pipeline!=2||service->second.metadata!=1||
         paths_.at(cpu)!=std::vector<std::string>{level,name})
        return deny("typed write private probe differs from selected one-level source path");
      const auto &s=service->second;
      *probe=WriteProbeV2{s.resource,s.lookup,s.dirty_enter,s.data_pipeline,s.metadata,64,16,private_hit.dirty};
    }
  }
  // This classification touches ONLY actual useful bytes. In particular a
  // one-column write never becomes a sixteen-byte memory write/taint reset.
  if(victim&&*victim){
    const auto&v=**victim;const auto p=caches_.at(victim_private_cache_)->invalidate(v.line*64);
    if(!p.hit||p.dirty!=v.private_dirty)return deny("victim private identity changed before admitted probe");
    if(!victim_clients_.emplace(std::make_pair(v.private_slot,v.generation),std::max(r.accepted,v.client_ready)).second)
      return deny("victim private controller identity already owned");
  }
  typed_private_dirty_=victim&&*victim&&(**victim).private_dirty;
  typed_private_original_dirty_=victim&&*victim&&(**victim).llc_dirty;
  typed_write_request_=true;
  typed_cold_miss_=cold?&**miss:nullptr;
  typed_release_writes_=cold?release_writes:nullptr;
  try{out.source_request=access({{useful.address,useful.bytes,true}},"device");}
  catch(...){typed_write_request_=false;typed_cold_miss_=nullptr;typed_release_writes_=nullptr;typed_private_dirty_=false;throw;}
  typed_write_request_=false;typed_cold_miss_=nullptr;typed_release_writes_=nullptr;typed_private_dirty_=false;
  if(!out.source_request.latency)return deny("typed write source request has unresolved memory ownership");
  if(cold){
    // These lower transactions are now owned by distinct SourceC/SourceA
    // actors. Keep ALL original cache/DRAM dependency values, but do not also
    // charge their latency/byte service in Directory/MSHR request admission.
    const auto&m=**miss;
    if(*out.source_request.latency!=device_write_request_pipeline_->stages+m.fill_latency+m.release_latency)
      return deny("cold write source/lower service decomposition is not exact");
    out.source_request.latency=device_write_request_pipeline_->stages;
    const auto shared=*model_.resource("memory.shared");auto&demands=out.source_request.demands;
    demands.erase(std::remove_if(demands.begin(),demands.end(),[&](const auto&d){return d.resource==shared;}),demands.end());
    feature_(m.acquire_block?"modeled.typed_write.cold.acquire_block":"modeled.typed_write.cold.permission_only",1);
    if(m.evicted_line)feature_(m.dirty_eviction?"modeled.typed_write.cold.dirty_victims":"modeled.typed_write.cold.clean_victims",1);
  }
  if(probe&&*probe){
    // This source law REPLACES the old aggregate snoop/cache-writeback scalar
    // path. Incoming ProbeAckData is SinkC's known MSHR CAM/write path, not a
    // second demand Directory lookup. The consumer separately schedules the
    // exact selected probe resource and first/last-C response handoff.
    out.source_request.latency=device_write_request_pipeline_->stages;
    auto&demands=out.source_request.demands;
    demands.erase(std::remove_if(demands.begin(),demands.end(),[&](const auto&d){return d.resource==(*probe)->resource;}),demands.end());
  }
  typed_probe_epoch_=true;
  if(full_packet||miss)typed_full_packet_slots_.insert(slot);
  out.sram_read_required=r.mask!=0xffff;
  feature_("modeled.typed_write.client_transaction_bytes",r.transaction_bytes);
  feature_("modeled.typed_write.useful_bytes",useful.bytes);
  return true;
}

SharedEffects MemorySystem::access(const std::vector<MemoryEffect> &effects, const std::string &path) {
  building_.clear();last_read_allocations_={};
  if(observation_sequence_==UINT64_MAX)throw std::overflow_error("memory observation identity overflow");
  ++observation_sequence_;last_observation_={};
  if(path=="cpu_data"&&!effects.empty()){
    cpu_data_miss_=false;const auto p=paths_.find(path);
    if(p!=paths_.end()&&!p->second.empty())for(const auto&e:effects)if(e.bytes&&!e.immutable)
      cpu_data_miss_|=!caches_.at(p->second.front())->probe(e.address).hit;
  }
  Walk walk;walk.device=path=="device";
  walk.cpu_fetch = path == "cpu_fetch";
  walk.complete = granule_ != 0;
  std::map<std::uint64_t, bool> regions;
  for (const auto &effect : effects) {
    if (!effect.bytes) continue;
    if (effect.immutable) {
      if (fetch_refill_ && walk.cpu_fetch) feature_("modeled.fetch_refill.immutable",1);
      if (effect.write) walk.complete = false;
      else {
        charge(walk, "memory.immutable_access_cycles");
        feature_("modeled.immutable_requested_bytes", effect.bytes);
      }
      continue;
    }
    feature_(path + (effect.write ? ".requested_write_bytes" : ".requested_read_bytes"), effect.bytes);
    if (!granule_ || effect.bytes - 1 > std::numeric_limits<std::uint64_t>::max() - effect.address) {
      walk.complete = false; continue;
    }
    const auto last = (effect.address + effect.bytes - 1) / granule_;
    for (auto region = effect.address / granule_;; ++region) {
      if (regions.size() >= model_.max_memory_entries && !regions.count(region)) {
        unresolved_("single memory event exceeds dependency capacity"); walk.complete = false; break;
      }
      regions[region] = regions[region] || effect.write;
      if (region == last) break;
    }
  }
  const auto selected = paths_.find(path);
  if (!regions.empty() && selected == paths_.end()) {
    unresolved_("memory path is unspecified: " + path); walk.complete = false;
  }
  // Hazard tracking uses coherence granules. Cache timing independently visits
  // every line intersected by each exact byte interval (never a rounded granule).
  for (const auto &region : regions) {
    if (const auto id = token(region.first))
      (region.second ? walk.writes : walk.reads).insert(*id);
    else walk.complete = false;
  }
  if (selected != paths_.end()) {
    for (const auto &effect : effects) {
      if (effect.immutable || !effect.bytes || effect.bytes - 1 > std::numeric_limits<std::uint64_t>::max() - effect.address) continue;
      std::uint64_t smallest = granule_;
      for (const auto &entry : lines_) smallest = smallest ? std::min(smallest, entry.second) : entry.second;
      if (!smallest || (effect.bytes - 1) / smallest + 1 > model_.max_memory_entries) {
        unresolved_("memory transfer exceeds bounded transaction budget"); walk.complete = false; continue;
      }
      if (path == "device") {
        // Each private-cache line is probed, including lines finer than the
        // logical coherence granule. Invalidation makes duplicate probes cheap.
        std::uint64_t step = granule_;
        for (const auto &entry : lines_) step = step ? std::min(step, entry.second) : entry.second;
        if (!step) { walk.complete = false; continue; }
        const auto last = (effect.address + effect.bytes - 1) / step;
        for (auto line = effect.address / step;; ++line) {
          coherent_access(std::max(effect.address,line * step), effect.write, walk);
          if (line == last) break;
        }
      }
      cache_access(effect.address, effect.bytes, effect.write, selected->second, 0, walk);
    }
  }
  walk.effects.reads.assign(walk.reads.begin(), walk.reads.end());
  walk.effects.writes.assign(walk.writes.begin(), walk.writes.end());
  for (const auto &entry : walk.boundary_bytes) {
    const auto price = "memory." + entry.first + ".per_byte_cycles";
    const auto cost = model_.cycles(price, entry.second);
    const auto resource = model_.resource(model_.document.get<std::string>(
        "memory.caches." + entry.first + ".byte_service.resource"));
    if (!cost || !resource || !add(walk.latency, *cost)) walk.complete = false;
    else walk.effects.demands.push_back({*resource, 1, *cost});
    feature_("modeled.cache." + entry.first + ".boundary_bytes", entry.second);
  }
  for (const auto &entry : walk.probe_cycles) {
    const auto &service = probe_service_.at(entry.first);
    walk.effects.demands.push_back({service.resource, 1, entry.second});
    // Scalar cache/snoop costs already account for some control work. Retain
    // them and enforce this independent protocol floor instead of adding the
    // same stages twice. Per-line cache/DMA overlap remains approximate.
    walk.latency = std::max(walk.latency, entry.second);
  }
  // Completion and controller release are different milestones. SharedEffects
  // already supports latency independent of occupancy; preserve its ABI and
  // existing hazards, without charging this pipeline as serialized probe work.
  for (const auto &entry:walk.probe_responses)
    walk.latency=std::max(walk.latency,entry.second);
  if (walk.bus) {
    const auto resource = model_.resource("memory.shared");
    if (resource) walk.effects.demands.push_back({*resource, 1, walk.bus});
    else walk.complete = false;
  }
  if (walk.complete) walk.effects.latency = walk.latency;
  else unresolved_("memory timing has unresolved prices, resources or semantics");
  if(walk.device && effects.size()==1 && !effects.front().write &&
      !effects.front().immutable && effects.front().bytes && walk.complete &&
      walk.device_lookups.size()==1) {
    last_observation_.address=effects.front().address;
    last_observation_.bytes=effects.front().bytes;
    last_observation_.sequence=observation_sequence_;
    last_observation_.lookup=walk.device_lookups.front();last_observation_.valid=true;
    last_observation_.no_probe=!walk.coherence_probe && !walk.device_lookups.front().dirty_eviction;
  }
  if(walk.shared_lookup) {
    const bool source_owned_read=read_allocations_selected_&&!walk.read_allocations.empty()&&!walk.coherence_probe&&walk.complete;
    if(typed_probe_epoch_&&(!walk.device||!typed_write_request_)&&!source_owned_read)
      unresolved_("typed masked-write source epoch intersects unsupported external shared-cache service before full fence");
    if(source_observations_.size()<64)
      source_observations_.push_back({observation_sequence_,walk.device,
          last_observation_.valid && last_observation_.no_probe && last_observation_.lookup->hit});
    else source_history_overflow_=true;
    if(!walk.device)for(const auto &epoch:source_epochs_) {
      const auto frontier=engine_.issue_frontier();
      if(!frontier || *frontier<epoch.final_response)
        unresolved_("resident read source epoch intersects a later posted CPU shared-cache arrival");
    }
  }
  if(!walk.read_allocations.empty()){
    last_read_allocations_.allocations=std::move(walk.read_allocations);
    last_read_allocations_.source_request=walk.effects;
    if(!walk.complete)last_read_allocations_.unavailable="captured read allocation has incomplete native source ownership";
  }
  return walk.effects;
}
bool MemorySystem::take_read_allocations(ReadAllocationEffectsV7&out){
  if(last_read_allocations_.allocations.empty())return false;
  out=std::move(last_read_allocations_);last_read_allocations_={};return true;
}
bool MemorySystem::last_observation(const merlin_timing::MemoryRequestIdentityV1 &request,
                                  merlin_timing::MemoryMilestonesV2 &out) const {
  if(!last_observation_.valid || !request.request || !request.return_generation ||
      request.address!=last_observation_.address || request.bytes!=last_observation_.bytes ||
      !last_observation_.lookup)return false;
  const auto &lookup=*last_observation_.lookup;
  out={};out.request=request;
  out.fill=merlin_timing::MemoryFillIdentityV1{lookup.cache,lookup.line,lookup.slot,lookup.generation};
  const auto visible=lookup.prior_fill_ready;
  out.line_pending_at_lookup=!visible || *visible>request.accepted;
  out.memory_observation=last_observation_.sequence;
  out.lookup=merlin_timing::MemoryLookupSnapshotV1{lookup.set,lookup.line_bytes,
      lookup.hit && last_observation_.no_probe,lookup.prior_fill_ready};
  for(const auto &epoch:source_epochs_)
    if(last_observation_.sequence>epoch.last_observation && request.accepted<epoch.final_response)
      unresolved_("resident read source epoch intersects a later posted device shared-cache arrival");
  // This is a cache-observation/fill-token identity, NOT an MSHR. SharedEffects
  // owns an aggregate payload bound; no source ID, first response or cache-line
  // visibility can be derived by splitting that number. Query is read-only.
  out.unavailable="source MSHR/set-secondary allocation, shared A/D/E/directory RR actions and first/last refill milestones unavailable";
  return true;
}
bool MemorySystem::admit_response_epoch(const merlin_timing::MemoryResponseEpochV1 &epoch) {
  if(epoch.version!=1 || epoch.size!=sizeof(epoch) || !epoch.first_observation ||
      epoch.last_observation<epoch.first_observation || !epoch.requests || epoch.requests>16 ||
      epoch.final_response<epoch.begin || !source_fence_clock_ || *source_fence_clock_>epoch.begin ||
      epoch.first_observation<=source_fence_sequence_ || epoch.last_observation!=observation_sequence_ ||
      source_history_overflow_ || source_observations_.size()!=epoch.requests)return false;
  for(const auto &record:source_observations_)
    if(record.sequence<epoch.first_observation || record.sequence>epoch.last_observation ||
        !record.device || !record.resident)return false;
  for(const auto &old:source_epochs_)if(old.final_response>epoch.begin)return false;
  source_epochs_.push_back(epoch);feature_("modeled.source_resident_read_epochs",1);return true;
}
void MemorySystem::source_full_fence(merlin_timing::Cycle at,bool close_typed_write_epoch) {
  if(close_typed_write_epoch){typed_probe_epoch_=false;typed_full_packet_epoch_=false;typed_full_packet_slots_.clear();}
  for(const auto &epoch:source_epochs_) {
    if(at<epoch.final_response)unresolved_("source epoch has unclosed final response at actual full fence");
    else feature_("modeled.source_resident_read_epochs_closed",1);
  }
  source_epochs_.clear();source_observations_.clear();source_history_overflow_=false;
  source_fence_sequence_=observation_sequence_;source_fence_clock_=at;
}
void MemorySystem::source_report() {
  if(typed_probe_epoch_)unresolved_("typed masked-write source epoch lacks actual closing full fence");
  if(!source_epochs_.empty())unresolved_("resident read source epoch lacks actual closing full fence");
}
void MemorySystem::instruction_fence() {
  const auto path = paths_.find("cpu_fetch");
  if (path == paths_.end() || path->second.empty()) {
    unresolved_("instruction cache fence path is unspecified"); return;
  }
  for (const auto *other : {"cpu_data", "device"}) {
    const auto selected = paths_.find(other);
    if (selected != paths_.end() && std::find(selected->second.begin(), selected->second.end(), path->second.front()) != selected->second.end()) {
      unresolved_("instruction fence requires an explicitly supported private instruction cache"); return;
    }
  }
  // Caller has drained the engine before invalidation.
  caches_.at(path->second.front())->clear();
}
} // namespace spike_timing
