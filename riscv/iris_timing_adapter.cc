#include "iris_timing_adapter.h"
#include <fstream>
#include <cmath>
#include <cstring>
#include <iostream>
#include <cstdlib>
#include <iomanip>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>

namespace {
uint64_t number(const std::string& text) {
  size_t used = 0;
  if (text.empty() || text[0] == '-') throw std::runtime_error("negative/empty timing parameter");
  uint64_t value = std::stoull(text, &used, 0);
  if (used != text.size() || value == std::numeric_limits<uint64_t>::max())
    throw std::runtime_error("invalid timing parameter: " + text);
  return value;
}
}

iris_timing_adapter::Profile iris_timing_adapter::Profile::load(const std::string& path, size_t count) {
  std::ifstream input(path);
  if (!input) throw std::runtime_error("cannot open timing fixture: " + path);
  Profile p; p.harts.resize(count);
  std::string line; unsigned lineno = 0;
  std::set<std::string> singleton, resource_names;
  bool purpose = false;
  while (std::getline(input, line)) {
    ++lineno; line = line.substr(0, line.find('#'));
    std::istringstream stream(line); std::vector<std::string> f;
    for (std::string token; stream >> token;) f.push_back(token);
    if (f.empty()) continue;
    try {
      const auto& key = f[0];
      if (key == "purpose" && f.size() == 2) {
        if (!singleton.insert(key).second || f[1] != "uncalibrated-integration-fixture")
          throw std::runtime_error("only explicit uncalibrated integration fixtures are accepted");
        purpose = true;
      } else if(key=="empirical_profile"&&f.size()==4){
        if(!singleton.insert(key).second||f[1]!="experimental-effective-services"||(f[3]!="bounded"&&f[3]!="full"))throw std::runtime_error("explicit empirical profile/history required");p.empirical=true;p.empirical_identity=f[2];p.keep_history=f[3]=="full";
       } else if(key=="empirical_instruction_service"&&f.size()==8){
        const auto hart=number(f[1]);std::array<double,3>v{};for(unsigned i=0;i<3;++i){size_t used=0;v[i]=std::stod(f[2+i],&used);if(used!=f[2+i].size()||!std::isfinite(v[i])||v[i]<0)throw std::runtime_error("invalid empirical instruction coefficient");}
        if(hart>=count||v[2]<1||f[7]!="core_cycles")throw std::runtime_error("invalid empirical instruction service");p.empirical_instruction_rules.push_back({unsigned(hart),v[0],v[1],v[2],f[5],f[6]});
      } else if(key=="empirical_branch_service"&&f.size()==6){
        const auto hart=number(f[1]);size_t used=0;const double penalty=std::stod(f[2],&used);if(hart>=count||used!=f[2].size()||!std::isfinite(penalty)||penalty<0||f[5]!="core_cycles")throw std::runtime_error("invalid empirical branch service");p.empirical_branch_rules.push_back({unsigned(hart),penalty,f[3],f[4]});
      } else if(key=="empirical_rocket_packets"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="source-IBuf-demand-4B-v1")throw std::runtime_error("unsupported empirical Rocket packet model");p.empirical_rocket_packets=true;
      } else if(key=="empirical_vme_work"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="source-shape-subtiles-v1")throw std::runtime_error("unsupported empirical VME work basis");p.empirical_vme_shape_work=true;
      } else if(key=="empirical_vector_store_capture"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="guard-Mbare-VSE32-COM-selfcheck-v1")throw std::runtime_error("unsupported vector-store capture guard");p.empirical_vector_store_capture=true;
      } else if(key=="empirical_scalar_fadd"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="source-HSD-pipeline-v1")throw std::runtime_error("unsupported finite scalar FADD model");p.empirical_scalar_fadd=true;
      } else if(key=="empirical_dcache_random"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="shuttle-miss-allocation-proxy-v1")throw std::runtime_error("unsupported empirical Dcache random policy");p.empirical_shuttle_random=true;
      } else if(key=="empirical_scalar_outer_response"&&f.size()==6){
        const auto hart=number(f[1]);size_t used=0;const double coefficient=std::stod(f[2],&used);
        if(hart>=count||used!=f[2].size()||!std::isfinite(coefficient)||coefficient<0||f[5]!="core_cycles"||f[4].size()!=64||f[4].find_first_not_of("0123456789abcdef")!=std::string::npos)throw std::runtime_error("invalid scalar OUTER response service");
        for(const auto&r:p.empirical_scalar_outer_rules)if(r.hart==hart)throw std::runtime_error("duplicate scalar OUTER response service");
        p.empirical_scalar_outer_rules.push_back({unsigned(hart),coefficient,f[3],f[4]});
      } else if(key=="empirical_scalar_l2_hit"&&f.size()==6){
        const auto hart=number(f[1]);size_t used=0;const double coefficient=std::stod(f[2],&used);
        if(hart>=count||used!=f[2].size()||!std::isfinite(coefficient)||coefficient<0||f[5]!="core_cycles"||f[4].size()!=64||f[4].find_first_not_of("0123456789abcdef")!=std::string::npos)throw std::runtime_error("invalid scalar L2-hit service");
        for(const auto&r:p.empirical_scalar_l2_hit_rules)if(r.hart==hart)throw std::runtime_error("duplicate scalar L2-hit service");
        p.empirical_scalar_l2_hit_rules.push_back({unsigned(hart),coefficient,f[3],f[4]});
      } else if(key=="empirical_read_overlap"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="response-ready-L1-read-only-v2")throw std::runtime_error("unsupported empirical read overlap");p.empirical_read_overlap=true;
      } else if(key=="empirical_store_front"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="owned-dirty-L1-COM-v1")throw std::runtime_error("unsupported empirical store front");p.empirical_store_front=true;
      } else if(key=="empirical_load_front"&&f.size()==2){
        if(!singleton.insert(key).second||(f[1]!="dram-L1-hit-latched-response-v1"&&f[1]!="dram-L1-hit-Shuttle-COM-forward-v2"))throw std::runtime_error("unsupported empirical load front");p.empirical_load_front=true;p.empirical_shuttle_load_com_forward=f[1]=="dram-L1-hit-Shuttle-COM-forward-v2";
      } else if(key=="empirical_icache"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="address-tags-refill-proxy-v1")throw std::runtime_error("unsupported empirical instruction-cache profile");p.empirical_icache=true;
      } else if(key=="empirical_opu_entry"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="source-VDQ4-IQ3-entry-MM-TK1-COMplus1-v2")throw std::runtime_error("unsupported finite source OPU entry overlap");p.empirical_opu_entry=true;
      } else if(key=="empirical_async"&&f.size()==2){
        if(!singleton.insert(key).second||(f[1]!="integer-vme-nonmemory-v1"&&f[1]!="integer-vme-nonmemory-v2"&&f[1]!="integer-vme-fadd-nonmemory-v3"))throw std::runtime_error("unsupported empirical async capability");p.empirical_async=true;p.empirical_async_two_owner=f[1]!="integer-vme-nonmemory-v1";p.empirical_async_fadd=f[1]=="integer-vme-fadd-nonmemory-v3";
      } else if(key=="empirical_cache_service"&&f.size()==11){
        const auto hart=number(f[1]);std::array<double,6>v{};for(unsigned i=0;i<6;++i){size_t used=0;v[i]=std::stod(f[2+i],&used);if(used!=f[2+i].size()||!std::isfinite(v[i])||v[i]<0)throw std::runtime_error("invalid empirical cache coefficient");}
        if(hart>=count||v[4]<1||f[10]!="core_cycles")throw std::runtime_error("invalid empirical cache service");
        p.empirical_cache_rules.push_back({unsigned(hart),v[0],v[1],v[2],v[3],v[4],v[5],f[8],f[9]});
      } else if(key=="empirical_family"&&f.size()==10){
        const auto hart=number(f[1]);size_t used=0;const double setup=std::stod(f[4],&used);if(used!=f[4].size())throw std::runtime_error("invalid empirical setup");const double work=std::stod(f[5],&used);if(used!=f[5].size())throw std::runtime_error("invalid empirical work");
        if(hart>=count||!std::isfinite(setup)||!std::isfinite(work)||setup<0||work<0||!number(f[6])||f[9]!="core_cycles")throw std::runtime_error("invalid empirical family");
        p.empirical_rules.push_back({unsigned(hart),f[2],f[3],f[7],f[8],setup,work,number(f[6])});
      } else if(key=="counter_policy"  && f.size()==2) {
        if(!singleton.insert(key).second || f[1]!="source-ungated-stall")throw std::runtime_error("unsupported source counter policy");
        p.source_counter_clock=true;
      } else if(key=="saturn_live" && f.size()==3) {
        if(!singleton.insert(key).second||f[1]!="finite-integer-K1-hart0")throw std::runtime_error("only explicit finite integer K1 Saturn scope is available");p.saturn_live=true;p.saturn_manifest=f[2];
      } else if(key=="rocket_scalar_memory" && f.size()==2) {
        if(!singleton.insert(key).second||f[1]!="source-cache-M-mode")throw std::runtime_error("unsupported Rocket scalar memory path");p.rocket_scalar_memory=true;
      } else if(key=="rocket_serial" && f.size()==14) {
        if(!singleton.insert(key).second||f[1]!="source-path-explicit-functional-AXI-fixture"||number(f[2])!=2||number(f[3])!=1||number(f[4])!=10||f[13]!="virtual_phase_units")throw std::runtime_error("explicit source Serial calendar 2/1/10 and functional fixture required");
        for(unsigned field=5;field<=9;++field)if(number(f[field])>UINT32_MAX)throw std::runtime_error("source Serial parameter exceeds physical 32-bit width");
        p.rocket_serial=true;p.rocket_memory_fabric=true;p.fabric_uncore_divider=2;p.serial_reset_phases=number(f[5]);
        p.serial_latency={unsigned(number(f[6])),unsigned(number(f[7])),unsigned(number(f[8])),unsigned(number(f[9]))};p.fabric_initial_elf=f[10];p.serial_system_identity=f[11];p.serial_latency_identity=f[12];
        if(p.serial_reset_phases<10||p.serial_reset_phases>10000||p.serial_reset_phases%10)throw std::runtime_error("explicit aligned component-reset reference phases required");
      } else if(key=="serial_cbus_fixture" && f.size()==4) {
        if(!singleton.insert(key).second)throw std::runtime_error("duplicate CBUS fixture");p.fabric_first_edges=number(f[1]);p.fabric_gap_edges=number(f[2]);p.fabric_service_source=f[3];
        if(!p.fabric_first_edges||!p.fabric_gap_edges||p.fabric_service_source!="explicit-synthetic-CBUS-ROM-CLINT-service")throw std::runtime_error("explicit CBUS fixture required");
      } else if(key=="rocket_fabric" && f.size()==8) {
        if(!singleton.insert(key).second || f[1]!="explicit-synthetic-external-service")throw std::runtime_error("unsupported source fabric service; explicit fixture required");
        p.rocket_memory_fabric=true;p.fabric_uncore_divider=number(f[2]);p.fabric_first_edges=number(f[3]);p.fabric_gap_edges=number(f[4]);p.fabric_initial_elf=f[5];p.fabric_service_source=f[6];
        if(!p.fabric_uncore_divider||!p.fabric_first_edges||!p.fabric_gap_edges||f[7]!="uncore_edges")throw std::runtime_error("explicit positive source fabric fixture periods and units required");
      } else if(key=="rocket_frontend" && f.size()==2) {
        if(!singleton.insert(key).second || f[1]!="saved-rtl-M-mode")throw std::runtime_error("unsupported Rocket source frontend");
        p.saved_rocket_frontend=true;
      } else if (key == "shuttle_frontend" && f.size()==4) {
        if(!singleton.insert(key).second || f[1]!="source-C++-M-mode")throw std::runtime_error("this isolated tree requires source-C++-M-mode frontend");
        p.saved_shuttle_frontend=true;p.frontend_seed=number(f[2]);p.frontend_reset_edges=number(f[3]);
        if(!p.frontend_seed || p.frontend_seed>INT32_MAX || p.frontend_reset_edges<2 || p.frontend_reset_edges>1024)throw std::runtime_error("explicit source reset edges required");
      } else if(key=="icache_service" && f.size()==5) {
        if(!singleton.insert(key).second || (f[1]!="synthetic"&&f[1]!="empirical-shared-L2"))throw std::runtime_error("explicit synthetic or empirical-shared-L2 frontend service required");
        p.synthetic_icache_first=number(f[2]);p.synthetic_icache_gap=number(f[3]);p.icache_service_source=f[4];
        if(!p.synthetic_icache_first || !p.synthetic_icache_gap)throw std::runtime_error("positive synthetic service periods required");
      } else if (key == "pipeline_values" && f.size() == 2) {
        if(f[1]!="private-pure-integer")throw std::runtime_error("unsupported private forwarded-value scope");
        p.private_forwarded_values=true;
      } else if (key == "shuttle_pipeline" && f.size() == 2) {
        if (!singleton.insert(key).second || (f[1] != "pure-integer-sequential-frontend" && f[1] != "pure-integer-rvc-sequential-frontend" && f[1] != "pure-integer-rvc-counter-sequential-frontend"))
          throw std::runtime_error("unsupported experimental Shuttle pipeline fixture");
        p.shuttle_pure_pipeline = true;
        p.shuttle_rvc_pipeline = f[1] != "pure-integer-sequential-frontend";
        p.shuttle_counter_pipeline = f[1] == "pure-integer-rvc-counter-sequential-frontend";
      } else if (key=="rocket_pipeline" && f.size()==2) {
        if (!singleton.insert(key).second || f[1]!="pure-integer-rvc-counter-sequential-frontend")
          throw std::runtime_error("unsupported experimental Rocket pipeline fixture");
        p.rocket_pure_pipeline=true;
      } else if (key == "source" && f.size() == 2) {
        if (!singleton.insert(key).second) throw std::runtime_error("duplicate source");
        p.source = f[1];
      } else if ((key == "base_hz" || key == "rtc_divider" || key == "max_cycles" || key == "trap_cycles") && f.size() == 2) {
        if (!singleton.insert(key).second) throw std::runtime_error("duplicate parameter");
        auto value = number(f[1]);
        if (!value) throw std::runtime_error("positive parameter required");
        if (key == "base_hz") p.base_hz = value;
        else if (key == "rtc_divider") p.rtc_divider = value;
        else if (key == "max_cycles") p.max_cycles = value;
        else p.trap_cycles = value;
      } else if (key == "hart" && f.size() == 4) {
        const bool source_idle=f[3]=="source";
        auto id = number(f[1]), divider = number(f[2]), idle = source_idle?0:number(f[3]);
        if (id >= count || !divider || idle > 1 || p.harts[id].divider)
          throw std::runtime_error("invalid/duplicate hart clock");
        p.harts[id] = {divider, bool(idle),source_idle};
      } else if (key == "resource" && f.size() == 3) {
        auto lanes = number(f[2]);
        if (!lanes || lanes > 1024 || !resource_names.insert(f[1]).second)
          throw std::runtime_error("invalid/duplicate resource");
        p.resources.emplace_back(f[1], unsigned(lanes));
      } else if (key == "memory_port" && f.size() == 4) {
        const auto lanes=number(f[2]);
        if (!lanes || lanes>1024 || !resource_names.insert(f[1]).second)
          throw std::runtime_error("invalid/duplicate memory port");
        p.memory_ports.push_back({f[1],unsigned(lanes),f[3]});
      } else if (key == "memory_region" && f.size() == 7) {
        const auto hart=number(f[1]);
        if (hart>=count) throw std::runtime_error("memory region hart out of range");
        p.memory_regions.push_back({unsigned(hart),number(f[2]),number(f[3]),number(f[4]),number(f[5]),f[6]});
      } else if (key == "memory_stage" && f.size() == 12) {
        if (f[11]!="base_cycles" || !number(f[10])) throw std::runtime_error("memory stage requires explicit clock and base_cycles units");
        const bool dynamic=f[6]=="access";
        p.memory_stages[f[1]].push_back({{f[2],f[3],number(f[4]),number(f[5]),dynamic?0:number(f[6]),
                                       number(f[7]),number(f[8]),f[9],number(f[10])},dynamic});
      } else if (key == "rule" && f.size() == 9) {
        auto hart = number(f[1]), mask = number(f[2]), match = number(f[3]);
        auto latency = number(f[5]), interval = number(f[6]);
        if (hart >= count || mask > UINT32_MAX || match > UINT32_MAX || (match & ~mask) ||
            !latency || !interval || f[8] != "base_cycles")
          throw std::runtime_error("invalid rule");
        p.rules.push_back({unsigned(hart), uint32_t(mask), uint32_t(match), f[4], latency, interval, f[7]});
      } else throw std::runtime_error("unknown field or incorrect field count");
    } catch (const std::exception& error) {
      throw std::runtime_error(path + ":" + std::to_string(lineno) + ": " + error.what());
    }
  }
  if (!purpose || p.source.empty() || !p.base_hz || !p.rtc_divider || !p.max_cycles || !p.trap_cycles)
    throw std::runtime_error("incomplete timing integration fixture");
  if(p.empirical_rocket_packets&&(!p.empirical||!p.rocket_pure_pipeline||p.saved_rocket_frontend||p.saturn_live))throw std::runtime_error("Rocket packet flow requires explicit empirical pure CPU mode and excludes other Rocket frontend actors");
  if(!p.empirical&&(p.empirical_vector_store_capture||p.empirical_async||p.empirical_icache||p.empirical_load_front||p.empirical_vme_shape_work||p.empirical_store_front||p.empirical_read_overlap||p.empirical_shuttle_random||!p.empirical_scalar_l2_hit_rules.empty()||!p.empirical_scalar_outer_rules.empty()||!p.empirical_instruction_rules.empty()||!p.empirical_branch_rules.empty()||!p.empirical_cache_rules.empty()||!p.empirical_rules.empty()))throw std::runtime_error("empirical family requires explicit empirical_profile");
  for(const auto&r:p.empirical_rules){if(!resource_names.count(r.resource))throw std::runtime_error("empirical family resource missing");}
  if(p.empirical&&(p.saved_rocket_frontend||p.rocket_memory_fabric||p.saturn_live))throw std::runtime_error("empirical mode never constructs RTL peers");
  if(p.saturn_live&&(!p.saved_shuttle_frontend||!p.source_counter_clock||p.rocket_memory_fabric))throw std::runtime_error("first live Saturn scope requires source frontend/counters and explicit functional shared-memory fixture");
  if(p.rocket_serial){
    if(singleton.count("rocket_fabric")||!singleton.count("serial_cbus_fixture")||!p.rocket_scalar_memory||!p.source_counter_clock||p.base_hz!=1000000000ULL)throw std::runtime_error("Serial source mode requires distinct explicit CBUS fixture, scalar memory, source counters and 1GHz virtual phase calendar");
    for(const auto&h:p.harts)if(h.divider!=2)throw std::runtime_error("Serial saved-reference requires all three source core periods2");
  }else if(singleton.count("serial_cbus_fixture"))throw std::runtime_error("CBUS fixture without source serial path");
  if(p.saved_rocket_frontend && (!p.saved_shuttle_frontend || !p.rocket_pure_pipeline || !p.private_forwarded_values))throw std::runtime_error("Rocket source frontend requires source Shuttle frontend and private integer pipeline");
  if(p.rocket_scalar_memory&&!p.rocket_memory_fabric)throw std::runtime_error("source scalar memory requires source fabric");
  if(p.rocket_memory_fabric&&(!p.saved_rocket_frontend||p.base_hz%p.fabric_uncore_divider||p.fabric_uncore_divider!=p.harts.at(2).divider))throw std::runtime_error("source fabric requires actual Rocket frontend and explicit integral uncore clock");
  if(p.source_counter_clock && !p.saved_shuttle_frontend&&!p.empirical)throw std::runtime_error("source counter policy currently requires source frontend scope");
  for(const auto& hart:p.harts)if(hart.source_counter_idle!=p.source_counter_clock)throw std::runtime_error("source counter policy requires hart idle declaration source; numeric count_wfi is synthetic");
  if(p.synthetic_icache_first && !p.saved_shuttle_frontend)throw std::runtime_error("instruction memory service without source frontend");
  if(p.saved_shuttle_frontend && (!p.shuttle_counter_pipeline || !p.private_forwarded_values))
    throw std::runtime_error("source frontend requires source RVC/counter pipeline and private values");
  if(p.private_forwarded_values && !(p.shuttle_pure_pipeline || p.rocket_pure_pipeline))
    throw std::runtime_error("private forwarded values require an explicit source pipeline");
  if ((p.shuttle_pure_pipeline || p.rocket_pure_pipeline) && count != 3)
    throw std::runtime_error("source Iris pipeline fixture requires all three physical harts");
  for (unsigned hart = 0; hart < count; ++hart) {
    if (!p.harts[hart].divider || p.base_hz % p.harts[hart].divider)
      throw std::runtime_error("missing/non-integral hart clock");
    bool found = false;
    for (const auto& rule : p.rules) {
      if (!resource_names.count(rule.resource)) throw std::runtime_error("rule resource missing");
      found |= rule.hart == hart;
    }
    if (!found) throw std::runtime_error("timing rules missing for hart");
  }
  if (p.base_hz % p.rtc_divider) throw std::runtime_error("non-integral RTC frequency");
  return p;
}

