// Optional adapter to the generic Spike timing plugin ABI. This translation
// unit can be loaded separately beside the unchanged functional extension.
#include "provider.hpp"
#include "staged.hpp"
#include "instruction_suffix.hpp"
#include "posted.hpp"
#include "command_ingress.hpp"
#include <timing/provider.hpp>

#include <memory>
#include <set>

namespace {
namespace G = gemmini_annotated_spike;
using spike_timing::Services;

struct CounterFeature {
  const char *name;
  std::uint64_t G::Counters::*member;
};
constexpr CounterFeature counter_features[] = {
    {"commands", &G::Counters::commands_total}, {"fences", &G::Counters::fences},
    {"load_publication.packet_per_row", &G::Counters::load_packet_per_row_publication},
    {"load_publication.packet_command_boundary", &G::Counters::load_packet_command_publication},
    {"load_publication.row_stream_command_boundary", &G::Counters::load_row_stream_publication},
    {"load_publication.aggregate_fallback", &G::Counters::load_aggregate_publication},
    {"load_publication.unsupported", &G::Counters::load_unsupported_publication},
    {"requested_read_bytes", &G::Counters::requested_read_bytes},
    {"requested_write_bytes", &G::Counters::requested_write_bytes},
    {"local_read_bytes", &G::Counters::local_read_bytes}, {"local_write_bytes", &G::Counters::local_write_bytes},
    {"nominal_padded_macs", &G::Counters::nominal_padded_macs}, {"useful_shape_macs", &G::Counters::useful_shape_macs},
    {"zero_fill_elements", &G::Counters::zero_fill_elements}, {"pooled_outputs", &G::Counters::pooled_outputs},
    {"semantic_unknown_events", &G::Counters::semantic_unknown_events}, {"illegal_events", &G::Counters::illegal_events}};

std::uint32_t integer(Services &s, const std::string &name) {
  const auto value = s.number("target.hardware." + name);
  if (!value || !std::isfinite(*value) || *value < 0 || std::floor(*value) != *value ||
      *value > std::numeric_limits<std::uint32_t>::max())
    throw std::invalid_argument("missing or invalid target hardware fact: " + name);
  return static_cast<std::uint32_t>(*value);
}

G::HardwareConfig hardware(Services &s) {
  const auto first = integer(s, "first_layer_optimizations");
  const auto full = integer(s, "full_width_accumulator_readout");
  if (first > 1 || full > 1) throw std::invalid_argument("invalid target feature fact");
  std::optional<std::uint8_t> activation;
  const auto selected = s.number("target.hardware.reset_accumulator_activation");
  if (selected) {
    if (!std::isfinite(*selected) || *selected < 0 || *selected > 4 || std::floor(*selected) != *selected)
      throw std::invalid_argument("invalid reset activation fact");
    activation = static_cast<std::uint8_t>(*selected);
  }
  std::optional<bool> normalizations;
  const auto norms = s.number("target.hardware.normalizations");
  if (norms) {
    if (*norms != 0 && *norms != 1) throw std::invalid_argument("invalid normalization capability fact");
    normalizations = *norms == 1;
  }
  std::optional<merlin_timing::Cycle> arrival;
  if (const auto enabled = s.number("target.scheduling.accumulator_readout_arrival")) {
    if (*enabled != 1 || s.number("target.scheduling.version") != std::optional<double>{5} ||
        normalizations != std::optional<bool>{false})
      throw std::invalid_argument("ACC readout arrival requires selected non-normalizing staged v5");
    const auto stages = integer(s, "accumulator_scale_pipeline_stages");
    if (!stages || stages > 256) throw std::invalid_argument("invalid ACC scale pipeline fact");
    arrival = stages;
  }
  return {integer(s, "dim"), integer(s, "scratchpad_rows"), integer(s, "accumulator_rows"),
          integer(s, "element_bytes"), integer(s, "accumulator_bytes"), integer(s, "address_bits"),
          bool(first), bool(full), activation, normalizations, arrival,
          s.number("target.scheduling.accumulator_streamed_readout")==std::optional<double>{1},
          s.number("target.scheduling.scratchpad_row_loads")==std::optional<double>{1},
          s.number("target.scheduling.scratchpad_packet_loads")==std::optional<double>{1},
          s.number("target.scheduling.accumulator_readout_packet_geometry")==std::optional<double>{1},
          s.number("target.scheduling.accumulator_readout_packet_geometry")==std::optional<double>{1}?integer(s,"writer_beat_bytes"):0,
          s.number("target.scheduling.accumulator_readout_packet_geometry")==std::optional<double>{1}?integer(s,"writer_max_request_bytes"):0,
          s.number("target.scheduling.accumulator_readout_full_packets")==std::optional<double>{1},
          s.number("target.scheduling.source_identity_ingress")==std::optional<double>{1},
          s.number("target.scheduling.wide_scratchpad_row_publication")==std::optional<double>{1},
          s.number("target.scheduling.wide_scratchpad_row_publication")==std::optional<double>{1}?integer(s,"selected_mvin_cols_bits"):0,
          s.number("target.scheduling.wide_scratchpad_row_publication")==std::optional<double>{1}?integer(s,"selected_mvin_rows_bits"):0,
          s.number("target.scheduling.source_full_accumulator_load")==std::optional<double>{1},
          s.number("target.scheduling.source_masked_i8_readout")==std::optional<double>{1}};
}

G::Parameters parameters(Services &s) {
  G::Parameters result;
  for (const auto *kind : G::priced_primitive_classes)
    for (const auto *field : {"latency_cycles", "occupancy_cycles", "latency_per_byte_cycles",
                             "occupancy_per_byte_cycles", "latency_per_mac_cycles", "occupancy_per_mac_cycles"}) {
      const auto key = std::string(kind) + "." + field;
      if (const auto value = s.number("target.prices." + key)) result[key] = *value;
    }
  for (const auto *field : {"dma.read_bytes_per_cycle", "dma.write_bytes_per_cycle"})
    if (const auto value = s.number(std::string("target.prices.") + field)) result[field] = *value;
  if (const auto relation = s.number("target.scheduling.pool_relu_shared_scale_pipeline")) {
    if (*relation != 1 ||
        s.number("target.hardware.relu_same_accumulator_scale_pipeline") != std::optional<double>{1} ||
        s.number("target.hardware.normalizations") != std::optional<double>{0})
      throw std::invalid_argument("pool ReLU service relation requires selected RTL pipeline facts");
    G::apply_pool_relu_shared_pipeline(result);
  }
  return result;
}

G::ResourceBindings resources(Services &s) {
  const auto staged = s.number("target.scheduling.version");
  if (staged == std::optional<double>{2} || staged == std::optional<double>{3} ||
      staged == std::optional<double>{4} || staged == std::optional<double>{5}) return {};
  const auto selected = [&](const std::string &name) -> std::optional<merlin_timing::ResourceId> {
    try { return s.resource("accelerator." + name); }
    catch (const std::exception &) {
      s.unresolved("missing_target_resource:" + name);
      return {};
    }
  };
  // Shared memory owns DMA reservations; standalone-only DMA bindings are not
  // requested, and their absence cannot taint a valid integrated observation.
  return {selected("config"), selected("load"), selected("store"), selected("execute"), {}, {}};
}

struct Inputs {
  G::HardwareConfig hardware;
  G::Parameters parameters;
  G::ResourceBindings resources;
  merlin_timing::ValueId tokens;
  std::uint32_t opcode, opcode_mask;
  std::optional<G::StagedConfig> staged;
};

std::optional<G::StagedConfig> staged_config(Services &services) {
  const auto version = services.number("target.scheduling.version");
  if (!version) return {};
  if (*version != 2 && *version != 3 && *version != 4 && *version != 5) throw std::invalid_argument("unsupported target scheduling version");
  G::StagedConfig result;
  const auto count = [&](const std::string &key) {
    const auto value = services.number("target.scheduling." + key);
    if (!value || !std::isfinite(*value) || *value < 1 || *value > 65536 || std::floor(*value) != *value)
      throw std::invalid_argument("missing selected staged capacity: " + key);
    return static_cast<std::size_t>(*value);
  };
  const auto price = [&](const std::string &key) -> std::optional<merlin_timing::Cycle> {
    const auto value = services.number("target.scheduling." + key);
    if (!value) { services.unresolved("missing_staged_price:" + key); return {}; }
    if (!std::isfinite(*value) || *value < 0 || std::floor(*value) != *value || *value >= std::ldexp(1., 64))
      throw std::invalid_argument("invalid staged price: " + key);
    return static_cast<merlin_timing::Cycle>(*value);
  };
  std::size_t i = 0;
  for (const auto *name : {"load", "execute", "store"}) {
    result.reservations[i] = count(std::string("reservations.") + name);
    result.controller_entries[i] = count(std::string("controller_entries.") + name);
    result.issue_resources[i] = services.resource(std::string("accelerator.issue.") + name);
    result.controller_resources[i] = services.resource(std::string("accelerator.controller.") + name);
    ++i;
  }
  result.dma_commands = {count("dma_commands.load"), count("dma_commands.store")};
  result.issue_latency = price("issue_latency_cycles");
  result.issue_occupancy = price("issue_occupancy_cycles");
  result.require_fenced_phases = services.number("target.scheduling.require_fenced_phases") == std::optional<double>{1};
  result.allow_dependency_ordered_phases = services.number("target.scheduling.allow_dependency_ordered_phases") == std::optional<double>{1};
  result.allow_disjoint_scratchpad_banks = services.number("target.scheduling.allow_disjoint_scratchpad_banks") == std::optional<double>{1};
  result.conservative_local_store_holds = services.number("target.scheduling.conservative_local_store_holds") == std::optional<double>{1};
  if (*version == 3 || *version == 4 || *version == 5) {
    if (services.number("target.scheduling.serialized_execute_epochs") != std::optional<double>{1})
      throw std::invalid_argument("staged v3 requires explicit serialized execute epoch semantics");
    result.serialized_execute_epochs = true;
  } else if (services.number("target.scheduling.serialized_execute_epochs")) {
    throw std::invalid_argument("execute epoch policy requires staged v3");
  }
  if (*version == 4 || *version == 5) {
    if (services.number("target.scheduling.serialized_output_stationary_epochs") != std::optional<double>{1})
      throw std::invalid_argument("staged v4 requires explicit OS epoch service semantics");
    result.serialized_output_stationary_epochs = true;
  } else if (services.number("target.scheduling.serialized_output_stationary_epochs")) {
    throw std::invalid_argument("OS epoch policy requires staged v4");
  }
  if (*version == 5) {
    if (services.number("target.scheduling.split_ws_feed_lifetimes") != std::optional<double>{1})
      throw std::invalid_argument("staged v5 requires explicit WS feed/result lifetime split");
    result.split_ws_feed_lifetimes = true;
  } else if (services.number("target.scheduling.split_ws_feed_lifetimes")) {
    throw std::invalid_argument("WS feed/result lifetime split requires staged v5");
  }
  if (const auto split = services.number("target.scheduling.split_ws_accumulate_operands")) {
    if (*split != 1 || !result.split_ws_feed_lifetimes || !result.conservative_local_store_holds)
      throw std::invalid_argument("accumulating WS operands require staged v5 and conservative ACC holds");
    result.split_ws_accumulate_operands = true;
  }
  if(const auto selected=services.number("target.scheduling.bounded_ws_operand_release")) {
    if(*selected!=1 || !result.split_ws_feed_lifetimes || !result.conservative_local_store_holds)
      throw std::invalid_argument("bounded WS operand release requires conservative v5 premises");
    result.bounded_ws_operand_release=true;
  }
  if(const auto selected=services.number("target.scheduling.late_accumulator_write_phases")) {
    const auto stages=services.number("target.hardware.accumulator_write_pipeline_stages");
    if(*selected!=1 || !result.bounded_ws_operand_release || !stages ||
        !std::isfinite(*stages) || std::floor(*stages)!=*stages || *stages<1 || *stages>256 ||
        services.number("target.hardware.accumulator_two_port_storage")!=std::optional<double>{1})
      throw std::invalid_argument("late ACC phases require selected two-port write pipeline facts");
    result.late_accumulator_write_pipeline=static_cast<merlin_timing::Cycle>(*stages);
  }
  if(const auto selected=services.number("target.scheduling.bounded_ws_descriptor_consumption")) {
    if(*selected!=1 || !result.late_accumulator_write_pipeline)
      throw std::invalid_argument("bounded WS descriptor lifetime requires retained row-write phases");
    result.bounded_ws_descriptor_consumption=true;
  }
  if(const auto selected=services.number("target.scheduling.ws_preload_operand_ownership")) {
    if(*selected!=1 || !result.bounded_ws_operand_release || !result.bounded_ws_descriptor_consumption)
      throw std::invalid_argument("PRELOAD operand ownership needs selected bounded WS consumed descriptors");
    result.ws_preload_operand_ownership=true;
  }
  if(const auto selected=services.number("target.scheduling.load_configuration_request_lifetime")) {
    if(*selected!=1 || !result.conservative_local_store_holds)
      throw std::invalid_argument("LOAD configuration request lifetime needs explicit data hazards");
    result.load_configuration_request_lifetime=true;
  }
  if (const auto release = services.number("target.scheduling.ws_feed_queue_release")) {
    if (*release != 1 || !result.split_ws_feed_lifetimes ||
        services.number("target.hardware.execute_completion_pending_register") != std::optional<double>{1})
      throw std::invalid_argument("WS queue release requires selected registered completion facts and staged v5");
    result.ws_feed_queue_release = true;
  }
  if (const auto paired = services.number("target.scheduling.ws_resident_mul_pre_pairing")) {
    if (*paired != 1 || !result.ws_feed_queue_release ||
        services.number("target.hardware.execute_command_lookahead_heads") != std::optional<double>{3})
      throw std::invalid_argument("WS resident pairing requires selected three-command lookahead and FIFO lifetimes");
    result.ws_resident_mul_pre_pairing = true;
  }
  if(const auto stream=services.number("target.scheduling.accumulator_streamed_readout")) {
    if(*stream!=1 || !result.conservative_local_store_holds ||
        services.number("target.scheduling.accumulator_readout_arrival")!=std::optional<double>{1} ||
        services.number("target.assumptions.accumulator_readout_translation_hits")!=std::optional<double>{1})
      throw std::invalid_argument("streamed ACC readout requires conservative holds, first-data path and explicit translation-hit assumption");
    const auto fact=[&](const char *key,std::size_t expected) {
      if(services.number(std::string("target.hardware.")+key)!=std::optional<double>{double(expected)})
        throw std::invalid_argument(std::string("unsupported streamed ACC fact: ")+key);
      return expected;
    };
    fact("accumulator_read_response_cycles",1);fact("writer_tlb_queue_entries",1);
    fact("writer_translation_queue_entries",1);fact("writer_translation_queue_pipe",1);
    fact("writer_max_request_bytes",64);
    if(integer(services,"dim")*integer(services,"accumulator_bytes")!=64)
      throw std::invalid_argument("streamed ACC readout requires one aligned64-byte row transaction");
    result.readout_stream=G::ReadoutStreamConfig{
        fact("write_dispatch_queue_entries",2),fact("write_norm_queue_entries",6),
        fact("normalizer_passthrough_queue_entries",2),fact("write_scale_queue_entries",6),
        fact("write_issue_queue_entries",5),fact("accumulator_scale_pipeline_stages",8),
        fact("writer_transaction_entries",16),fact("writer_beat_bytes",16)};
  }
  if(const auto selected=services.number("target.scheduling.scratchpad_row_loads")) {
    if(*selected!=1 || !result.conservative_local_store_holds ||
        services.number("target.assumptions.scratchpad_load_translation_hits")!=std::optional<double>{1} ||
        services.number("target.assumptions.scratchpad_load_fifo_responses")!=std::optional<double>{1})
      throw std::invalid_argument("row loads require explicit translation/FIFO assumptions and storage hazards");
    const auto fact=[&](const char *key,std::size_t expected) {
      if(services.number(std::string("target.hardware.")+key)!=std::optional<double>{double(expected)})
        throw std::invalid_argument(std::string("unsupported scratchpad row-load fact: ")+key);
      return expected;
    };
    fact("dim",16);fact("element_bytes",1);fact("reader_beat_bytes",16);
    fact("reader_translation_queue_entries",1);fact("reader_tlb_queue_entries",1);
    fact("reader_beat_merger_stages",1);fact("identity_scale_input_stages",1);
    fact("identity_scale_output_stages",1);fact("scratchpad_singleported",1);
    result.scratchpad_load_stream=G::ScratchpadLoadConfig{
        fact("reader_transaction_entries",16),fact("identity_scale_queue_entries",3),2,
        3+integer(services,"first_layer_optimizations")};
  }
  if(const auto packets=services.number("target.scheduling.scratchpad_packet_loads")) {
    if(*packets!=1 || !result.scratchpad_load_stream ||
        services.number("target.hardware.reader_max_request_bytes")!=std::optional<double>{64} ||
        services.number("target.assumptions.reader_packet_last_response_bound")!=std::optional<double>{1})
      throw std::invalid_argument("pitched loads require selected64-byte reader packet law and explicit conservative last-response bound");
    result.scratchpad_packet_loads=true;
  }
  if(const auto selected=services.number("target.scheduling.scratchpad_request_admission")) {
    if(*selected!=1 || !result.scratchpad_load_stream ||
        services.number("target.assumptions.reader_a_ready_with_transaction_credit")!=std::optional<double>{1})
      throw std::invalid_argument("independent row requests require explicit A-ready credit assumption");
    result.scratchpad_load_stream->independent_request_admission=true;
  }
  if(const auto selected=services.number("target.scheduling.source_identity_ingress")) {
    if(*selected!=1 || !result.scratchpad_load_stream ||
        services.number("target.hardware.identity_ingress_queue_entries")!=std::optional<double>{2} ||
        services.number("target.hardware.identity_ingress_register_entries")!=std::optional<double>{1} ||
        services.number("target.hardware.identity_completed_ring_entries")!=std::optional<double>{3} ||
        services.number("target.hardware.identity_pixel_register_entries")!=std::optional<double>{1})
      throw std::invalid_argument("identity ingress requires source-bound2/1/3/1 registered stages");
    result.source_identity_ingress=true;
  }
  if(const auto selected=services.number("target.scheduling.source_bounded_mul_pre_pairing")) {
    if(*selected!=1 || !result.ws_resident_mul_pre_pairing || !result.bounded_ws_descriptor_consumption ||
        !result.ws_preload_operand_ownership || !result.late_accumulator_write_pipeline ||
        services.number("target.hardware.execute_command_lookahead_heads")!=std::optional<double>{3} ||
        services.number("target.hardware.execute_completion_pending_register")!=std::optional<double>{1})
      throw std::invalid_argument("bounded execute pairing requires selected three-head lookahead and retained output/ROB phases");
    result.source_bounded_mul_pre_pairing=true;
  }
  if(const auto selected=services.number("target.scheduling.source_fenced_single_mul")) {
    if(*selected!=1 || !result.source_bounded_mul_pre_pairing ||
        services.number("target.hardware.ws_minimum_input_rows")!=std::optional<double>{4} ||
        services.number("target.assumptions.source_instruction_suffix_commit_validation")!=std::optional<double>{1})
      throw std::invalid_argument("fenced single-MUL requires sourcefloor4 and committed immutable suffix validation");
    result.source_fenced_single_mul=true;
  }
  if(const auto selected=services.number("target.scheduling.wide_scratchpad_row_publication")) {
    if(*selected!=1 || services.number("target.hardware.selected_mvin_cols_bits")!=std::optional<double>{7} ||
        services.number("target.hardware.selected_mvin_rows_bits")!=std::optional<double>{5} ||
        services.number("target.scheduling.source_identity_ingress")!=std::optional<double>{1} ||
        services.number("target.scheduling.scratchpad_packet_loads")!=std::optional<double>{1})
      throw std::invalid_argument("wide row publication requires selected7/5-bit mvin fields and original identity packet pipeline");
  }
  if (result.allow_disjoint_scratchpad_banks || result.conservative_local_store_holds)
    result.scratchpad_bank_rows = count("scratchpad_bank_rows");
  if (result.conservative_local_store_holds) {
    const auto banks = count("scratchpad_bank_count");
    if (banks > 128) throw std::invalid_argument("local store resource count exceeds bound");
    for (std::size_t bank = 0; bank < banks; ++bank)
      result.scratchpad_bank_resources.push_back(services.resource("accelerator.storage.scratchpad." + std::to_string(bank)));
    result.accumulator_storage_resource = services.resource("accelerator.storage.accumulator.all");
  }
  return result;
}

class Provider final : public spike_timing::TargetProvider {
public:
  Provider(Services services, Inputs inputs)
      : services_(std::move(services)), opcode_(inputs.opcode), opcode_mask_(inputs.opcode_mask),
        staged_(inputs.staged ? std::make_unique<G::StagedObserver>(services_.engine, *inputs.staged,
          inputs.tokens + inputs.hardware.scratchpad_rows + inputs.hardware.accumulator_rows + 4,
          services_.unresolved, inputs.tokens, inputs.hardware.scratchpad_rows, inputs.hardware.dim, inputs.hardware.accumulator_rows) : nullptr),
        observer_(services_.engine, inputs.hardware, std::move(inputs.parameters),
          inputs.resources, inputs.tokens, [this](merlin_timing::View<G::Transfer> transfers) {
            std::vector<spike_timing::MemoryEffect> rows;
            for (std::size_t i = 0; i < transfers.size; ++i) {
              const auto &transfer = transfers[i];
              for (std::uint64_t row = 0; row < transfer.rows; ++row)
                rows.push_back({transfer.address + row * transfer.row_stride, transfer.row_bytes, transfer.write});
            }
            const auto effects = services_.memory(rows);
            return G::TransferEffects{effects.reads, effects.writes, effects.demands, effects.latency};
          }, staged_ ? G::SubmitHook{[this](const auto &kind, const auto &event, auto occupancy,
                                          auto funct, auto rs1, auto rs2, const auto &phase) {
            return staged_->submit(kind, event, occupancy, funct, rs1, rs2, phase);
          }} : G::SubmitHook{}) {
    for (const auto &counter : counter_features) services_.feature(std::string("target.") + counter.name, 0);
    services_.feature("target.source_fenced_single_mul_feed",0);
    services_.feature("target.source_validated_instruction_suffix",0);
    services_.feature("target.source_bounded_mul_pre_pair",0);
    services_.feature("target.foreign_custom_opcode", 0);
    services_.feature("target.custom_counter_result_unknown", 0);
    for (const auto *kind : G::priced_primitive_classes) services_.feature(std::string("target.class.") + kind, 0);
    for (const auto *kind : G::diagnostic_primitive_classes) services_.feature(std::string("target.class.") + kind, 0);
  }

