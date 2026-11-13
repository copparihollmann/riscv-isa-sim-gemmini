// See LICENSE for license details.

#include "config.h"
#include "processor.h"
#include "mmu.h"
#include "disasm.h"
#include "decode_macros.h"
#include <cassert>
#include <cstdlib>
#include <sstream>
#include <stdexcept>

// The launcher resolves explicit fatal-handler symbols from the guest ELF.
// Recoverable architectural traps are still delivered normally to the guest.
static void check_iris_fatal_pc(processor_t* p, reg_t pc)
{
  static const std::vector<reg_t> fatal_pcs = [] {
    std::vector<reg_t> result;
    if (const char* raw = std::getenv("IRIS_FATAL_PCS")) {
      std::stringstream stream(raw);
      std::string token;
      while (std::getline(stream, token, ',')) {
        size_t used = 0;
        reg_t address = std::stoull(token, &used, 0);
        if (used != token.size()) throw std::runtime_error("invalid IRIS_FATAL_PCS");
        result.push_back(address);
      }
    }
    return result;
  }();
  for (reg_t fatal_pc : fatal_pcs) if (pc == fatal_pc) {
    auto* state = p->get_state();
    std::ostringstream error;
    error << "IRIS_FATAL hart=" << p->get_id() << " pc=0x" << std::hex << pc
      << " cause=0x" << state->mcause->read() << " epc=0x" << state->mepc->read()
      << " tval=0x" << state->mtval->read() << std::dec
      << " cycle=" << state->mcycle->read();
    throw std::runtime_error(error.str());
  }
}

static void check_iris_datatype(processor_t* p, reg_t pc, insn_t insn)
{
  if (!p->get_cfg().iris_vme) return;
  const uint32_t raw = insn.bits(), opcode = raw & 127, f3 = (raw >> 12) & 7;
  if (raw == 0x30500073 && p->get_id() == 2 && p->get_state()->prv == PRV_M) {
    std::ostringstream message;
    message << "IRIS_UNSUPPORTED_CORE_INSTRUCTION hart=2 pc=0x" << std::hex << pc
      << " instruction=0x30500073 reason=Rocket CEASE halt-until-reset behavior is not modeled";
    throw std::runtime_error(message.str());
  }
  const char* unsupported = nullptr;
  if ((raw & MASK_FCVT_BF16_S) == MATCH_FCVT_BF16_S ||
      (raw & MASK_FCVT_S_BF16) == MATCH_FCVT_S_BF16)
    throw trap_illegal_instruction(insn.bits());
  if (opcode == 0x57 && (f3 == 1 || f3 == 5)) {
    const unsigned cmp_f6=raw>>26;
    const bool known_fpcomp=cmp_f6==4||cmp_f6==5||cmp_f6==6||cmp_f6==7||cmp_f6==8||cmp_f6==9||cmp_f6==10||cmp_f6==0x18||cmp_f6==0x19||cmp_f6==0x1b||cmp_f6==0x1c||(f3==5&&(cmp_f6==0x1d||cmp_f6==0x1f));
    if (known_fpcomp && p->VU.vsew==8) throw trap_illegal_instruction(insn.bits());
    if ((!known_fpcomp || p->VU.vsew==8) && p->get_id() >= 2 && (p->VU.vsew == 8 || (p->VU.vsew == 16 && p->VU.altfmt)))
      unsupported = "hart 2 has no Mx BF16/FP8 arithmetic or conversion datapath";
    if (p->VU.vsew == 8) {
      const unsigned f6 = raw >> 26;
      const bool conversion =
        (raw & MASK_VFWCVTBF16_F_F_V) == MATCH_VFWCVTBF16_F_F_V ||
        (raw & MASK_VFNCVTBF16_F_F_W) == MATCH_VFNCVTBF16_F_F_W ||
        (raw & MASK_VFNCVTBF16_SAT_F_F_W) == MATCH_VFNCVTBF16_SAT_F_F_W;
      const bool implemented_fma = f6 == 0 || f6 == 1 || f6 == 2 || f6 == 3 ||
        f6 == 0x31 || f6 == 0x33 || f6 == 0x24 || f6 == 0x27 ||
        (f6 >= 0x28 && f6 <= 0x2f) || f6 == 0x30 || f6 == 0x32 ||
        f6 == 0x34 || f6 == 0x36 || f6 == 0x38 || f6 >= 0x3c;
      if (!conversion && !implemented_fma)
        unsupported = "vector-FP8 reduction/divide/comparison or other unverified datapath";
    } else if (p->VU.vsew == 16 && p->VU.altfmt) {
      // Source-backed BF16 FMA/conversion paths; comparison/division datapaths
      // do not select BF16. Do not silently emulate idealized BF16 semantics.
      const unsigned f6 = raw >> 26;
      const bool fma = f6 == 0 || f6 == 1 || f6 == 2 || f6 == 3 || f6 == 0x31 || f6 == 0x33 ||
        f6 == 0x24 || f6 == 0x27 ||
        (f6 >= 0x28 && f6 <= 0x2f) || f6 == 0x30 || f6 == 0x32 ||
        f6 == 0x34 || f6 == 0x36 || f6 == 0x38 || (f6 >= 0x3c);
      const bool fpcomp=f6==4||f6==5||f6==6||f6==7||f6==8||f6==9||f6==10||f6==0x18||f6==0x19||f6==0x1b||f6==0x1c||(f3==5&&(f6==0x1d||f6==0x1f));
      if (!fma && !fpcomp && f6 != 0x12)
        unsupported = "BF16 comparison/division or other non-FMA datapath has no verified BF16 format selection";
    }
  }
  if (unsupported) {
    std::ostringstream message;
    message << "IRIS_UNSUPPORTED_DATATYPE hart=" << p->get_id() << " pc=0x" << std::hex << pc
      << " instruction=0x" << raw << " reason=" << unsupported;
    throw std::runtime_error(message.str());
  }
}