iris_timing_adapter::iris_timing_adapter(Profile profile, std::vector<processor_t*> cores,
    std::function<void(Cycle, Cycle)> advance,
    std::function<std::optional<Cycle>()> timer_deadline,
    std::function<bool()> host_request, std::optional<uint64_t> schedule_seed)
    : profile_(std::move(profile)), cores_(std::move(cores)),
      clock_(cores_.size(), profile_.rtc_divider), pending_(cores_.size()),
      previous_(cores_.size()), blocked_(cores_.size(), false),
      timer_deadline_(std::move(timer_deadline)), host_request_(std::move(host_request)),
      retired_(cores_.size(), 0), seed_(schedule_seed), rng_(schedule_seed.value_or(0)) {
  empirical_diagnostics_=std::getenv("IRIS_EMPIRICAL_DIAGNOSTICS")!=nullptr;empirical_load_metrics_.resize(cores_.size());empirical_branch_recovery_.resize(cores_.size());empirical_fallback_counts_.resize(cores_.size());empirical_fetch_.resize(cores_.size());empirical_async_.resize(cores_.size());empirical_async_next_.resize(cores_.size());empirical_async_handoffs_.resize(cores_.size());empirical_branches_.resize(cores_.size());features_.resize(cores_.size());memory_features_.resize(cores_.size());
  if(profile_.empirical_store_front&&(profile_.saturn_live||profile_.rocket_scalar_memory||!profile_.private_forwarded_values))throw std::runtime_error("IRIS_STORE_FRONT_EXPLICIT_EMPIRICAL_PRIVATE_PIPELINE_REQUIRED");
  store_metrics_.resize(cores_.size());store_deferred_.resize(cores_.size());
  if(profile_.empirical)empirical_cache_=std::make_unique<iris::empirical::CacheHistoryV9>(iris::empirical::iris_geometry_v9(),profile_.empirical_read_overlap,profile_.empirical_shuttle_random);
  empirical_scalar_l2_services_.resize(cores_.size());for(const auto&r:profile_.empirical_scalar_l2_hit_rules)empirical_scalar_l2_services_.at(r.hart).configure(r.coefficient,profile_.max_cycles);
  empirical_scalar_outer_services_.resize(cores_.size());for(const auto&r:profile_.empirical_scalar_outer_rules)empirical_scalar_outer_services_.at(r.hart).configure(r.coefficient,profile_.max_cycles);
  if(profile_.empirical){if(const char*path=std::getenv("IRIS_EMPIRICAL_ASYNC_TRACE")){async_trace_=std::make_unique<std::ofstream>(path);if(!*async_trace_)throw std::runtime_error("cannot open empirical async trace");}}
  if(profile_.empirical){if(const char*path=std::getenv("IRIS_EMPIRICAL_FEATURES")){feature_stream_=std::make_unique<std::ofstream>(path);if(!*feature_stream_)throw std::runtime_error("cannot open empirical feature stream");}}
  opu_pending_.resize(cores_.size());opu_queues_.resize(cores_.size());opu_clock_active_.resize(cores_.size());opu_queue_peak_.resize(cores_.size());opu_full_edges_.resize(cores_.size());opu_front_stalls_.resize(cores_.size());opu_accepted_.resize(cores_.size());opu_writes_.resize(cores_.size());opu_peak_.resize(cores_.size());
  if(profile_.empirical_opu_entry&&(!profile_.empirical_async||!profile_.private_forwarded_values||profile_.saturn_live||profile_.rocket_scalar_memory))throw std::runtime_error("IRIS_OPU_ENTRY_EXPLICIT_EMPIRICAL_PRIVATE_PIPELINE_REQUIRED");
  if(profile_.empirical_opu_entry)for(unsigned h=0;h<2;++h){clock_.configure_resource("source.opu.queue.clock"+std::to_string(h),1);clock_.configure_resource("source.opu.mrf.write"+std::to_string(h),1);clock_.configure_resource("source.opu.callback.clock"+std::to_string(h),1);}
  scalar_fadd_.resize(cores_.size());scalar_fadd_accepted_.resize(cores_.size());scalar_fadd_published_.resize(cores_.size());scalar_fadd_killed_.resize(cores_.size());scalar_fadd_peak_.resize(cores_.size());scalar_fadd_irq_deferrals_.resize(cores_.size());scalar_fadd_last_irq_.resize(cores_.size());
  pure_.resize(cores_.size());clock_.retain_history(profile_.keep_history);
  if(profile_.source_counter_clock)for(const auto& hart:profile_.harts)source_counter_clocks_.emplace_back(hart.divider);
  counter_sequences_.resize(cores_.size(),0);
  for (const auto& resource : profile_.resources) clock_.configure_resource(resource.first, resource.second);
  if(!profile_.empirical_cache_rules.empty()||!profile_.empirical_instruction_rules.empty())clock_.configure_resource("empirical.outer",1);
  if (!profile_.memory_ports.empty() || !profile_.memory_regions.empty() || !profile_.memory_stages.empty()) {
    for (const auto* core:cores_)
      if (core->get_const_xlen()!=64)
        throw std::runtime_error("IRIS_TIMING_SCALAR_MEMORY_REQUIRES_RV64");
    std::set<std::string> ports;
    for (const auto& port:profile_.memory_ports) ports.insert(port.resource);
    for (const auto& path:profile_.memory_stages) for (const auto& stage:path.second)
      if (!ports.count(stage.stage.resource)) throw std::runtime_error("memory stage port missing");
    memory_routes_=std::make_unique<iris::ScalarMemoryRoutes>(cores_.size(),profile_.memory_regions,profile_.memory_stages);
    memory_paths_=std::make_unique<iris::MemoryPaths>(clock_,profile_.memory_ports);
  }
  for (size_t i = 0; i < cores_.size(); ++i) {
    order_.push_back(i);
    if (cores_[i]->get_id() != i) throw std::runtime_error("timing adapter requires contiguous architectural hart IDs");
    if(profile_.empirical_scalar_fadd)clock_.configure_resource("source.scalarFPU"+std::to_string(i),1);
    clock_.configure_resource("trap" + std::to_string(i), 1);
    if(profile_.empirical)clock_.configure_resource("empirical.vector-memory"+std::to_string(i),1);
    if(profile_.empirical_load_front||profile_.empirical_store_front)clock_.configure_resource("empirical.memory"+std::to_string(i),1);
    if(!profile_.empirical_branch_rules.empty())clock_.configure_resource("empirical.frontend"+std::to_string(i),1);
    if(profile_.empirical&&i==0){clock_.configure_resource("empirical.tcm.target0",1);clock_.configure_resource("empirical.tcm.target1",1);}
    if(profile_.empirical_icache)clock_.configure_resource("empirical.icache"+std::to_string(i),1);
    if(profile_.empirical_async){clock_.configure_resource("empirical.vector"+std::to_string(i),1);clock_.configure_resource("empirical.vme"+std::to_string(i),1);if(profile_.empirical_async_fadd)clock_.configure_resource((i==2?"empirical.sharedFPU":"empirical.vectorFP")+std::to_string(i),1);}
    if (profile_.shuttle_pure_pipeline && i < 2) {
      if (cores_[i]->get_const_xlen() != 64)
        throw std::runtime_error("IRIS_PIPELINE_REQUIRES_RV64");
      const auto prefix = "shuttle" + std::to_string(i) + ".";
      clock_.configure_resource(prefix + "EX", 2);
      clock_.configure_resource(prefix + "CSR_EX", 1);
      if(profile_.empirical)clock_.configure_resource(prefix+"BRANCH_MEM",1);
      clock_.configure_resource(prefix + "MEM_ALU", 1);
  
    if(profile_.empirical_load_front)clock_.configure_resource(prefix+"LOAD_RESPONSE",1);
      clock_.configure_resource(prefix + "COM", 2);
      clock_.configure_resource(prefix + "WB", 2);
    }
    if (profile_.rocket_pure_pipeline && i==2) {
      if (cores_[i]->get_const_xlen()!=64) throw std::runtime_error("IRIS_ROCKET_PIPELINE_REQUIRES_RV64");
      for (const auto* stage:{"EX","MEM","WB"}) clock_.configure_resource("rocket2."+std::string(stage),1);
    }
  }
  clock_.on_advance([this,advance=std::move(advance)](Cycle before,Cycle now){advance(before,now);if(profile_.empirical_opu_entry)opu_check_irq();if(async_trace_)for(unsigned h=0;h<cores_.size();++h)if(empirical_async_[h]&&cores_[h]->iris_pipeline_interrupt_exception())*async_trace_<<"{\"event\":\"interrupt_pre_completion\",\"hart\":"<<h<<",\"cycle\":"<<now<<",\"pending\":"<<(empirical_async_next_[h]?2:1)<<"}\n";});
  frontend_initialize();
  if(profile_.saturn_live)saturn_initialize();
  if(profile_.empirical_rocket_packets)rocket_packet_initialize();
}
void iris_timing_adapter::retired(unsigned hart, size_t count) { if(profile_.empirical&&count==1)empirical_retired(hart);retired_.at(hart) += count; }