  merlin_timing::Result command(std::uint64_t pc, std::uint64_t bits, std::uint64_t rs1,
                                std::uint64_t rs2, merlin_timing::Cycle earliest) override {
    if ((bits & opcode_mask_) != opcode_) {
      count_errors_.insert("foreign_custom_opcode");
      services_.unresolved("foreign_custom_opcode");
      services_.feature("target.foreign_custom_opcode", 1);
      merlin_timing::Event unknown;
      unknown.earliest = earliest;
      return services_.engine.submit(unknown);
    }
    // Pinned rocc_insn_t places xs2 after opcode[6:0] + rd[4:0],
    // followed by xs1. libgemmini passes all-ones for a disabled operand.
    if (!(bits & (1ull << 13))) rs1 = std::numeric_limits<std::uint64_t>::max();
    if (!(bits & (1ull << 12))) rs2 = std::numeric_limits<std::uint64_t>::max();
    // The functional extension supplies a dummy/random custom counter return.
    // It cannot qualify control/data that depends on a hardware counter result.
    if (((bits >> 25) & 127) == 126 && (bits & (1ull << 14))) {
      count_errors_.insert("custom_counter_result_not_hardware_equivalent");
      services_.unresolved("custom_counter_result_not_hardware_equivalent");
      services_.feature("target.custom_counter_result_unknown", 1);
      merlin_timing::Event unknown;
      unknown.earliest = earliest;
      return services_.engine.submit(unknown);
    }
    if(staged_)staged_->proven_single_mul(proof_for_current_ && !(bits&(1ull<<14)) &&
        current_context_.phase==merlin_timing::InstructionPhase::committed &&
        current_context_.pc==pc && current_context_.bits==bits);
    const auto result = observer_.observe_command(pc, (bits >> 25) & 127, rs1, rs2, earliest);
    proof_for_current_=false;
    if(staged_)staged_->proven_single_mul(false);
    features();
    return result;
  }
  void fence(merlin_timing::Cycle earliest) override {
    observer_.observe_fence(earliest);
    features();
  }
  void instruction_context(const merlin_timing::InstructionContextV1 &context) {
    proof_for_current_=false;current_context_=context;
    if(!merlin_timing::valid_instruction_context(context)) {
      services_.unresolved("target:invalid_committed_instruction_context");return;
    }
    ++contexts_seen_;
    const auto progress=suffix_evidence_.observe(context);
    if(progress==merlin_timing::SuffixProgress::invalid)
      services_.unresolved("target:immutable_suffix_commit_mismatch");
    if(progress==merlin_timing::SuffixProgress::closed) {
      ++suffixes_validated_;services_.feature("target.source_validated_instruction_suffix",1);
    }
  }
  void immutable_suffix(const merlin_timing::ImmutableInstructionSuffixV1 &suffix) {
    const auto &c=suffix.current;
    if(!staged_ || !merlin_timing::valid_instruction_context(c) || c.phase!=merlin_timing::InstructionPhase::committed ||
       c.sequence!=current_context_.sequence || c.pc!=current_context_.pc || c.bits!=current_context_.bits ||
       c.primary_elf_sha256!=current_context_.primary_elf_sha256 || (c.bits&opcode_mask_)!=opcode_ ||
       ((c.bits>>25)&127)!=4 || (c.bits&(1ull<<14)))return;
    const auto role=[this](const merlin_timing::ImmutableInstructionV1&i) {
      using R=merlin_timing::SuffixRole;
      if(i.bits==0x0ff0000full && i.length==4)return R::closing_barrier;
      if(i.length==2) {
        const auto q=i.bits&3,funct=(i.bits>>13)&7;
        if(q==0 && funct!=4)return R::permitted;
        if(q==1 && funct<5)return R::permitted;
        if(q==2 && (funct!=4 || ((i.bits>>2)&31)))return R::permitted;
        return R::forbidden;
      }
      const auto opcode=i.bits&127;
      if((i.bits&opcode_mask_)==opcode_) {
        if(i.bits&(1ull<<14))return R::forbidden;
        const auto funct=(i.bits>>25)&127;
        return funct==0 || funct==1 || funct==2 || funct==3 || funct==7 || funct==14 ?
            R::permitted:R::forbidden;
      }
      switch(opcode) {
        case 0x03:case 0x23:case 0x13:case 0x1b:case 0x33:case 0x3b:case 0x17:case 0x37:
          return R::permitted;
        default:return R::forbidden;
      }
    };
    if(suffix_evidence_.arm(suffix,role))proof_for_current_=true;
  }
  spike_timing::FeatureObservationStatus feature_status() const {
    auto reasons = count_errors_;
    if(suffix_evidence_.pending())reasons.insert("target_instruction_suffix_not_yet_committed");
    if(suffix_evidence_.failed())reasons.insert("target_instruction_suffix_commit_failed");
    for (const auto &entry : observer_.unknown_semantics()) reasons.insert("target:" + entry.first);
    if (observer_.counters().accounting_overflow) reasons.insert("target_counter_overflow");
    if (observer_.counters().illegal_events) reasons.insert("target_illegal_events");
    return {reasons.empty(), {reasons.begin(), reasons.end()}};
  }

private:
  Services services_; // Own callback closures for the complete provider lifetime.
  std::uint32_t opcode_, opcode_mask_;
  std::unique_ptr<G::StagedObserver> staged_;
  G::TargetObserver observer_;
  G::Counters previous_{};
  std::uint64_t previous_bounded_pairings_=0,previous_fenced_single_feeds_=0;
  merlin_timing::InstructionSuffixEvidence suffix_evidence_;
  merlin_timing::InstructionContextV1 current_context_;
  bool proof_for_current_=false;
  std::uint64_t contexts_seen_=0,suffixes_validated_=0;
  std::map<std::string, std::uint64_t> previous_classes_;
  std::set<std::string> reported_unknowns_;
  std::set<std::string> count_errors_;