static void commit_log_reset(processor_t* p)
{
  p->get_state()->log_reg_write.clear();
  p->get_state()->log_mem_read.clear();
  p->get_state()->log_mem_write.clear();
}

static void commit_log_stash_privilege(processor_t* p)
{
  state_t* state = p->get_state();
  state->last_inst_priv = state->prv;
  state->last_inst_xlen = p->get_xlen();
  state->last_inst_flen = p->get_flen();
}

static void commit_log_print_value(FILE *log_file, int width, const void *data)
{
  assert(log_file);

  switch (width) {
    case 8:
      fprintf(log_file, "0x%02" PRIx8, *(const uint8_t *)data);
      break;
    case 16:
      fprintf(log_file, "0x%04" PRIx16, *(const uint16_t *)data);
      break;
    case 32:
      fprintf(log_file, "0x%08" PRIx32, *(const uint32_t *)data);
      break;
    case 64:
      fprintf(log_file, "0x%016" PRIx64, *(const uint64_t *)data);
      break;
    default:
      if (width % 8 == 0) {
        const uint8_t *arr = (const uint8_t *)data;

        fprintf(log_file, "0x");
        for (int idx = width / 8 - 1; idx >= 0; --idx) {
          fprintf(log_file, "%02" PRIx8, arr[idx]);
        }
      } else {
        abort();
      }
      break;
  }
}

static void commit_log_print_value(FILE *log_file, int width, uint64_t val)
{
  commit_log_print_value(log_file, width, &val);
}

static void commit_log_print_insn(processor_t *p, reg_t pc, insn_t insn)
{
  FILE *log_file = p->get_log_file();

  auto& reg = p->get_state()->log_reg_write;
  auto& load = p->get_state()->log_mem_read;
  auto& store = p->get_state()->log_mem_write;
  int priv = p->get_state()->last_inst_priv;
  int xlen = p->get_state()->last_inst_xlen;
  int flen = p->get_state()->last_inst_flen;

  // print core id on all lines so it is easy to grep
  fprintf(log_file, "core%4" PRId32 ": ", p->get_id());

  fprintf(log_file, "%1d ", priv);
  commit_log_print_value(log_file, xlen, pc);
  fprintf(log_file, " (");
  commit_log_print_value(log_file, insn.length() * 8, insn.bits());
  fprintf(log_file, ")");
  bool show_vec = false;

  for (auto item : reg) {
    if (item.first == 0)
      continue;

    char prefix = ' ';
    int size;
    int rd = item.first >> 4;
    bool is_vec = false;
    bool is_vreg = false;
    switch (item.first & 0xf) {
    case 0:
      size = xlen;
      prefix = 'x';
      break;
    case 1:
      size = flen;
      prefix = 'f';
      break;
    case 2:
      size = p->VU.VLEN;
      prefix = 'v';
      is_vreg = true;
      break;
    case 3:
      is_vec = true;
      break;
    case 4:
      size = xlen;
      prefix = 'c';
      break;
    default:
      assert("can't been here" && 0);
      break;
    }

    if (!show_vec && (is_vreg || is_vec)) {
        fprintf(log_file, " e%ld %s%ld l%ld",
                (long)p->VU.vsew,
                p->VU.vflmul < 1 ? "mf" : "m",
                p->VU.vflmul < 1 ? (long)(1 / p->VU.vflmul) : (long)p->VU.vflmul,
                (long)p->VU.vl->read());
        show_vec = true;
    }

    if (!is_vec) {
      if (prefix == 'c')
        fprintf(log_file, " c%d_%s ", rd, csr_name(rd));
      else
        fprintf(log_file, " %c%-2d ", prefix, rd);
      if (is_vreg)
        commit_log_print_value(log_file, size, &p->VU.elt<uint8_t>(rd, 0));
      else
        commit_log_print_value(log_file, size, item.second.v);
    }
  }

  for (auto item : load) {
    fprintf(log_file, " mem ");
    commit_log_print_value(log_file, xlen, std::get<0>(item));
  }

  for (auto item : store) {
    fprintf(log_file, " mem ");
    commit_log_print_value(log_file, xlen, std::get<0>(item));
    fprintf(log_file, " ");
    commit_log_print_value(log_file, std::get<2>(item) << 3, std::get<1>(item));
  }
  fprintf(log_file, "\n");
}