const insn_fetch_t* iris_timing_adapter::completion_fetch(unsigned hart) const {
  if (!completing_ || *completing_ != hart) return nullptr;
  if (completing_pure_) {
    const auto& instruction = pure_.at(hart).instructions.at(*completing_pure_);
    return instruction.exception ? nullptr : &instruction.fetch;
  }
  if (!pending_.at(hart)) throw std::logic_error("timing completion has no fetched instruction");
  return &pending_[hart]->fetch;
}

std::exception_ptr iris_timing_adapter::completion_exception(unsigned hart) const {
  if (!completing_ || *completing_ != hart || !completing_pure_) return {};
  return pure_.at(hart).instructions.at(*completing_pure_).exception;
}

void iris_timing_adapter::issue(unsigned hart, reg_t pc, const insn_fetch_t& fetch) {
  if(profile_.empirical_scalar_fadd&&scalar_fadd_pending(hart)&&!pure_candidate(hart,fetch))throw iris_timing_wait{};
  if (blocked_.at(hart)) throw std::logic_error("second in-flight instruction in conservative adapter");
  if (profile_.saturn_live&&saturn_try_issue(hart,pc,fetch)) throw iris_timing_wait{};
  if(profile_.empirical_async&&empirical_async_[hart]&&!pure_candidate(hart,fetch))throw iris_timing_wait{};
  auto empirical_instruction=fetch.insn;
  if(profile_.empirical&&!frontend_enabled(hart)&&!empirical_fetch_ready(hart,pc,empirical_instruction.length(),&fetch))throw iris_timing_wait{};
  if (pure_begin(hart, pc, fetch)) throw iris_timing_wait{};
  // A legal opcode can still be outside the qualified CPU fetch front (e.g.
  // a 4-byte Shuttle instruction split over4KiB). Never let that fallback
  // mutate VRF/MRF ahead of accepted entry-owned physical writes.
  if(profile_.empirical_opu_entry&&hart<2){
    if(!opu_pending_[hart].empty())throw iris_timing_wait{};
    if(opu_is_mm(&fetch))throw std::runtime_error("IRIS_OPU_ENTRY_MM_CPU_FETCH_BOUNDARY_UNMODELED hart="+std::to_string(hart)+" pc="+std::to_string(pc));
  }
  if(profile_.rocket_memory_fabric&&hart<2){
    const auto bits=frontend_[hart].outputs.queue[0].expanded;
    std::array<uint64_t,32> registers;for(unsigned reg=0;reg<32;++reg)registers[reg]=cores_[hart]->get_state()->XPR.read_transport(reg).value;
    const auto access=iris::scalar_memory_access(bits,registers);
    if(access.decode==iris::MemoryDecode::scalar){cores_[hart]->get_state()->XPR.require_defined((bits>>15)&31,sizeof(reg_t),{hart,pc,"source-fabric-other-hart-address"});
      if((access.address>=0x70000000&&access.address<0x70040000)||(access.address>=0x80000000&&access.address<0x180000000ULL)||(access.address>=0x580000000ULL&&access.address<0x580020000ULL))throw std::runtime_error("IRIS_SOURCE_FABRIC_SHUTTLE_DATA_PEER_NOT_CONNECTED");}
    if(access.decode==iris::MemoryDecode::vector||access.decode==iris::MemoryDecode::unresolved)throw std::runtime_error("IRIS_SOURCE_FABRIC_SHUTTLE_VECTOR_DATA_PEER_NOT_CONNECTED");
  }
  const Rule* selected = nullptr;
  auto instruction = fetch.insn;
  if(hart==2 && rocket_frontend_enabled() && (uint32_t(instruction.bits())&127)==0x73 && ((uint32_t(instruction.bits())>>12)&7) && uint32_t(instruction.bits())>>20==0x7c1)throw std::runtime_error("IRIS_ROCKET_SOURCE_CUSTOM_CSR_ACCESS_UNMODELED");
  for (const auto& rule : profile_.rules)
    if (rule.hart == hart && (uint32_t(instruction.bits()) & rule.mask) == rule.match) { selected = &rule; break; }
  if (!selected) throw std::runtime_error("IRIS_TIMING_UNMODELED_INSTRUCTION hart=" + std::to_string(hart));
  if(profile_.rocket_memory_fabric && !profile_.rocket_scalar_memory && hart==2) {
    const auto bits=rocket_frontend_.outputs.id.expanded;
    if((bits&127)==0x03||(bits&127)==0x23||(bits&127)==0x2f||(bits&127)==0x07||(bits&127)==0x27)throw std::runtime_error("IRIS_ROCKET_FABRIC_SCALAR_DATA_CPU_PHASE_NOT_INTEGRATED");
  }
  if(profile_.rocket_scalar_memory&&hart==2){const auto bits=rocket_frontend_.outputs.id.expanded,op=bits&127;
    if(op==3||op==0x23||op==0x2f||op==7||op==0x27)throw std::runtime_error("IRIS_ROCKET_FABRIC_DATA_OPCODE_OUTSIDE_QUALIFIED_SCALAR_SUBSET");}
  iris::ScalarAccess access;
  if (memory_routes_) {
    std::array<uint64_t,32> registers;
    const auto* state=cores_[hart]->get_state();
    for (unsigned i=0;i<32;++i) registers[i]=state->XPR[i];
    access=iris::scalar_memory_access(uint32_t(instruction.bits()),registers);
    if (access.decode==iris::MemoryDecode::vector || access.decode==iris::MemoryDecode::unresolved)
      throw std::runtime_error("IRIS_TIMING_MEMORY_OPERATION_UNMODELED hart="+std::to_string(hart));
    if (access.decode==iris::MemoryDecode::scalar && cores_[hart]->VU.iris_mode) {
      // Effective-address extraction may inspect placeholders internally, but
      // routing/bank selection must never observe an unknown architectural
      // base. This matches the actual handler's RS1 read before translation.
      const uint32_t raw=uint32_t(instruction.bits());
      const unsigned base=(raw&3)==3 ? (raw>>15)&31 : (raw&3)==0 ? 8+((raw>>7)&7) : 2;
      state->XPR.require_defined(base,sizeof(reg_t),{hart,pc,"timing-memory-address"});
    }
    if (access.decode==iris::MemoryDecode::scalar &&
        (state->prv!=PRV_M || state->v || state->debug_mode || (state->mstatus->read()&MSTATUS_MPRV)))
      throw std::runtime_error("IRIS_TIMING_TRANSLATED_MEMORY_UNMODELED hart="+std::to_string(hart));
  }
  if(frontend_enabled(hart)) {
    auto& f=frontend_[hart];
    if(!f.prepared || !f.outputs.queue[0].valid || f.outputs.queue[0].pc!=pc)throw std::runtime_error("IRIS_FRONTEND_BOUNDARY_QUEUE_MISMATCH");
    f.conservative=f.outputs.queue[0];frontend_consume(hart,1);
  }
  if(hart==2 && rocket_frontend_enabled()) {
    auto& f=rocket_frontend_;if(!f.prepared || !f.outputs.id.valid || f.outputs.id.replay || f.outputs.id.pc!=pc)throw std::runtime_error("IRIS_ROCKET_FRONTEND_BOUNDARY_QUEUE_MISMATCH");
    f.conservative=f.outputs.id;rocket_frontend_consume();
  }
  if(profile_.empirical)empirical_fetch_consume(hart,pc,instruction.length());
  pending_[hart] = Pending{pc, fetch, {},profile_.empirical?empirical_feature(hart,fetch):Feature{}}; blocked_[hart] = true;
  iris::Op op{hart, selected->name, selected->resource, selected->latency, selected->interval};
  std::vector<iris::NodeId> cache_dependencies;std::optional<iris::empirical::Delta> cache_delta;
  if(profile_.empirical_load_front&&(uint32_t(instruction.bits())&127)==0x0f)for(const auto&[node,actor]:empirical_load_responses_)if(actor->hart==hart&&!actor->done)op.deps.push_back(node);
  if(profile_.empirical&&pending_[hart]->feature.memory.decode==iris::MemoryDecode::scalar){
   auto&f=pending_[hart]->feature;const auto*state=cores_[hart]->get_state();
   if(state->prv!=PRV_M||state->v||(state->mstatus->read()&MSTATUS_MPRV))throw std::runtime_error("IRIS_EMPIRICAL_TRANSLATED_MEMORY_UNSUPPORTED");
   const uint32_t raw=uint32_t(instruction.bits());const unsigned base=(raw&3)==3?(raw>>15)&31:(raw&3)==0?8+((raw>>7)&7):2;
   state->XPR.require_defined(base,sizeof(reg_t),{hart,pc,"empirical-memory-address"});
   const auto owner=next_cache_owner_++;const bool write=f.memory.kind==iris::AccessKind::store||f.memory.kind==iris::AccessKind::sc||f.memory.kind==iris::AccessKind::amo;
   const iris::empirical::Access access{owner,hart,f.memory.address,f.memory.bytes,write,clock_.now()};
   const bool vector=f.family.starts_with("memory.vector.");
   const auto delta=vector?empirical_cache_->begin_vector(access):f.memory.kind==iris::AccessKind::load?empirical_cache_->begin_read(access):empirical_cache_->begin(access);cache_delta=delta;
   if(vector){op.latency=std::max(op.latency,f.dlen_beats*profile_.harts[hart].divider);op.resource="empirical.vector-memory"+std::to_string(hart);}pending_[hart]->cache_owner=owner;
   for(const auto id:delta.wait_for){const auto found=cache_nodes_.find(id);if(found==cache_nodes_.end())throw std::logic_error("empirical pending owner missing node");cache_dependencies.push_back(found->second);}
   if(f.family.starts_with("memory.")&&!f.family.starts_with("memory.vector."))f.family="memory."+std::string(iris::empirical::path_name(delta.path))+(f.memory.kind==iris::AccessKind::lr?".lr":f.memory.kind==iris::AccessKind::sc?".sc":f.memory.kind==iris::AccessKind::amo?".atomic":write?".store":".load");
   empirical_memory_feature(hart,delta,write);
  }

  if(profile_.empirical){const auto&feature=pending_[hart]->feature;for(const auto&rule:profile_.empirical_rules)if(rule.hart==hart&&rule.family==feature.family&&!(cache_delta&&cache_delta->path==iris::empirical::Path::DRAM&&!feature.family.starts_with("memory.vector.")&&!profile_.empirical_cache_rules.empty())){const auto key=std::to_string(hart)+":"+feature.family;auto&fraction=empirical_fraction_[key];fraction+=rule.setup+rule.work*feature.work;if(!std::isfinite(fraction)||fraction>profile_.max_cycles)throw std::runtime_error("IRIS_EMPIRICAL_COST_OUTSIDE_HORIZON");const auto extra=uint64_t(std::floor(fraction));fraction-=extra;op.latency+=extra*profile_.harts[hart].divider;op.interval=rule.interval*profile_.harts[hart].divider;op.resource=rule.resource;if(cache_delta&&(cache_delta->path==iris::empirical::Path::LocalTCM||cache_delta->path==iris::empirical::Path::RemoteTCM))op.resource="empirical.tcm.target"+std::to_string((cache_delta->canonical_address-0x70000000ULL)/0x20000ULL);op.name="empirical."+feature.family;break;}op.bytes=feature.bytes;op.macs=feature.macs;}
  if(cache_delta&&cache_delta->path==iris::empirical::Path::DRAM){for(const auto&r:profile_.empirical_cache_rules)if(r.hart==hart){const auto&d=*cache_delta;const bool write=pending_[hart]->feature.memory.kind!=iris::AccessKind::load&&pending_[hart]->feature.memory.kind!=iris::AccessKind::lr;const bool vector=pending_[hart]->feature.family.starts_with("memory.vector.");const auto residual=(vector?0:(write?r.write:r.read)+r.l1*d.l1_misses)+r.outer*d.l2_misses+r.dirty*d.l2_dirty_victims;auto&fraction=empirical_fraction_["cache:"+std::to_string(hart)];fraction+=residual;if(!std::isfinite(fraction)||fraction>profile_.max_cycles)throw std::runtime_error("IRIS_EMPIRICAL_COST_OUTSIDE_HORIZON");const auto extra=uint64_t(std::floor(fraction));fraction-=extra;op.latency=(vector?op.latency:selected->latency)+extra*profile_.harts[hart].divider;op.name="empirical.cache."+pending_[hart]->feature.family;if(d.l2_misses){op.resource="empirical.outer";op.interval=uint64_t(std::ceil(r.outer_interval*d.l2_misses))*profile_.harts[hart].divider;}break;}}
  if(cache_delta){const auto&f=pending_[hart]->feature;const auto actor=f.family.starts_with("memory.vector.")?iris::empirical::L2ServiceActor::VectorMemory:f.memory.kind==iris::AccessKind::load?iris::empirical::L2ServiceActor::ScalarLoad:iris::empirical::L2ServiceActor::Other;op.latency+=(empirical_scalar_l2_hit_extra(hart,*cache_delta,actor)+empirical_scalar_outer_extra(hart,*cache_delta,actor))*profile_.harts[hart].divider;}
  op.deps.insert(op.deps.end(),cache_dependencies.begin(),cache_dependencies.end());
  op.pc = pc; op.retires = false; op.issue_period = profile_.harts[hart].divider;
  if (previous_[hart]) op.deps.push_back(*previous_[hart]);
  op.on_complete = [this, hart] {
    if (cores_[hart]->get_state()->pc != pending_[hart]->pc)
      throw std::runtime_error("IRIS_TIMING_PC_CHANGED_DURING_FLIGHT");
    if(profile_.source_counter_clock && clock_.now()%profile_.harts[hart].divider)throw std::runtime_error("IRIS_SOURCE_COUNTER_COM_OFF_HART_EDGE_UNMODELED");
    completing_ = hart;
    completing_node_ = pending_[hart]->completion_node;
    completion_reads_.clear();
    if (!completing_node_) throw std::logic_error("IRIS_COUNTER_CAPTURE_COMPLETION_NODE_MISSING");
    const auto retired_before = retired_[hart];
    try { empirical_vector_store_step(hart); }
    catch (...) { completion_reads_.clear(); completing_node_.reset(); completing_.reset(); throw; }
    if(retired_[hart]==retired_before+1)empirical_store_boundary_observe(hart);
    finish_counter_reads(hart,retired_before);
    if(hart==2&&rocket_packets_&&retired_[hart]==retired_before+1){auto instruction=pending_[hart]->fetch.insn;if(cores_[hart]->get_state()->pc!=pending_[hart]->pc+instruction.length())rocket_packet_redirect(cores_[hart]->get_state()->pc,"conservative-COM-control",2);}

    if(pending_[hart]->cache_owner){const auto id=*pending_[hart]->cache_owner;empirical_cache_->complete(id,clock_.now(),retired_[hart]==retired_before+1);cache_nodes_.erase(id);}
    std::optional<unsigned> source_trap_ras_head;
    if(frontend_enabled(hart)) {
      if(!frontend_[hart].conservative)throw std::logic_error("IRIS_SOURCE_CONSERVATIVE_TRAP_OWNER_MISSING");
      source_trap_ras_head=frontend_[hart].conservative->ras_head;
      if(retired_[hart]==retired_before+1)frontend_boundary_complete(hart,pending_[hart]->pc,pending_[hart]->fetch);
      else frontend_[hart].conservative.reset(); // exception owns the captured parcel redirect below
    }
    if(hart==2 && rocket_frontend_enabled()) {
      if(retired_[hart]==retired_before+1)rocket_frontend_boundary_complete(pending_[hart]->pc,pending_[hart]->fetch);
      else rocket_frontend_.conservative.reset();
    }
    completing_.reset(); pending_[hart].reset(); blocked_[hart] = false; ++completions_;
    if (retired_[hart] == retired_before) queue_trap(hart,source_trap_ras_head);
  };
  if (access.decode==iris::MemoryDecode::scalar) {
    // Validate address routing before adding any nodes or executing effects.
    auto request=memory_routes_->request(hart,access,pc,profile_.harts[hart].divider,{},op.on_complete);
    op.on_complete={};
    const auto address_generation=clock_.issue(std::move(op));
    request.dependencies={address_generation};
    auto transfer=memory_paths_->submit(std::move(request));
    previous_[hart]=transfer.nodes.back();
    memory_transfers_.push_back({hart,access.kind,std::move(transfer)});
  } else previous_[hart] = clock_.issue(std::move(op));
  pending_[hart]->completion_node=previous_[hart];
  if(pending_[hart]->cache_owner)cache_nodes_[*pending_[hart]->cache_owner]=*previous_[hart];
  if(profile_.empirical_store_front&&async_trace_&&pending_[hart]->cache_owner){const auto&f=pending_[hart]->feature;if(!f.family.starts_with("memory.vector.")&&(f.memory.kind==iris::AccessKind::load||f.memory.kind==iris::AccessKind::store)){*async_trace_<<"{\"event\":\"scalar_cache_intent\",\"scope\":\"V6-approximate-intent-time-tags\",\"hart\":"<<hart<<",\"pc\":"<<pc<<",\"cycle\":"<<clock_.now()<<",\"address\":"<<f.memory.address<<",\"bytes\":"<<f.memory.bytes<<",\"write\":"<<(f.memory.kind==iris::AccessKind::store?"true":"false")<<",\"cache_owner\":"<<*pending_[hart]->cache_owner<<",\"node\":"<<*previous_[hart]<<",\"dependencies\":[";for(unsigned i=0;i<cache_dependencies.size();++i){if(i)*async_trace_<<',';*async_trace_<<cache_dependencies[i];}*async_trace_<<"]}\n";}}

  throw iris_timing_wait{};
}

