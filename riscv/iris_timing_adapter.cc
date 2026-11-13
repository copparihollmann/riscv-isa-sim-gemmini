#include "iris_timing_adapter.h"
#include <fstream>
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
      } else if (key == "shuttle_pipeline" && f.size() == 2) {
        if (!singleton.insert(key).second || (f[1] != "pure-integer-sequential-frontend" && f[1] != "pure-integer-rvc-sequential-frontend"))
          throw std::runtime_error("unsupported experimental Shuttle pipeline fixture");
        p.shuttle_pure_pipeline = true;
        p.shuttle_rvc_pipeline = f[1] == "pure-integer-rvc-sequential-frontend";
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
        auto id = number(f[1]), divider = number(f[2]), idle = number(f[3]);
        if (id >= count || !divider || idle > 1 || p.harts[id].divider)
          throw std::runtime_error("invalid/duplicate hart clock");
        p.harts[id] = {divider, bool(idle)};
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
  if (p.shuttle_pure_pipeline && count != 3)
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
  pure_.resize(cores_.size());
  for (const auto& resource : profile_.resources) clock_.configure_resource(resource.first, resource.second);
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
    clock_.configure_resource("trap" + std::to_string(i), 1);
    if (profile_.shuttle_pure_pipeline && i < 2) {
      if (cores_[i]->get_const_xlen() != 64)
        throw std::runtime_error("IRIS_PIPELINE_REQUIRES_RV64");
      const auto prefix = "shuttle" + std::to_string(i) + ".";
      clock_.configure_resource(prefix + "EX", 2);
      clock_.configure_resource(prefix + "MEM_ALU", 1);
      clock_.configure_resource(prefix + "COM", 2);
      clock_.configure_resource(prefix + "WB", 2);
    }
  }
  clock_.on_advance(std::move(advance));
}
void iris_timing_adapter::retired(unsigned hart, size_t count) { retired_.at(hart) += count; }

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
  if (blocked_.at(hart)) throw std::logic_error("second in-flight instruction in conservative adapter");
  if (pure_begin(hart, pc, fetch)) throw iris_timing_wait{};
  const Rule* selected = nullptr;
  auto instruction = fetch.insn;
  for (const auto& rule : profile_.rules)
    if (rule.hart == hart && (uint32_t(instruction.bits()) & rule.mask) == rule.match) { selected = &rule; break; }
  if (!selected) throw std::runtime_error("IRIS_TIMING_UNMODELED_INSTRUCTION hart=" + std::to_string(hart));
  iris::ScalarAccess access;
  if (memory_routes_) {
    std::array<uint64_t,32> registers;
    const auto* state=cores_[hart]->get_state();
    for (unsigned i=0;i<32;++i) registers[i]=state->XPR[i];
    access=iris::scalar_memory_access(uint32_t(instruction.bits()),registers);
    if (access.decode==iris::MemoryDecode::vector || access.decode==iris::MemoryDecode::unresolved)
      throw std::runtime_error("IRIS_TIMING_MEMORY_OPERATION_UNMODELED hart="+std::to_string(hart));
    if (access.decode==iris::MemoryDecode::scalar &&
        (state->prv!=PRV_M || state->v || state->debug_mode || (state->mstatus->read()&MSTATUS_MPRV)))
      throw std::runtime_error("IRIS_TIMING_TRANSLATED_MEMORY_UNMODELED hart="+std::to_string(hart));
  }
  pending_[hart] = Pending{pc, fetch}; blocked_[hart] = true;
  iris::Op op{hart, selected->name, selected->resource, selected->latency, selected->interval};
  op.pc = pc; op.retires = false; op.issue_period = profile_.harts[hart].divider;
  if (previous_[hart]) op.deps.push_back(*previous_[hart]);
  op.on_complete = [this, hart] {
    if (cores_[hart]->get_state()->pc != pending_[hart]->pc)
      throw std::runtime_error("IRIS_TIMING_PC_CHANGED_DURING_FLIGHT");
    completing_ = hart;
    const auto retired_before = retired_[hart];
    try { cores_[hart]->step(1); }
    catch (...) { completing_.reset(); throw; }
    completing_.reset(); pending_[hart].reset(); blocked_[hart] = false; ++completions_;
    if (retired_[hart] == retired_before) queue_trap(hart);
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
  throw iris_timing_wait{};
}

void iris_timing_adapter::dispatch_ready() {
  if (seed_) std::shuffle(order_.begin(), order_.end(), rng_);
  for (unsigned hart : order_) {
    if (blocked_[hart]) continue;
    if (profile_.shuttle_pure_pipeline && hart < 2 && pure_[hart].engaged) {
      pure_dispatch(hart);
      if (pure_[hart].engaged) continue;
    }
    auto* core = cores_[hart]; auto* state = core->get_state();
    if (core->is_waiting_for_interrupt() && !(state->mip->read() & state->mie->read())) continue;
    core->step(1);
    if (blocked_[hart] || pure_[hart].engaged || core->is_waiting_for_interrupt()) continue;
    // A fetch/interrupt/architectural trap can happen before instruction issue.
    // Its state transition is local; the handler cannot run until this event ends.
    queue_trap(hart);
  }
}
void iris_timing_adapter::queue_trap(unsigned hart) {
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
    dispatch_ready();
    auto event = clock_.next_event_cycle();
    auto timer = timer_deadline_();
    if (timer && (!event || *timer < *event)) event = timer;
    if (!event) {
      // Give HTIF one opportunity to consume an exit request already stored by
      // the guest. Repeated absence of events is an explicit deadlock diagnostic.
      if (yielded_without_event_)
        throw std::runtime_error("IRIS_TIMING_NO_EVENT: all harts parked without a modeled wakeup");
      yielded_without_event_ = true;
      return;
    }
    yielded_without_event_ = false;
    if (*event > profile_.max_cycles) {
      clock_.run_until(profile_.max_cycles);
      throw std::runtime_error("IRIS_TIMING_MAX_CYCLES");
    }
    clock_.run_until(*event);
    if (host_request_()) return;
  }
}

void iris_timing_adapter::write_json(const std::string& path) const {
  if (path.empty()) return;
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
  write_pure_json(out);
  out<<"}\n";
}
