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
      } else if(key=="counter_policy" && f.size()==2) {
        if(!singleton.insert(key).second || f[1]!="source-ungated-stall")throw std::runtime_error("unsupported source counter policy");
        p.source_counter_clock=true;
      } else if(key=="shuttle_scalar_memory"&&f.size()==2){
        if(!singleton.insert(key).second||f[1]!="source-cache-serialized-M-mode")throw std::runtime_error("unsupported Shuttle scalar memory path");p.shuttle_scalar_memory=true;
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
        if(!singleton.insert(key).second || f[1]!="saved-rtl-M-mode")throw std::runtime_error("unsupported source frontend");
        p.saved_shuttle_frontend=true;p.frontend_seed=number(f[2]);p.frontend_reset_edges=number(f[3]);
        if(!p.frontend_seed || p.frontend_seed>INT32_MAX || p.frontend_reset_edges<2 || p.frontend_reset_edges>1024)throw std::runtime_error("explicit source reset edges required");
      } else if(key=="icache_service" && f.size()==5) {
        if(!singleton.insert(key).second || f[1]!="synthetic")throw std::runtime_error("only explicitly synthetic external service accepted by this fixture");
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
  if(p.shuttle_scalar_memory&&!p.rocket_serial)throw std::runtime_error("IRIS_SHUTTLE_SOURCE_REQUIRES_SHARED_SERIAL_SYSTEM");
  if(p.rocket_serial){
    if(singleton.count("rocket_fabric")||!singleton.count("serial_cbus_fixture")||!p.rocket_scalar_memory||!p.source_counter_clock||p.base_hz!=1000000000ULL)throw std::runtime_error("Serial source mode requires distinct explicit CBUS fixture, scalar memory, source counters and 1GHz virtual phase calendar");
    for(const auto&h:p.harts)if(h.divider!=2)throw std::runtime_error("Serial saved-reference requires all three source core periods2");
  }else if(singleton.count("serial_cbus_fixture"))throw std::runtime_error("CBUS fixture without source serial path");
  if(p.saved_rocket_frontend && (!p.saved_shuttle_frontend || !p.rocket_pure_pipeline || !p.private_forwarded_values))throw std::runtime_error("Rocket source frontend requires source Shuttle frontend and private integer pipeline");
  if(p.rocket_scalar_memory&&!p.rocket_memory_fabric)throw std::runtime_error("source scalar memory requires source fabric");
  if(p.rocket_memory_fabric&&(!p.saved_rocket_frontend||p.base_hz%p.fabric_uncore_divider||p.fabric_uncore_divider!=p.harts.at(2).divider))throw std::runtime_error("source fabric requires actual Rocket frontend and explicit integral uncore clock");
  if(p.source_counter_clock && !p.saved_shuttle_frontend)throw std::runtime_error("source counter policy currently requires source frontend scope");
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
  pure_.resize(cores_.size());
  if(profile_.source_counter_clock)for(const auto& hart:profile_.harts)source_counter_clocks_.emplace_back(hart.divider);
  counter_sequences_.resize(cores_.size(),0);
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
      clock_.configure_resource(prefix + "CSR_EX", 1);
      clock_.configure_resource(prefix + "MEM_ALU", 1);
      clock_.configure_resource(prefix + "COM", 2);
      clock_.configure_resource(prefix + "WB", 2);
    }
    if (profile_.rocket_pure_pipeline && i==2) {
      if (cores_[i]->get_const_xlen()!=64) throw std::runtime_error("IRIS_ROCKET_PIPELINE_REQUIRES_RV64");
      for (const auto* stage:{"EX","MEM","WB"}) clock_.configure_resource("rocket2."+std::string(stage),1);
    }
  }
  clock_.on_advance(std::move(advance));
  frontend_initialize();
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
  if(profile_.shuttle_scalar_memory&&hart<2){const auto bits=frontend_[hart].outputs.queue[0].expanded;const auto opcode=bits&127;
    if(opcode==3||opcode==0x23||(bits&0x707f)==0x000f)shuttle_memory_issue(hart,pc,fetch,bits);
    if(opcode==0x2f||opcode==7||opcode==0x27)throw std::runtime_error("IRIS_SHUTTLE_SOURCE_SERIALIZED_DATA_OPCODE_UNQUALIFIED");}
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
  pending_[hart] = Pending{pc, fetch, {}}; blocked_[hart] = true;
  iris::Op op{hart, selected->name, selected->resource, selected->latency, selected->interval};
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
    try { cores_[hart]->step(1); }
    catch (...) { completion_reads_.clear(); completing_node_.reset(); completing_.reset(); throw; }
    finish_counter_reads(hart,retired_before);
    if(frontend_enabled(hart)) {
      if(retired_[hart]==retired_before+1)frontend_boundary_complete(hart,pending_[hart]->pc,pending_[hart]->fetch);
      else frontend_[hart].conservative.reset(); // exception owns redirect/zero RAS, below
    }
    if(hart==2 && rocket_frontend_enabled()) {
      if(retired_[hart]==retired_before+1)rocket_frontend_boundary_complete(pending_[hart]->pc,pending_[hart]->fetch);
      else rocket_frontend_.conservative.reset();
    }
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
  pending_[hart]->completion_node=previous_[hart];
  throw iris_timing_wait{};
}