void iris_timing_adapter::dispatch_ready() {
  if (seed_) std::shuffle(order_.begin(), order_.end(), rng_);
  for (unsigned hart : order_) {
    if (blocked_[hart]||empirical_branch_recovery_[hart]) continue;
    if(profile_.empirical_store_front&&store_deferred_[hart])continue;
    if(scalar_fadd_defer_irq(hart))continue;
    if(profile_.empirical_async&&empirical_async_[hart]&&cores_[hart]->iris_pipeline_interrupt_exception()){if(async_trace_)*async_trace_<<"{\"event\":\"interrupt_defer\",\"hart\":"<<hart<<",\"cycle\":"<<clock_.now()<<",\"pending\":"<<(empirical_async_next_[hart]?2:1)<<"}\n";continue;}
    if(profile_.source_counter_clock && (clock_.now()%profile_.harts[hart].divider || source_counter_clocks_[hart].blocks_rrd(clock_.now())))continue;
    if (((profile_.shuttle_pure_pipeline && hart<2) || (profile_.rocket_pure_pipeline && hart==2)) && pure_[hart].engaged) {
      pure_dispatch(hart);
      if (pure_[hart].engaged) continue;
    }
    auto* core = cores_[hart]; auto* state = core->get_state();
    if(frontend_enabled(hart)) {
      const auto& f=frontend_[hart];
      if(!f.prepared || f.inputs.redirect_flush || !f.outputs.queue[0].valid)continue;
      if(f.outputs.queue[0].pc!=state->pc){frontend_diagnostic(hart,"architectural-queue-PC-mismatch");throw std::runtime_error("IRIS_FRONTEND_ARCHITECTURAL_QUEUE_PC_MISMATCH hart="+std::to_string(hart)+" queue="+std::to_string(f.outputs.queue[0].pc)+" architectural="+std::to_string(state->pc));}
    }
    if (core->is_waiting_for_interrupt() && !(state->mip->read() & state->mie->read())) continue;
    // The source-clock policy clears this transport flag at its sampled
    // wake edge. Legacy synthetic policy still needs Spike's ordinary
    // locally-enabled-pending wake before using a prepared completion fetch,
    // which intentionally bypasses take_pending_interrupt at COM.
    if(hart==2 && rocket_frontend_enabled() && core->is_waiting_for_interrupt())core->clear_waiting_for_interrupt();
    if(hart==2 && rocket_frontend_enabled()) {
      auto& f=rocket_frontend_;
      if(!f.prepared || f.inputs.redirect_valid || !f.outputs.id.valid)continue;
      if(f.outputs.id.replay){rocket_frontend_replay_accept();continue;}
      if(f.outputs.id.pc!=state->pc)throw std::runtime_error("IRIS_ROCKET_FRONTEND_ARCHITECTURAL_PC_MISMATCH");
      const auto& u=f.outputs.id;std::exception_ptr exception=core->iris_pipeline_interrupt_exception();
      if(!exception && (u.first_access_fault||u.second_access_fault))exception=std::make_exception_ptr(trap_instruction_access_fault(false,u.pc+(u.second_access_fault?2:0),0,0));
      if(!exception && (u.first_page_fault||u.second_page_fault||u.first_guest_page_fault||u.second_guest_page_fault))throw std::runtime_error("IRIS_ROCKET_FRONTEND_VM_FAULT_UNMODELED");
      if(exception){auto& p=pure_[hart];p.engaged=true;p.boundary=false;p.frontier=u.pc;pure_exception(hart,exception);rocket_frontend_consume();continue;}
      const insn_t raw(u.compressed?uint16_t(u.raw):u.raw);
      try{issue(hart,u.pc,{core->decode_for_model(raw),raw});}catch(iris_timing_wait&){}
      continue;
    }
    if (core->is_waiting_for_interrupt() && !(state->mip->read() & state->mie->read())) continue;
    std::optional<unsigned> direct_source_ras_head;
    if(frontend_enabled(hart) && !core->is_waiting_for_interrupt()) {
      if(!core->iris_pipeline_context_safe())throw std::runtime_error("IRIS_FRONTEND_NON_M_MODE_CONTEXT_UNMODELED");
      const auto& u=frontend_[hart].outputs.queue[0];
      std::exception_ptr exception=core->iris_pipeline_interrupt_exception();
      if(!exception && u.exception) {
        if(u.exception_cause==CAUSE_FETCH_ACCESS)exception=std::make_exception_ptr(trap_instruction_access_fault(false,u.pc,0,0));
        else if(u.exception_cause==CAUSE_FETCH_PAGE_FAULT)exception=std::make_exception_ptr(trap_instruction_page_fault(false,u.pc,0,0));
        else throw std::runtime_error("IRIS_FRONTEND_EXCEPTION_CAUSE_UNMODELED");
      }
      if(exception) {
        auto& p=pure_[hart];if(!p.packets.empty())throw std::logic_error("frontend direct exception with live packets");
        p.engaged=true;p.boundary=false;p.frontier=u.pc;pure_exception(hart,exception);frontend_consume(hart,1);continue;
      }
      const insn_t raw(u.compressed?uint16_t(u.raw):u.raw);
      try {issue(hart,u.pc,{core->decode_for_model(raw),raw});}catch(iris_timing_wait&){}
      // issue only schedules or waits; this arm never synchronously steps the
      // core. An empty boundary retry therefore cannot be a trap entry.
      continue;
    } else {
      if(frontend_enabled(hart)){
        const auto&f=frontend_[hart];
        if(!f.prepared||!f.outputs.queue[0].valid||f.outputs.queue[0].pc!=state->pc)
          throw std::logic_error("IRIS_SOURCE_DIRECT_WAKE_TRAP_PARCEL_MISSING");
        direct_source_ras_head=f.outputs.queue[0].ras_head;
      }
      if(hart==2&&rocket_packets_)rocket_packet_waiting_=false;core->step(1);
    }
    if (blocked_[hart] || pure_[hart].engaged || core->is_waiting_for_interrupt() || (hart==2&&rocket_packet_waiting_)) continue;
    // A fetch/interrupt/architectural trap can happen before instruction issue.
    // Its state transition is local; the handler cannot run until this event ends.
    queue_trap(hart,direct_source_ras_head);
  }
}
void iris_timing_adapter::queue_trap(unsigned hart,std::optional<unsigned> source_ras_head) {
  if(frontend_enabled(hart)&&(!source_ras_head||*source_ras_head>7))
    throw std::logic_error("IRIS_SOURCE_TRAP_RAS_OWNER_UNAVAILABLE");
  if(hart==2&&rocket_packets_)rocket_packet_redirect(cores_[hart]->get_state()->pc,"architectural-trap-entry",2);
  if(profile_.empirical){++empirical_fetch_[hart].generation;empirical_fetch_[hart].response_ready=false;}
  if(hart==2 && rocket_frontend_enabled())rocket_frontend_redirect(cores_[hart]->get_state()->pc);
  if(frontend_enabled(hart))frontend_redirect(hart,cores_[hart]->get_state()->pc,*source_ras_head);
  blocked_[hart] = true;
  iris::Op entry{hart, "trap-entry", "trap" + std::to_string(hart), profile_.trap_cycles, 1};
  entry.retires = false; entry.pc = cores_[hart]->get_state()->pc;
  entry.issue_period = profile_.harts[hart].divider;
  if (previous_[hart]) entry.deps.push_back(*previous_[hart]);
  entry.on_complete = [this, hart] { blocked_[hart] = false; ++completions_; };
  previous_[hart] = clock_.issue(std::move(entry));
}