  void features() {
    if(staged_ && staged_->fenced_single_feeds()>previous_fenced_single_feeds_) {
      services_.feature("target.source_fenced_single_mul_feed",staged_->fenced_single_feeds()-previous_fenced_single_feeds_);
      previous_fenced_single_feeds_=staged_->fenced_single_feeds();
    }
    if(staged_ && staged_->bounded_pairings()>previous_bounded_pairings_) {
      services_.feature("target.source_bounded_mul_pre_pair",staged_->bounded_pairings()-previous_bounded_pairings_);
      previous_bounded_pairings_=staged_->bounded_pairings();
    }
    const auto &now = observer_.counters();
    const auto feature = [&](const char *name, std::uint64_t current, std::uint64_t previous) {
      if (current > previous) services_.feature(std::string("target.") + name, current - previous);
    };
    for (const auto &counter : counter_features)
      feature(counter.name, now.*counter.member, previous_.*counter.member);
    for (const auto &entry : observer_.primitive_classes()) {
      if (!G::registered_primitive_class(entry.first)) {
        count_errors_.insert("unregistered_target_primitive_class");
        services_.unresolved("unregistered_target_primitive_class");
        continue;
      }
      auto &before = previous_classes_[entry.first];
      if (entry.second > before) services_.feature("target.class." + entry.first, entry.second - before);
      before = entry.second;
    }
    for (const auto *reasons : {&observer_.unknown_semantics(), &observer_.unknown_timing()})
      for (const auto &entry : *reasons)
        if (reported_unknowns_.insert(entry.first).second) services_.unresolved("target:" + entry.first);
    if (now.accounting_overflow && !previous_.accounting_overflow) services_.unresolved("target_counter_overflow");
    previous_ = now;
  }
};
// Separate optional factory; the original Provider and v1 path are unchanged.
class PostedProvider final : public spike_timing::TargetProvider {
 Services &services_; Inputs inputs_; G::PostedSourceObserver posted_;
 G::TargetObserver observer_,architectural_; G::Counters previous_{};
 std::unique_ptr<G::PostedCommandIngress> ingress_;
 std::optional<merlin_timing::StageOrigin> timing_origin_;
 std::map<std::string,std::uint64_t> classes_;std::set<std::string> reasons_;
 static G::TransferEffects metadata(merlin_timing::View<G::Transfer>){return {{},{},{},merlin_timing::Cycle{0}};}
 void features(){
   const auto &current=architectural_.counters();
   for(const auto &c:counter_features)if(current.*(c.member)>previous_.*(c.member))
     services_.feature(std::string("target.")+c.name,current.*(c.member)-previous_.*(c.member));
   for(const auto &item:architectural_.primitive_classes()){
     if(item.second>classes_[item.first])services_.feature("target.class."+item.first,item.second-classes_[item.first]);
     classes_[item.first]=item.second;
   }
   for(auto *entries:{&architectural_.unknown_semantics(),&architectural_.unknown_timing(),&observer_.unknown_semantics(),&observer_.unknown_timing()})
     for(const auto &item:*entries)if(reasons_.insert(item.first).second)services_.unresolved("posted_target:"+item.first);
   previous_=current;
 }
 static std::optional<std::size_t>group(const G::PostedCommandIngress::Request&r){
   const auto f=(r.bits>>25)&127;
   if(f==1||f==2||f==14||(f==0&&(r.rs1&3)==1))return 0;
   if(f==3||(f==0&&((r.rs1&3)==2||(r.rs1&3)==3)))return 2;
   if(f==4||f==5||f==6||(f==0&&(r.rs1&3)==0))return 1;
   return {};
 }
 public:
 PostedProvider(Services&s,Inputs inputs,merlin_timing::PostedTimeline&q):services_(s),inputs_(std::move(inputs)),
   posted_(s,q,inputs_.hardware,*inputs_.staged,inputs_.tokens),
   observer_(s.engine,inputs_.hardware,inputs_.parameters,{},inputs_.tokens,metadata,
     [this](const auto &kind,const auto &event,auto occupancy,auto funct,auto rs1,auto rs2,const auto &phase){
       if(ingress_&&kind=="flush")return merlin_timing::Result{event.earliest,event.earliest,event.earliest};
       auto origin=timing_origin_;if(origin)origin->actor="target."+kind;
       return posted_.submit(kind,event,occupancy,funct,rs1,rs2,phase,observer_.transfers(),std::move(origin));
     }),
   architectural_(s.engine,inputs_.hardware,inputs_.parameters,{},inputs_.tokens,metadata,
     [](const auto&,const auto&e,auto,auto,auto,auto,const auto&){return merlin_timing::Result{e.earliest,e.earliest,e.earliest};}) {
   for(const auto&counter:counter_features)s.feature(std::string("target.")+counter.name,0);
   for(const auto *kind:G::priced_primitive_classes)s.feature(std::string("target.class.")+kind,0);
   for(const auto *kind:G::diagnostic_primitive_classes)s.feature(std::string("target.class.")+kind,0);
   for(auto name:{"accepted","issued","modeled_identity_port_wait","modeled_merger_backpressure","modeled_cpu_rs_wait_cycles","modeled_target_fence_wait_cycles","raw_accepted","raw_to_rs_allocated","raw_bypass","modeled_raw_source_wait_cycles"})s.feature(std::string("target.posted.")+name,0);
   if(const auto enabled=s.number("target.scheduling.source_raw_command_ingress")){
     if(*enabled!=1)throw std::invalid_argument("invalid raw ingress selection");
     for(auto name:{"raw_command_queue_entries","loop_conv_command_queue_entries","loop_matmul_command_queue_entries","unrolled_command_queue_entries"})
       if(integer(s,name)!=2)throw std::invalid_argument("raw ingress requires selected four Queue2 source facts");
     for(auto prefix:{"raw_command_queue","loop_conv_command_queue","loop_matmul_command_queue","unrolled_command_queue"})
       if(integer(s,std::string(prefix)+"_flow")||integer(s,std::string(prefix)+"_pipe"))
         throw std::invalid_argument("raw ingress requires selected non-flow/non-pipe queues");
     if(integer(s,"selected_has_loop_conv")!=1)
       throw std::invalid_argument("raw ingress requires instantiated LoopConv");
     ingress_=std::make_unique<G::PostedCommandIngress>(q,std::array<std::size_t,4>{2,2,2,2},
       [this](const auto&r,auto at){return ((r.bits>>25)&127)==7 || (group(r)&&posted_.can_allocate(*group(r),at));},
       [this](const auto&r,auto at){
         if(((r.bits>>25)&127)==7)services_.feature("target.posted.raw_bypass",1);
         else services_.feature("target.posted.raw_to_rs_allocated",1);
         timing_origin_=merlin_timing::StageOrigin{r.pc,r.bits,{},"target.command"};
         observer_.observe_command(r.pc,(r.bits>>25)&127,r.rs1,r.rs2,at);features();
       });
   }
 }
 void memory_lookup_query(const merlin_timing::MemoryMilestoneQueryV2&query){posted_.memory_lookup_query(query);}
 void write_transactions(const spike_timing::WriteTransactionServiceV1&service){posted_.write_transactions(service);}
 void write_transactions(const spike_timing::WriteTransactionServiceV2&service){posted_.write_transactions(service);}
 void full_write_packets(const spike_timing::FullWritePacketServiceV3&service){posted_.full_write_packets(service);}
 void cold_writes(const spike_timing::ColdWriteServiceV4&service){posted_.cold_writes(service);}
 void cold_writes(const spike_timing::ColdWriteServiceV5&service){posted_.cold_writes(service);}
 void cold_writes(const spike_timing::ColdWriteServiceV6&service){posted_.cold_writes(service);}
 void read_allocations(const spike_timing::ReadAllocationServiceV7&s){posted_.read_allocations(s);}
 bool submit_read_allocations(const spike_timing::ReadAllocationEffectsV7&b,const merlin_timing::StageOrigin&o,merlin_timing::Cycle at,void*cookie,spike_timing::ReadAllocationReadyV7 ready){return posted_.submit_read_allocations(b,o,at,cookie,ready);}
 merlin_timing::Result command(std::uint64_t pc,std::uint64_t bits,std::uint64_t rs1,std::uint64_t rs2,merlin_timing::Cycle earliest)override{
   if((bits&inputs_.opcode_mask)!=inputs_.opcode || (bits&(1ull<<14))){
     reasons_.insert("unsupported_custom_opcode_or_return");services_.unresolved("posted_target:unsupported_custom_opcode_or_return");return {};
   }
   if(!(bits&(1ull<<13)))rs1=UINT64_MAX;
   if(!(bits&(1ull<<12)))rs2=UINT64_MAX;
   // Counts retain the ORIGINAL committed instruction boundary, independently
   // of deferred timing allocation and current CPU PC at a later callback.
   architectural_.observe_command(pc,(bits>>25)&127,rs1,rs2,earliest);features();
   timing_origin_=merlin_timing::StageOrigin{pc,bits,{},"target.command"};
   if(!ingress_){const auto result=observer_.observe_command(pc,(bits>>25)&127,rs1,rs2,earliest);features();return result;}
   G::PostedCommandIngress::Request request{pc,bits,rs1,rs2,earliest};
   if(!group(request)&&((bits>>25)&127)!=7){services_.unresolved("posted_target:unsupported_raw_frontend_command");return {};}
   const auto before=ingress_->coverage().source_wait;const auto result=ingress_->push(request);
   services_.feature("target.posted.raw_accepted",1);
   services_.feature("target.posted.modeled_raw_source_wait_cycles",ingress_->coverage().source_wait-before);
   services_.engine.advance_issue(result.issue);return result;
 }
 void fence(merlin_timing::Cycle at)override{
   architectural_.observe_fence(at);features();
   if(ingress_&&!ingress_->drain()){services_.unresolved("posted_target:unfinished_raw_ingress");return;}
   observer_.observe_fence(at);features();
 }
 spike_timing::FeatureObservationStatus feature_status()const{
   std::vector<std::string>reasons(reasons_.begin(),reasons_.end());
   return {reasons.empty()&&!architectural_.counters().accounting_overflow,std::move(reasons)};
 }
};
} // namespace