void iris_timing_adapter::dispatch_ready() {
  if (seed_) std::shuffle(order_.begin(), order_.end(), rng_);
  for (unsigned hart : order_) {
    if (blocked_[hart]) continue;
    if(profile_.source_counter_clock && (clock_.now()%profile_.harts[hart].divider || source_counter_clocks_[hart].blocks_rrd(clock_.now())))continue;
    if (((profile_.shuttle_pure_pipeline && hart<2) || (profile_.rocket_pure_pipeline && hart==2)) && pure_[hart].engaged) {
      pure_dispatch(hart);
      if (pure_[hart].engaged) continue;
    }
    auto* core = cores_[hart]; auto* state = core->get_state();
    if(frontend_enabled(hart)) {
      const auto& f=frontend_[hart];
      if(!f.prepared || f.inputs.redirect_flush || !f.outputs.queue[0].valid)continue;
      if(f.outputs.queue[0].pc!=state->pc)throw std::runtime_error("IRIS_FRONTEND_ARCHITECTURAL_QUEUE_PC_MISMATCH hart="+std::to_string(hart)+" queue="+std::to_string(f.outputs.queue[0].pc)+" architectural="+std::to_string(state->pc));
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
    } else core->step(1);
    if (blocked_[hart] || pure_[hart].engaged || core->is_waiting_for_interrupt()) continue;
    // A fetch/interrupt/architectural trap can happen before instruction issue.
    // Its state transition is local; the handler cannot run until this event ends.
    queue_trap(hart);
  }
}
void iris_timing_adapter::queue_trap(unsigned hart) {
  if(hart==2 && rocket_frontend_enabled())rocket_frontend_redirect(cores_[hart]->get_state()->pc);
  if(frontend_enabled(hart))frontend_redirect(hart,cores_[hart]->get_state()->pc);
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
    frontend_prepare();
    if(profile_.rocket_scalar_memory)rocket_memory_after_prepare();
    rocket_frontend_resolve_mem();
    dispatch_ready();
    frontend_commit_edges();
    auto event = clock_.next_event_cycle();
    for(unsigned hart=0;hart<2;++hart)if(frontend_enabled(hart) && (!event || frontend_[hart].next_edge<*event))event=frontend_[hart].next_edge;
    if(rocket_frontend_enabled() && (!event || rocket_frontend_.next_edge<*event))event=rocket_frontend_.next_edge;
    if(profile_.rocket_memory_fabric&&(!event||rocket_frontend_.next_uncore_edge<*event))event=rocket_frontend_.next_uncore_edge;
    if(profile_.rocket_serial){if(!event||rocket_frontend_.next_bringup_edge<*event)event=rocket_frontend_.next_bringup_edge;if(!event||rocket_frontend_.next_serial_edge<*event)event=rocket_frontend_.next_serial_edge;}
    if(profile_.source_counter_clock)for(const auto& clock:source_counter_clocks_)if(!event || clock.next_edge()<*event)event=clock.next_edge();
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
    frontend_flush_annotations();
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
  write_counter_reads(out);
  write_pure_json(out);
  write_rocket_json(out);
  write_frontend_json(out);
  write_source_counter_json(out);
  write_rocket_frontend_json(out);
  write_rocket_fabric_json(out);
  if(profile_.shuttle_scalar_memory)write_shuttle_memory_json(out);
  out<<"}\n";
}