void iris_timing_adapter::step(size_t budget) {
  uint64_t before = completions_;
  while (completions_ - before < budget) {
    compact_histories();
    if(empirical_diagnostics_&&++empirical_debug_steps_%100000==0){std::cerr<<"IRIS_CPU_PROGRESS now="<<clock_.now()<<" cachepending="<<empirical_cache_->pending()<<"\n";for(unsigned h=0;h<cores_.size();++h){const auto&p=pure_[h];std::cerr<<"HART "<<h<<" pc="<<std::hex<<cores_[h]->get_state()->pc<<std::dec<<" blocked="<<blocked_[h]<<" engaged="<<p.engaged<<" boundary="<<p.boundary<<" frontier="<<std::hex<<p.frontier<<std::dec<<" packets="<<p.packets.size()<<" next="<<p.next_commit<<" end="<<p.instructions.size()<<" fetchowner="<<empirical_fetch_[h].owner.value_or(0)<<" unitpending="<<bool(empirical_async_[h])<<"\n";}}
    frontend_prepare();
    if(profile_.saturn_live)saturn_prepare();
    if(profile_.rocket_scalar_memory)rocket_memory_after_prepare();
    rocket_frontend_resolve_mem();
    dispatch_ready();
    frontend_commit_edges();
    if(profile_.empirical_rocket_packets)rocket_packet_finish();
    auto event = clock_.next_event_cycle();
    for(unsigned hart=0;hart<2;++hart)if(frontend_enabled(hart) && (!event || frontend_[hart].next_edge<*event))event=frontend_[hart].next_edge;
    if(rocket_frontend_enabled() && (!event || rocket_frontend_.next_edge<*event))event=rocket_frontend_.next_edge;
    if(profile_.rocket_memory_fabric&&(!event||rocket_frontend_.next_uncore_edge<*event))event=rocket_frontend_.next_uncore_edge;
    if(profile_.rocket_serial){if(!event||rocket_frontend_.next_bringup_edge<*event)event=rocket_frontend_.next_bringup_edge;if(!event||rocket_frontend_.next_serial_edge<*event)event=rocket_frontend_.next_serial_edge;}
    if(profile_.source_counter_clock)for(unsigned h=0;h<source_counter_clocks_.size();++h){const auto&counter=source_counter_clocks_[h];const auto*state=cores_[h]->get_state();const bool pending=(state->mip->read()&state->mie->read())!=0;const bool wake_pending=counter.stalled()&&pending;const bool wake_edge=counter.edge()&&counter.edge()->cycle==clock_.now()&&counter.edge()->stall_before&&!counter.edge()->stall_after;if((!profile_.empirical||wake_pending||wake_edge)&&(!event||counter.next_edge()<*event))event=counter.next_edge();}
    // A pure cohort may drain after this edge's sole RRD attempt. The next
    // instruction is then a known boundary, but there is no timed stage left
    // to carry the scheduler to its next RRD edge. Preserve that real retry
    // opportunity instead of jumping to an unrelated, possibly distant timer.
    if(profile_.empirical)for(unsigned h=0;h<pure_.size();++h){const auto&p=pure_[h];if(p.engaged&&p.boundary&&p.packets.empty()&&p.last_attempt==std::optional<Cycle>(clock_.now())&&!blocked_[h]&&!empirical_branch_recovery_[h]&&!cores_[h]->is_waiting_for_interrupt()&&(!profile_.source_counter_clock||!source_counter_clocks_[h].stalled())){const auto divider=profile_.harts[h].divider;if(divider>=UINT64_MAX-clock_.now())throw std::overflow_error("IRIS_EMPIRICAL_RRD_RETRY_HORIZON");const auto retry=clock_.now()+divider;if(!event||retry<*event){event=retry;++empirical_boundary_retry_ticks_;}}}
    if(rocket_packets_)if(auto packet_edge=rocket_packets_->next_edge();packet_edge&&(!event||*packet_edge<*event))event=*packet_edge;
    auto timer = timer_deadline_();
    if (timer && (!event || *timer < *event)) event = timer;
    if (!event) {
      if(empirical_diagnostics_){std::cerr<<"NO_EVENT now="<<clock_.now()<<" host="<<host_request_()<<"\n";for(unsigned h=0;h<cores_.size();++h){const auto&p=pure_[h];const auto&f=empirical_fetch_[h];const auto*s=cores_[h]->get_state();std::cerr<<"FINAL_HART "<<h<<" pc="<<std::hex<<s->pc<<" a0="<<s->XPR.read_transport(10).value<<" a4="<<s->XPR.read_transport(14).value<<" a5="<<s->XPR.read_transport(15).value<<std::dec<<" wfi="<<cores_[h]->is_waiting_for_interrupt()<<" blocked="<<blocked_[h]<<" engaged="<<p.engaged<<" boundary="<<p.boundary<<" frontier="<<std::hex<<p.frontier<<" ready_pc="<<f.ready_pc<<std::dec<<" readybytes="<<f.ready_bytes<<" ready="<<f.response_ready<<" owner="<<f.owner.value_or(0)<<" packets="<<p.packets.size()<<"\n";}}
      // Give HTIF one opportunity to consume an exit request already stored by
      // the guest. Repeated absence of events is an explicit deadlock diagnostic.
      if (yielded_without_event_)
        throw std::runtime_error("IRIS_TIMING_NO_EVENT: all harts parked without a modeled wakeup");
      yielded_without_event_ = true;
      return;
    }
    yielded_without_event_ = false;
    if (*event > profile_.max_cycles) {
      if(empirical_diagnostics_){std::cerr<<"IRIS_PRE_MAX_EVENT now="<<clock_.now()<<" next="<<*event<<" timer="<<timer.value_or(0)<<"\n";for(unsigned h=0;h<cores_.size();++h){const auto*s=cores_[h]->get_state();const auto&p=pure_[h];std::cerr<<"IRIS_PRE_MAX_HART hart="<<h<<" pc="<<std::hex<<s->pc<<" mip="<<s->mip->read()<<" mie="<<s->mie->read()<<std::dec<<" wfi="<<cores_[h]->is_waiting_for_interrupt()<<" blocked="<<blocked_[h]<<" pure="<<p.engaged<<" boundary="<<p.boundary<<" packets="<<p.packets.size()<<" last_attempt="<<p.last_attempt.value_or(0)<<" recovery="<<empirical_branch_recovery_[h].value_or(0)<<" fetch="<<empirical_fetch_[h].owner.value_or(0);if(profile_.source_counter_clock){const auto&c=source_counter_clocks_[h];std::cerr<<" stalled="<<c.stalled()<<" blocks_rrd="<<c.blocks_rrd(clock_.now());if(c.edge())std::cerr<<" edge="<<c.edge()->cycle<<" before="<<c.edge()->stall_before<<" after="<<c.edge()->stall_after;}std::cerr<<"\n";}}
      clock_.run_until(profile_.max_cycles);
      if(empirical_diagnostics_){for(unsigned h=0;h<cores_.size();++h){const auto*s=cores_[h]->get_state();std::cerr<<"IRIS_MAX_CYCLE_HART hart="<<h<<" pc="<<std::hex<<s->pc<<" mip="<<s->mip->read()<<" mie="<<s->mie->read()<<" mstatus="<<s->mstatus->read()<<std::dec<<" wfi="<<cores_[h]->is_waiting_for_interrupt()<<" pending_loads="<<empirical_load_responses_.size()<<"\n";}}
      throw std::runtime_error("IRIS_TIMING_MAX_CYCLES");
    }
    clock_.run_until(*event);
    frontend_flush_annotations();
    if (host_request_()) return;
  }
}

