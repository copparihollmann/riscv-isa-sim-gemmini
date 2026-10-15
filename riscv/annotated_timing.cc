#include "../timing/observer.hpp"
#include "cpu_decode.hpp"
#include "memory.hpp"
#include "model.hpp"
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
  std::string report_path, elf_digest, input_digest;
  std::map<std::string, std::uint64_t> features;
  std::set<std::string> unresolved;
  std::unique_ptr<MemorySystem> memory;
  std::unique_ptr<Services> services;
  std::unique_ptr<TargetProvider> target;
  ValueId next_token = 67;
  std::optional<Cycle> pending_flags = Cycle{0};
  std::array<bool,64> time_dependent{};
  bool temporal_rounding = false, temporal_flags = false;
  std::uint64_t instructions = 0, aborted_instructions = 0;
  std::uint64_t pc = 0, bits = 0, first_counter_pc = 0, first_counter_instruction = 0;
  unsigned accelerator_depth = 0;
  bool in_instruction = false, finished = false, counter_pending = false;
  bool access_overflow = false, command_pending = false, trapped = false;
  std::array<std::uint64_t, 4> command{};
  std::vector<MemoryEffect> accesses;
  std::function<unsigned(std::uint64_t, std::size_t)> memory_kind;
  std::vector<CounterWindow> windows;
  std::vector<std::string> library_digests;
  bool isa_checked = false;
  std::optional<Cycle> first_counter;
  std::map<std::string, std::uint64_t> first_counter_features;

  Impl(const std::string &path, const std::string &output, const std::string &elf,
       const std::string &input, const std::vector<std::string> &libraries,
       std::function<unsigned(std::uint64_t, std::size_t)> classify,
       const std::string &scope_binding)
      : model(path), engine(model.max_values, model.resources), report_path(output),
        elf_digest(sha256_file(elf)), input_digest(input), memory_kind(std::move(classify)) {
    model.bind_scope(scope_binding, elf_digest, input_digest);
    for (const auto *name : cpu_feature_classes) {
      add_feature(name, 0);
      const std::string kind(name);
      if (kind.compare(0, 7, "cpu.fp_") == 0 || kind == "cpu.int_to_fp")
        for (const auto width : {32, 64}) add_feature(kind + ".f" + std::to_string(width), 0);
    }
    for (const auto *name : {"cpu.fp_convert.f32_to_f64", "cpu.fp_convert.f64_to_f32",
                             "cpu.branch_taken", "cpu.branch_not_taken"}) add_feature(name, 0);
    issue_resource = model.resource("cpu.issue");
    issue_cost = model.cycles("cpu.issue_cycles");
    branch_taken = model.cycles("cpu.branch.taken_penalty_cycles");
    branch_not_taken = model.cycles("cpu.branch.not_taken_penalty_cycles");
    if (input_digest.empty()) unknown("external input identity is unspecified");
    else if (!is_digest(input_digest)) throw std::invalid_argument("invalid input SHA-256");
    if (model.domain.at("feature_engine_sha256") != SPIKE_TIMING_SOURCE_SHA256)
      unknown("feature engine source identity differs from selected profile");
    for (const auto &library : libraries) library_digests.push_back(sha256_file(library));
    std::vector<std::string> expected_libraries;
    if (const auto expected = model.document.get_child_optional("libraries"))
      for (const auto &entry : *expected) {
        if (!is_digest(entry.second.data())) throw std::invalid_argument("invalid library digest");
        expected_libraries.push_back(entry.second.data());
      }
    if (library_digests != expected_libraries)
      unknown("loaded functional or timing libraries differ from selected profile");
    auto allocate = [this](std::size_t count) { return allocate_tokens(count); };
    auto feature = [this](const std::string &name, std::uint64_t count) { add_feature(name, count); };
    auto missing = [this](const std::string &reason) { unknown(reason); };
    memory = std::make_unique<MemorySystem>(model, engine, allocate, feature, missing);
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
          unknown("device transfer outside stable RAM is unsupported"); return SharedEffects{};
        }
        return memory->access(effects, "device");
      },
      feature, missing,
    });
    const auto factory = reinterpret_cast<CreateProvider>(dlsym(RTLD_DEFAULT, "spike_timing_create_provider_v1"));
    if (factory) {
      target.reset(factory(services.get()));
      if (!target) throw std::runtime_error("timing provider factory returned no provider");
    }
    accesses.reserve(std::min<std::size_t>(model.max_accesses_per_instruction, 64));
    namespace fs = std::filesystem;
    if (fs::is_symlink(report_path)) throw std::invalid_argument("timing output must be an ordinary file");
    if (fs::exists(report_path)) {
      if (!fs::is_regular_file(report_path) || fs::equivalent(report_path, path) || fs::equivalent(report_path, elf))
        throw std::invalid_argument("timing output conflicts with an input or nonregular file");
      std::ifstream old(report_path); std::array<char,128> prefix{};
      old.read(prefix.data(),prefix.size());
      if (std::string(prefix.data(),old.gcount()).find("merlin.annotated_spike_report.v1") == std::string::npos)
        throw std::invalid_argument("timing output would replace a nonreport file");
    }
    std::ofstream pending(report_path, std::ios::binary | std::ios::trunc);
    if (!pending || !(pending << "{\"schema\":\"merlin.annotated_spike_report.v1\",\"timing_complete\":false,\"status\":\"running\"}\n"))
      throw std::runtime_error("cannot initialize incomplete timing output");
  }
  CpuCost cpu_cost(const std::string &priced, const std::string &kind) {
    const auto cached = cpu_costs.find(priced);
    if (cached != cpu_costs.end()) return cached->second;
    if (cpu_costs.size() >= 128) throw std::runtime_error("CPU cost cache budget exceeded");
    CpuCost cost{model.cycles(priced + ".latency_cycles"), model.cycles(priced + ".occupancy_cycles"), {}};
    const auto resources = model.document.get_child_optional("cpu_execution_resources");
    if (resources) {
      const auto selected = resources->find(kind);
      if (selected != resources->not_found()) cost.resource = model.resource(selected->second.data());
    }
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
  void add_feature(const std::string &name, std::uint64_t amount) {
    if (features.size() >= 512 && !features.count(name))
      throw std::runtime_error("timing feature budget exceeded");
    auto &value = features[name];
    if (amount > std::numeric_limits<std::uint64_t>::max() - value) {
      unknown("feature counter overflow"); return;
    }
    value += amount;
  }
  void begin(processor_t *processor, std::uint64_t address, std::uint64_t instruction) {
    if (in_instruction) throw std::logic_error("nested architectural instruction observation");
    in_instruction = true; pc = address; bits = instruction;
    accesses.clear(); access_overflow = false; command_pending = false;
    const auto decoded = decode_cpu(bits);
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
      bool supported = isa.compare(0, 4, "rv64") == 0 && !base.empty() && base.find_first_not_of("imafdc") == std::string::npos;
      std::istringstream extensions(split == std::string::npos ? "" : isa.substr(split + 1));
      std::string extension;
      while (std::getline(extensions, extension, '_'))
        if (extension != "zicsr" && extension != "zifencei" && extension != "zicntr" && extension != "zihpm") supported = false;
      if (!supported) unknown("architectural extensions are outside the supported scalar timing domain");
      if (model.document.get<std::string>("cpu.isa", "") != isa)
        unknown("architectural ISA differs from selected timing profile");
    }
    if (decoded.floating_register_operands &&
        (processor->get_isa().extension_enabled(EXT_ZFINX) ||
         processor->get_isa().extension_enabled(EXT_ZDINX)))
      unknown("floating operands in integer registers are outside this timing domain");
    if (processor->get_state()->mstatus->read() & MSTATUS_MPRV)
      unknown("effective data privilege translation is outside the baremetal timing domain");
    if (processor->get_xlen() != 64 || processor->get_state()->prv != 3)
      unknown("timing profile currently requires single-hart RV64 baremetal execution");
  }
  void record_memory(std::uint64_t address, std::size_t bytes, access_type type) {
    if (!in_instruction || accelerator_depth || type == FETCH) return;
    if (accesses.size() >= model.max_accesses_per_instruction) {
      access_overflow = true; return;
    }
    const auto kind = memory_kind(address, bytes);
    if (!kind || (kind == 2 && type == STORE)) {
      unknown("unmodeled MMIO or nonstable memory access"); access_overflow = true; return;
    }
    accesses.push_back({address, bytes, type == STORE, kind == 2});
  }
  void abort_instruction(bool trap = true) noexcept {
    if (trap) { trapped = true; if (in_instruction) ++aborted_instructions; }
    in_instruction = false; accelerator_depth = 0; command_pending = false; accesses.clear();
  }
  void finish_instruction(std::uint64_t next_pc, bool committed) {
    if (!committed) { abort_instruction(false); return; }
    if (!in_instruction) throw std::logic_error("instruction completion has no matching begin");
    in_instruction = false;
    if (instructions == std::numeric_limits<std::uint64_t>::max())
      throw std::overflow_error("executed instruction count overflow");
    ++instructions;
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
    const auto csr_address = (bits >> 20) & 4095;
    const bool clock_csr = (bits & 127) == 0x73 && ((bits >> 12) & 7) &&
        ((csr_address >= 0xc00 && csr_address <= 0xc1f) ||
         (csr_address >= 0xb00 && csr_address <= 0xb1f));
    bool temporal = clock_csr;
    const auto csr_mode = (bits >> 12) & 7;
    if (clock_csr && (csr_mode == 1 || csr_mode == 5 || ((bits >> 15) & 31)))
      unknown("writes to architectural performance counters are outside the timing trace contract");
    for (unsigned i=0; i<decoded.read_count; ++i) temporal = temporal || time_dependent[decoded.reads[i]];
    if (decoded.reads_rounding_mode) temporal = temporal || temporal_rounding;
    if (decoded.reads_fflags) temporal = temporal || temporal_flags;
    if (decoded.writes_rounding_mode) temporal_rounding = temporal;
    if (decoded.writes_fflags) temporal_flags = temporal;
    if (decoded.accumulates_fflags) temporal_flags = temporal_flags || temporal;
    if (temporal && (bits & 127) == 0x73 && !clock_csr && csr_address > 3)
      unknown("counter-derived architectural state is outside the timing trace contract");
    if (temporal && (decoded.branch || !accesses.empty() || decoded.custom))
      unknown("counter-derived control, address or stored data is outside the timing trace contract");
    for (unsigned i=0; i<decoded.write_count; ++i) time_dependent[decoded.writes[i]] = temporal;
    if (!decoded.known) unknown("unsupported CPU instruction semantics");
    if (access_overflow) unknown("instruction memory observation budget exceeded");
    if (accelerator_depth && !(decoded.custom && accelerator_depth == 1)) {
      unknown("accelerator observation begin/end is incomplete"); accelerator_depth = 0;
    }
    accelerator_depth = 0;
    if (decoded.fence) {
      if (target) target->fence(engine.issue_frontier().value_or(0));
      engine.barrier();
      if (decoded.icache_fence) memory->instruction_fence();
    }
    const auto instruction_bytes = (bits & 3) == 3 ? 4u : 2u;
    const auto instruction_space = memory_kind(pc, instruction_bytes);
    SharedEffects fetch;
    if (!instruction_space) unknown("instruction fetch outside stable memory is unsupported");
    else fetch = memory->access({MemoryEffect{pc, instruction_bytes, false, instruction_space == 2}}, "cpu_fetch");
    const ValueId fetch_token = 64;
    fetch.writes.push_back(fetch_token);
    Event fetch_event{0, view(fetch.reads), view(fetch.writes), view(fetch.demands), fetch.latency, true};
    engine.submit(fetch_event);

    auto data = memory->access(accesses, "cpu_data");
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
    const auto cpu = engine.submit(event);
    if (decoded.accumulates_fflags)
      pending_flags = pending_flags && cpu.ready ?
          std::optional<Cycle>{std::max(*pending_flags, *cpu.ready)} : std::nullopt;
    if (decoded.writes_fflags) pending_flags = cpu.ready;
    if (decoded.custom) {
      if (!target || !command_pending) unknown("custom instruction has no successful target observation");
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
    } else if (command_pending) unknown("target command was attached to a non-custom instruction");
    if (decoded.counter_read && (!model.scope_pc_pair || pc == model.scope_begin_pc || pc == model.scope_end_pc)) {
      const bool opening = model.scope_pc_pair ? pc == model.scope_begin_pc : !counter_pending;
      if (opening) {
        if (counter_pending) unknown("counter scope opened again before completion");
        counter_pending = true; first_counter = cpu.start;
        first_counter_pc = pc; first_counter_instruction = instructions;
        first_counter_features = features;
      } else {
        if (!counter_pending) { unknown("counter scope closed without its opening boundary"); return; }
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
        windows.push_back({first_counter_pc, pc, instructions - first_counter_instruction, elapsed, std::move(scoped),
                           selected ? unresolved : std::set<std::string>{}, engine.report().complete && !trapped});
        counter_pending = false;
      }
    }
  }
  void write_report(int exit_code, bool completed) {
    if (finished) throw std::logic_error("timing report already finalized");
    finished = true;
    if (in_instruction) unknown("instruction observation is unfinished");
    if (trapped) unknown("trapping instruction timing and exception transition are unsupported");
    const auto observed = engine.report();
    if (counter_pending) unknown("unmatched cycle counter boundary");
    std::optional<Cycle> estimate = observed.modeled_makespan;
    const auto scope_kind = model.document.get<std::string>("scope.kind");
    if (scope_kind == "counter_pair" || scope_kind == "counter_pc_pair") {
      const auto index = model.scope_window;
      if (index >= windows.size()) { unknown("selected counter window was not executed"); estimate.reset(); }
      else estimate = windows[index].cycles;
    } else if (scope_kind != "whole_program") {
      unknown("unsupported measurement boundary"); estimate.reset();
    }
    const bool scoped = scope_kind != "whole_program" && model.scope_window < windows.size();
    const auto scope_features = scoped ? &windows[model.scope_window].features : &features;
    const auto &scope_reasons = scoped ? windows[model.scope_window].unresolved : unresolved;
    const bool event_complete = scoped ? windows[model.scope_window].timing_complete : observed.complete;
    const bool complete = completed && event_complete && scope_reasons.empty() && exit_code == 0 && estimate.has_value();
    const std::string estimated_json = complete ? std::to_string(estimate.value_or(0)) : "null";
    std::ostringstream out;
    out << "{\"schema\":\"merlin.annotated_spike_report.v1\",\"profile\":" << json_string(model.profile)
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
        << ",\"instructions\":" << instructions << ",\"aborted_instructions\":" << aborted_instructions
        << ",\"memory_dependency_entries\":" << memory->pending_tokens()
        << ",\"feature_counts\":{";
    bool first = true;
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
    out << "],\"whole_trace_timing_complete\":" << (observed.complete && unresolved.empty() ? "true" : "false")
        << ",\"cycle_breakdown\":{\"scope\":\"whole_trace\",\"additive\":false,\"modeled_horizon\":" << observed.modeled_makespan
        << ",\"resources\":["; first = true;
    for (const auto &resource : observed.resources) {
      if (!first) out << ',';
      first = false;
      out << "{\"resource_id\":" << resource.id << ",\"reservations\":" << resource.reservations
          << ",\"busy_unit_cycles\":" << cycle_json(resource.busy_unit_cycles)
          << ",\"unknown_events\":" << resource.unknown_events
          << ",\"peak_queue_entries\":" << resource.peak_queue_entries << '}';
    }
    out << "]}";
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
                 const std::string &scope_binding)
    : impl_(std::make_unique<Impl>(model, report, elf, input_digest, libraries, std::move(memory_kind), scope_binding)) {
  if (active) throw std::logic_error("only one annotated session is supported");
  active = this;
}
Session::~Session() { if (active == this) active = nullptr; }
bool enabled() noexcept { return active != nullptr; }
void before(processor_t *p, std::uint64_t pc, std::uint64_t bits) { active->impl_->begin(p, pc, bits); }
void after(std::uint64_t pc, bool committed) { active->impl_->finish_instruction(pc, committed); }
void aborted() noexcept { if (active) active->impl_->abort_instruction(); }
bool Session::interested_in_range(std::uint64_t, std::uint64_t, access_type type) { return type != FETCH; }
void Session::trace(std::uint64_t address, std::size_t bytes, access_type type) { impl_->record_memory(address, bytes, type); }
void Session::clean_invalidate(std::uint64_t, std::size_t, bool, bool) { impl_->unknown("cache-block maintenance semantics are unsupported"); }
void Session::finish(int exit_code, bool completed) { impl_->write_report(exit_code, completed); }
} // namespace spike_timing