extern "C" spike_timing::TargetProvider *spike_timing_create_provider_v1(spike_timing::Services *services) {
  if (!services) return nullptr;
  try {
    auto h = hardware(*services);
    const auto opcode = integer(*services, "custom_opcode");
    const auto mask = integer(*services, "custom_opcode_mask");
    if (!mask || mask > 127 || (opcode & ~mask)) throw std::invalid_argument("invalid target custom opcode fact");
    Inputs inputs{h, parameters(*services), resources(*services),
                  services->allocate_tokens(G::TargetObserver::required_tokens(h)), opcode, mask,
                  staged_config(*services)};
    return new Provider(*services, std::move(inputs));
  } catch (const std::exception &error) {
    services->unresolved(std::string("target_provider_configuration:") + error.what());
    return nullptr;
  }
}

extern "C" spike_timing::FeatureObservationStatus
spike_timing_provider_feature_observation_v1(const spike_timing::TargetProvider *provider) {
  if(const auto posted=dynamic_cast<const PostedProvider *>(provider))return posted->feature_status();
  const auto selected = dynamic_cast<const Provider *>(provider);
  if (!selected) return {false, {"feature observation belongs to a different provider"}};
  return selected->feature_status();
}

extern "C" void spike_timing_provider_instruction_context_v1(void *opaque,
    const merlin_timing::InstructionContextV1 *context) {
  if(!opaque || !context)return;
  auto selected=dynamic_cast<Provider *>(static_cast<spike_timing::TargetProvider *>(opaque));
  if(selected)selected->instruction_context(*context);
}
extern "C" void spike_timing_provider_immutable_suffix_v1(void *opaque,
    const merlin_timing::ImmutableInstructionSuffixV1 *suffix) {
  if(!opaque || !suffix)return;
  auto selected=dynamic_cast<Provider *>(static_cast<spike_timing::TargetProvider *>(opaque));
  if(selected)selected->immutable_suffix(*suffix);
}