void iris_timing_adapter::write_json(const std::string& path) const {
  if (path.empty()) return;
  if(!profile_.keep_history){std::ofstream out(path);if(!out)throw std::runtime_error("cannot open empirical summary");out<<"{\"schema\":\"iris.empirical.summary.v1\",\"status\":\"experimental_uncalibrated\",\"cycles\":"<<clock_.now()<<",\"history_mode\":\"bounded\",\"retained_nodes\":"<<clock_.retained_nodes()<<",\"retired_instructions\":[";for(unsigned h=0;h<retired_.size();++h){if(h)out<<',';out<<retired_[h];}out<<"],\"completed_model_operations\":"<<clock_.completed_total()<<",\"calibrated_2pct\":false";empirical_write_totals(out);write_frontend_json(out);out<<",\"base_clock_hz\":"<<profile_.base_hz<<",\"hart_cycle_dividers\":[";for(unsigned h=0;h<profile_.harts.size();++h){if(h)out<<',';out<<profile_.harts[h].divider;}out<<"]}\n";return;}
  std::ofstream out(path);
  if (!out) throw std::runtime_error("cannot open timing graph output: " + path);
  std::ostringstream graph; clock_.write_json(graph, true);
  auto text = graph.str(); text.pop_back();
  out << text << ",\"timing_mode\":\"uncalibrated-integration-fixture\",\"base_clock_hz\":"
      << profile_.base_hz << ",\"clock_source\":" << std::quoted(profile_.source)
      << ",\"completed_events\":" << completions_ << ",\"hart_cycle_dividers\":[";
  for (size_t i = 0; i < profile_.harts.size(); ++i) { if (i) out << ','; out << profile_.harts[i].divider; }
  out << "],\"retired_instructions\":[";
  for (size_t i = 0; i < retired_.size(); ++i) { if (i) out << ','; out << retired_[i]; }
  out << "],\"schedule_seed\":" << (seed_ ? std::to_string(*seed_) : "null")
      << ",\"traffic_accounting\":\"not_instrumented\",\"arithmetic_accounting\":\"not_instrumented\",\"memory_transactions\":[";
  for (size_t i=0;i<memory_transfers_.size();++i) {
    if (i) out<<',';
    const auto& row=memory_transfers_[i];const auto& t=row.transfer;
    out<<"{\"hart\":"<<row.hart<<",\"address\":"<<t.address<<",\"access_bytes\":"<<t.access_bytes
       <<",\"kind\":"<<std::quoted(row.kind==iris::AccessKind::load?"load":row.kind==iris::AccessKind::store?"store":
            row.kind==iris::AccessKind::lr?"lr":row.kind==iris::AccessKind::sc?"sc":"amo")
       <<",\"path\":"<<std::quoted(t.path)<<",\"stages\":[";
    for (size_t j=0;j<t.nodes.size();++j) {
      if (j) out<<',';
      const auto& p=t.parameters[j];const auto& s=p.parameters;
      const auto& node=clock_.nodes().at(t.nodes[j]);
      out<<"{\"node\":"<<t.nodes[j]<<",\"name\":"<<std::quoted(s.name)<<",\"resource\":"<<std::quoted(s.resource)
         <<",\"state\":"<<std::quoted(node.completed?"completed":node.issued?"inflight":"pending")
         <<",\"included_in_events\":"<<((node.completed||(node.issued&&node.start<clock_.now()))?"true":"false")
         <<",\"scheduled_start\":"<<(node.issued?std::to_string(node.start):"null")
         <<",\"scheduled_end\":"<<(node.issued?std::to_string(node.end):"null")
         <<",\"first_beat_latency\":"<<s.first_beat_latency<<",\"launch_interval\":"<<s.launch_interval
         <<",\"bytes\":"<<s.bytes<<",\"beat_bytes\":"<<s.beat_bytes<<",\"beat_interval\":"<<s.beat_interval
         <<",\"issue_period\":"<<s.issue_period
         <<",\"derived_latency\":"<<p.derived_latency<<",\"derived_interval\":"<<p.derived_interval
         <<",\"source\":"<<std::quoted(s.source)<<",\"port_source\":"<<std::quoted(p.port_source)<<'}';
    }
    out<<"]}";
  }
  out<<"]";
  if(profile_.empirical)empirical_write_totals(out);
  write_counter_reads(out);
  write_pure_json(out);
  write_rocket_json(out);
  write_frontend_json(out);
  write_source_counter_json(out);
  write_rocket_frontend_json(out);
  write_rocket_packet_json(out);
  write_rocket_fabric_json(out);
  write_saturn_json(out);
  out<<"}\n";
}

void iris_timing_adapter::compact_histories(){
 if(profile_.keep_history)return;
 for(auto&p:pure_){
  while(!p.instructions.empty()&&p.instructions.base()<p.first_live&&p.instructions.front().released){
   const auto id=p.instructions.base();for(auto&writer:p.last_writer)if(writer==std::optional<size_t>(id))writer.reset();
   p.instructions.pop_front();
  }
 }
}

#include "iris_empirical_features.inc"
#include "iris_empirical_branch.inc"
#include "iris_opu_entry_overlap.inc"
#include "iris_empirical_async.inc"
#include "iris_empirical_icache.inc"
#include "iris_empirical_load.inc"
#include "iris_empirical_store.inc"

#include "iris_vector_store_capture.inc"