inline void processor_t::update_histogram(reg_t pc)
{
  if (histogram_enabled)
    pc_histogram[pc]++;
}

// These two functions are expected to be inlined by the compiler separately in
// the processor_t::step() loop. The logged variant is used in the slow path
static inline reg_t execute_insn_fast(processor_t* p, reg_t pc, insn_fetch_t fetch) {
  p->iris_validate_interrupts();
  check_iris_fatal_pc(p, pc);
  check_iris_datatype(p, pc, fetch.insn);
  return fetch.func(p, fetch.insn, pc);
}
static inline reg_t execute_insn_logged(processor_t* p, reg_t pc, insn_fetch_t fetch)
{
  p->iris_validate_interrupts();
  check_iris_fatal_pc(p, pc);
  check_iris_datatype(p, pc, fetch.insn);
  if (p->get_log_commits_enabled()) {
    commit_log_reset(p);
    commit_log_stash_privilege(p);
  }

  reg_t npc;

  try {
    npc = fetch.func(p, fetch.insn, pc);
    if (npc != PC_SERIALIZE_BEFORE) {
      if (p->get_log_commits_enabled()) {
        commit_log_print_insn(p, pc, fetch.insn);
      }
     }
  } catch(mem_trap_t& t) {
      //handle segfault in midlle of vector load/store
      if (p->get_log_commits_enabled()) {
        for (auto item : p->get_state()->log_reg_write) {
          if ((item.first & 3) == 3) {
            commit_log_print_insn(p, pc, fetch.insn);
            break;
          }
        }
      }
      throw;
  } catch(...) {
    throw;
  }
  p->update_histogram(pc);

  return npc;
}

bool processor_t::slow_path() const
{
  return debug || state.single_step != state.STEP_NONE || state.debug_mode ||
         log_commits_enabled || histogram_enabled || is_waiting_for_interrupt() || check_triggers_icount ||
         !cfg->iris_timing_fixture.empty();
}

