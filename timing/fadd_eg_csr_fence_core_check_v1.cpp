#include "VShuttleLSUPhase.h"
#include "verilated.h"
#include <array>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <vector>

static void need(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}

int main() {
  try {
    unsigned runs = 0;
    for (unsigned seed : {1U, 17U, 31U})
      for (unsigned hart : {0U, 1U})
        for (unsigned mask = 0; mask != 4; ++mask)
          for (unsigned csr : {0xb00U, 0xb02U, 0xc00U, 0xc02U})
            for (unsigned funct : {2U, 3U, 6U, 7U})
              for (unsigned barrier : {0U, 0x0330000fU, 0x0ff0000fU}) {
                VerilatedContext context;
                context.threads(1);
                context.randReset(2);
                context.randSeed(seed);
                const char* args[] = {"FADD-counter-FENCE-source-boundary"};
                context.commandArgs(1, args);
                Verilated::threadContextp(&context);
                VShuttleLSUPhase model(&context);
                auto& m = model;
#include "initialize.hpp"
                m.io_hartid = hart;
                m.io_dmem_req_ready = 1;
                m.io_dmem_ordered = 1;
                m.io_vector_ex_ready = 1;
                m.io_vector_com_scalar_check_ready = 1;
                m.io_ptw_tlb_req_ready = 1;
                auto edge = [&] {
                  Verilated::threadContextp(&context);
                  m.clock = 0; m.eval(); m.clock = 1; m.eval(); m.clock = 0; m.eval();
                };
                m.reset = 1;
                for (unsigned i = 0; i != 10; ++i) edge();
                m.reset = 0;
                // Actual source instructions define VS/FS, vtype/VL and FCSR.
                // The VU boundary supplies no numeric result or scalar-FPR response.
                std::vector<unsigned> code = {
                    0x000062b7, 0x6002829b, 0x3002a073, 0xcd00f057,
                    0x00301073, 0x02881457};
                if (barrier) code.push_back(barrier);
                code.push_back((csr << 20) | (funct << 12) | (6 << 7) | 0x73);
                const unsigned csr_index = code.size() - 1;
                unsigned next = 0, vector_ex_events = 0;
                std::array<bool, 5> setup_retired{};
                std::optional<unsigned> vector_rrd, vector_com, fence_rrd, fence_com,
                                        csr_rrd, csr_com;
                for (unsigned cycle = 0; cycle != 210; ++cycle) {
                  m.io_vector_backend_busy = (mask & 1) && cycle >= 110 && cycle < 160;
                  m.io_vector_trap_check_busy = (mask & 2) && cycle >= 110 && cycle < 170;
                  m.io_imem_resp_0_valid = next < code.size()
                      && (next < 5 ? cycle >= 10 + 20 * next : cycle >= 110);
                  if (next < code.size()) {
                    m.io_imem_resp_0_bits_inst = code[next];
                    m.io_imem_resp_0_bits_raw_inst = code[next];
                    m.io_imem_resp_0_bits_pc = 0x80000000ULL + 4 * next;
                  }
                  m.clock = 0; m.eval();
                  const bool fire = m.io_imem_resp_0_valid && m.io_imem_resp_0_ready;
                  if (fire && next == 5) vector_rrd = cycle;
                  if (fire && barrier && next == 6) fence_rrd = cycle;
                  if (fire && next == csr_index) csr_rrd = cycle;
                  if (m.io_vector_ex_valid && m.io_vector_ex_fire
                      && m.io_vector_ex_uop_inst == 0x02881457) {
                    ++vector_ex_events;
                    need(!m.io_vector_ex_vconfig_vtype_vill
                         && m.io_vector_ex_vconfig_vtype_vsew == 2
                         && m.io_vector_ex_vconfig_vl == 1,
                         "actual VFADD lacks defined source vector configuration");
                  }
                  for (unsigned lane = 0; lane != 2; ++lane) {
                    const auto valid = lane ? m.io_trace_core_ingress_group_1_iretire
                                            : m.io_trace_core_ingress_group_0_iretire;
                    const auto pc = lane ? m.io_trace_core_ingress_group_1_iaddr
                                         : m.io_trace_core_ingress_group_0_iaddr;
                    if (!valid) continue;
                    if (pc >= 0x80000000ULL && pc < 0x80000014ULL)
                      setup_retired[(pc - 0x80000000ULL) / 4] = true;
                    if (pc == 0x80000014ULL) vector_com = cycle;
                    if (barrier && pc == 0x80000018ULL) fence_com = cycle;
                    if (pc == 0x80000000ULL + 4 * csr_index) csr_com = cycle;
                  }
                  m.clock = 1; m.eval(); m.clock = 0; m.eval();
                  if (fire) ++next;
                }
                for (auto value : setup_retired) need(value, "setup instruction failed to retire");
                need(next == code.size() && vector_ex_events == 1 && vector_rrd == 110
                     && vector_com == 113 && csr_rrd && csr_com,
                     "VFADD/counter did not progress through the actual Core");
                if (!barrier) {
                  need(*csr_rrd == 111 && *csr_com == 116,
                       "independent counter inherited backend busy or wrong scalar phase");
                } else {
                  const unsigned expected = mask & 2 ? 170 : mask & 1 ? 160 : 114;
                  need(fence_rrd == expected && fence_com == expected + 3
                       && *csr_rrd == expected + 1 && *csr_com == expected + 6,
                       "FENCE did not wait full backend/trap gate or wrong CSR phase");
                }
                std::cout << "{\"seed\":" << seed << ",\"hart\":" << hart
                          << ",\"physical_busy_mask\":" << mask
                          << ",\"counter_CSR\":" << csr << ",\"CSR_funct3\":" << funct
                          << ",\"barrier_raw\":" << barrier
                          << ",\"VFADD_RRD\":" << *vector_rrd
                          << ",\"VFADD_COM\":" << *vector_com
                          << ",\"CSR_RRD\":" << *csr_rrd << ",\"CSR_COM\":" << *csr_com;
                if (barrier) std::cout << ",\"FENCE_RRD\":" << *fence_rrd
                                      << ",\"FENCE_COM\":" << *fence_com;
                std::cout << "}\n";
                ++runs;
              }
    std::cout << "{\"pass\":true,\"runs\":" << runs
              << ",\"scope\":\"actual cached Core; external VU ready/busy/flags boundary; no numeric VU/whole-SoC proof\"}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