extern "C" spike_timing::TargetProvider *spike_timing_create_posted_provider_v1(
    spike_timing::Services *s,merlin_timing::PostedTimeline *timeline) {
 if(!s||!timeline)return nullptr;
 try{
   auto h=hardware(*s);auto config=staged_config(*s);
   if(!config)throw std::invalid_argument("posted target requires explicit source-service facts");
   Inputs inputs{h,parameters(*s),{},s->allocate_tokens(G::TargetObserver::required_tokens(h)),
     integer(*s,"custom_opcode"),integer(*s,"custom_opcode_mask"),config};
   return new PostedProvider(*s,std::move(inputs),*timeline);
 }catch(const std::exception&e){s->unresolved(std::string("posted_provider_configuration:")+e.what());return nullptr;}
}

// Optional diagnostic capability, unrelated to physical/model qualification.
extern "C" bool spike_timing_provider_stage_origins_v1(const spike_timing::TargetProvider *provider) {
 return dynamic_cast<const PostedProvider *>(provider)!=nullptr;
}

// Optional read-only native observation ABI. Does not repeat a memory access,
// manufacture source/MSHR identity, or confer timing qualification.
extern "C" void spike_timing_provider_memory_milestones_v2(void *opaque,
    const merlin_timing::MemoryMilestoneQueryV2 *query){
 if(!opaque||!query)return;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 if(selected)selected->memory_lookup_query(*query);
}
extern "C" void spike_timing_provider_write_transactions_v1(void*opaque,const spike_timing::WriteTransactionServiceV1*service){
 if(!opaque||!service)return;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 if(selected)selected->write_transactions(*service);
}
extern "C" void spike_timing_provider_write_transactions_v2(void*opaque,const spike_timing::WriteTransactionServiceV2*service){
 if(!opaque||!service)return;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 if(selected)selected->write_transactions(*service);
}
extern "C" void spike_timing_provider_full_write_packets_v3(void*opaque,const spike_timing::FullWritePacketServiceV3*service){
 if(!opaque||!service)return;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 if(selected)selected->full_write_packets(*service);
}
extern "C" void spike_timing_provider_cold_writes_v4(void*opaque,const spike_timing::ColdWriteServiceV4*service){
 if(!opaque||!service)return;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 if(selected)selected->cold_writes(*service);
}
extern "C" void spike_timing_provider_cold_writes_v5(void*opaque,const spike_timing::ColdWriteServiceV5*service){
 if(!opaque||!service)return;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 if(selected)selected->cold_writes(*service);
}
extern "C" void spike_timing_provider_cold_writes_v6(void*opaque,const spike_timing::ColdWriteServiceV6*service){
 if(!opaque||!service)return;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 if(selected)selected->cold_writes(*service);
}

extern "C" void spike_timing_provider_read_allocations_v7(void*opaque,const spike_timing::ReadAllocationServiceV7*service){
 if(!opaque||!service)return;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 if(selected)selected->read_allocations(*service);
}
extern "C" bool spike_timing_provider_submit_read_allocations_v7(void*opaque,const spike_timing::ReadAllocationEffectsV7*batch,
 const merlin_timing::StageOrigin*origin,merlin_timing::Cycle at,void*cookie,spike_timing::ReadAllocationReadyV7 ready){
 if(!opaque||!batch||!origin||!ready)return false;
 auto selected=dynamic_cast<PostedProvider*>(static_cast<spike_timing::TargetProvider*>(opaque));
 return selected&&selected->submit_read_allocations(*batch,*origin,at,cookie,ready);
}