// fetch/decode/execute loop
void processor_t::step(size_t n)
{
  mmu_t* _mmu = mmu;

  if (!state.debug_mode) {
    if (halt_request == HR_REGULAR) {
      enter_debug_mode(DCSR_CAUSE_DEBUGINT, 0);
    } else if (halt_request == HR_GROUP) {
      enter_debug_mode(DCSR_CAUSE_GROUP, 0);
    } else if (halt_on_reset) {
      halt_on_reset = false;
      enter_debug_mode(DCSR_CAUSE_HALT, 0);
    }
  }

  while (n > 0) {
    size_t instret = 0;
    reg_t pc = state.pc;
    state.prv_changed = false;
    state.v_changed = false;

    #define advance_pc() { \
      if (unlikely(invalid_pc(pc))) { \
        switch (pc) { \
          case PC_SERIALIZE_BEFORE: state.serialized = true; break; \
          case PC_SERIALIZE_AFTER: ++instret; break; \
          default: abort(); \
        } \
        pc = state.pc; \
        goto serialize; \
      } else { \
        state.pc = pc; \
        instret++; \
      }}

    try
    {
      // An already issued instruction completes before newly pending interrupts.
      if (!sim->iris_completion_fetch(id)) take_pending_interrupt();

      check_if_lpad_required();

      if (unlikely(slow_path()))
      {
        // Main simulation loop, slow path.
        while (instret < n)
        {
          if (unlikely(!state.serialized && state.single_step == state.STEP_STEPPED)) {
            state.single_step = state.STEP_NONE;
            if (!state.debug_mode) {
              enter_debug_mode(DCSR_CAUSE_STEP, 0);
              // enter_debug_mode changed state.pc, so we can't just continue.
              break;
            }
          }

          if (unlikely(state.single_step == state.STEP_STEPPING)) {
            state.single_step = state.STEP_STEPPED;
          }

          if (!state.serialized && check_triggers_icount) {
            auto match = TM.detect_icount_match();
            if (match.has_value()) {
              assert(match->timing == triggers::TIMING_BEFORE);
              throw triggers::matched_t((triggers::operation_t)0, 0, match->action, state.v);
            }
          }

          if (unlikely(is_waiting_for_interrupt()))
            return;

          const auto* prepared = sim->iris_completion_fetch(id);
          insn_fetch_t fetch = prepared ? *prepared : mmu->load_insn(pc);
          if (!prepared) sim->iris_issue(id, pc, fetch);
          if (debug && !state.serialized)
            disasm(fetch.insn);
          pc = execute_insn_logged(this, pc, fetch);
          advance_pc();

          // Resume from debug mode in critical error
          if (state.critical_error && !state.debug_mode) {
            if (state.dcsr->read() & DCSR_CETRIG) {
              enter_debug_mode(DCSR_CAUSE_EXTCAUSE, DCSR_EXTCAUSE_CRITERR);
            } else {
              // Handling of critical error is implementation defined
              // For now just enter debug mode
              enter_debug_mode(DCSR_CAUSE_HALT, 0);
            }
          }
        }
      }
      else while (instret < n)
      {
        // Main simulation loop, fast path.
        for (auto ic_entry = _mmu->access_icache(pc); instret < n; instret++) {
          auto fetch = ic_entry->data;
          ic_entry = ic_entry->next;
          auto new_pc = execute_insn_fast(this, pc, fetch);
          if (unlikely(ic_entry->tag != new_pc)) {
            ic_entry = &_mmu->icache[_mmu->icache_index(new_pc)];
            _mmu->icache[_mmu->icache_index(pc)].next = ic_entry;
            if (ic_entry->tag != new_pc) {
              pc = new_pc;
              advance_pc();
              break;
            }
          }
          state.pc = pc = ic_entry->tag;
        }
      }
    }
    catch(iris_timing_wait&)
    {
      // Fetch/issue has occurred, but no instruction side effects may run until
      // the shared scheduler grants the completion event.
      n = instret;
    }
    catch(trap_t& t)
    {
      take_trap(t, pc);
      n = instret;

      // If critical error then enter debug mode critical error trigger enabled
      if (state.critical_error) {
        if (state.dcsr->read() & DCSR_CETRIG) {
          enter_debug_mode(DCSR_CAUSE_EXTCAUSE, DCSR_EXTCAUSE_CRITERR);
        } else {
          // Handling of critical error is implementation defined
          // For now just enter debug mode
          enter_debug_mode(DCSR_CAUSE_HALT, 0);
        }
      }
      // Trigger action takes priority over single step
      auto match = TM.detect_trap_match(t);
      if (match.has_value())
        take_trigger_action(match->action, 0, state.pc, 0);
      else if (unlikely(state.single_step == state.STEP_STEPPED)) {
        state.single_step = state.STEP_NONE;
        enter_debug_mode(DCSR_CAUSE_STEP, 0);
      }
    }
    catch (triggers::matched_t& t)
    {
      take_trigger_action(t.action, t.address, pc, t.gva);
      // End this step at the trigger boundary.  In particular, a timing-before
      // trigger retires no instruction, so continuing would immediately execute
      // from the debug ROM or trap vector to consume the remaining step count.
      n = instret;
    }
    catch(trap_debug_mode&)
    {
      enter_debug_mode(DCSR_CAUSE_SWBP, 0);
    }

serialize:
    sim->iris_retired(id, instret);
    state.minstret->bump((state.mcountinhibit->read() & MCOUNTINHIBIT_IR) ? 0 : instret);

    // In timing mode the shared clock advances mcycle, including stall/idle time.
    // A zero bump still resolves explicit counter-write serialization semantics.
    state.mcycle->bump(!cfg->iris_timing_fixture.empty() ||
                      (state.mcountinhibit->read() & MCOUNTINHIBIT_CY) ? 0 : instret);

    n -= instret;
  }
}
