// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: main() simulation loop, created with --main

#include "verilated.h"
#include "verilated_vpi.h"
#include "VTestDriver.h"
#include "VTestDriver___024root.h"
#include <cstring>
#include <stdexcept>

static VTestDriver___024root* iris_root;
static uint64_t iris_preloaded;
#include "diag_fields.inc"
#include "deep_fields.inc"
static uint8_t* checked_memory(uint64_t address,size_t bytes) {
    constexpr uint64_t lo=0x80000000ull, split=0x100000000ull, hi=0x180000000ull;
    if(!iris_root || address<lo || address>=hi || bytes>hi-address || (address<split && bytes>split-address))
        throw std::runtime_error("RTL preload outside a native DRAM bank");
    auto* words = address<split ? iris_root->TestDriver__DOT__testHarness__DOT__ram__DOT__srams__DOT__mem_ext__DOT__Memory.data()
                              : iris_root->TestDriver__DOT__testHarness__DOT__ram__DOT__srams_1__DOT__mem_ext__DOT__Memory.data();
    return reinterpret_cast<uint8_t*>(words)+(address&0x7fffffffull);
}
extern "C" void iris_rtl_load_write(uint64_t address,size_t bytes,const void* data) {
    memcpy(checked_memory(address,bytes),data,bytes); iris_preloaded+=bytes;
    if(iris_preloaded<=1024) fprintf(stderr,"RTL_PRELOAD write address=%lx bytes=%zu total=%lu\n",address,bytes,iris_preloaded);
}
extern "C" void iris_rtl_load_read(uint64_t address,size_t bytes,void* data) { memcpy(data,checked_memory(address,bytes),bytes); }

// User VPI code adds to this array to get startup main() callbacks
extern "C" void (*vlog_startup_routines[])() VL_ATTR_WEAK;

//======================

int main(int argc, char** argv, char**) {
    // Setup context, defaults, and parse command line
    Verilated::debug(0);
    const std::unique_ptr<VerilatedContext> contextp{new VerilatedContext};
    contextp->threads(1);
    contextp->commandArgs(argc, argv);

    // Construct the Verilated model, from Vtop.h generated from Verilating
    const std::unique_ptr<VTestDriver> topp{new VTestDriver{contextp.get(), ""}};

    iris_root=topp->rootp;
    uint64_t next_report=10000;

    // Hook VPI startup routines and invoke callback
    if (vlog_startup_routines) {
        for (auto routinep = &vlog_startup_routines[0]; *routinep; routinep++) (*routinep)();
    }
    VerilatedVpi::callCbs(cbStartOfSimulation);

    // Simulate until $finish
    while (VL_LIKELY(!contextp->gotFinish())) {
        // VPI callbacks
        VerilatedVpi::callTimedCbs();
        VerilatedVpi::callCbs(cbNextSimTime);
        VerilatedVpi::callCbs(cbAtStartOfSimTime);
        // Evaluate model
        topp->eval();
        if(iris_root->TestDriver__DOT__trace_count>=next_report) {
            fprintf(stderr,"RTL_PROGRESS tb=%lu time=%lu preloaded=%lu pc0=%lx pc1=%lx pc2=%lx x5=%lx x6=%lx\n",iris_root->TestDriver__DOT__trace_count,contextp->time(),iris_preloaded,
            iris_root->TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain__DOT__element_reset_domain_shuttle_tile__DOT__core__DOT__com_uops_reg_0_bits_pc,
            iris_root->TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain_1__DOT__element_reset_domain_shuttle_tile__DOT__core__DOT__com_uops_reg_0_bits_pc,
            iris_root->TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain_2__DOT__element_reset_domain_rockettile__DOT__core__DOT__wb_reg_pc,
            iris_root->TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain__DOT__element_reset_domain_shuttle_tile__DOT__core__DOT__iregfile_5,
            iris_root->TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain__DOT__element_reset_domain_shuttle_tile__DOT__core__DOT__iregfile_6);
            iris_diag_state();
            iris_diag_deep();
            fflush(stdout);next_report+=10000;
        }
        // VPI callbacks
        VerilatedVpi::callValueCbs();
        VerilatedVpi::callCbs(cbAtEndOfSimTime);
        VerilatedVpi::callCbs(cbReadWriteSynch);
        VerilatedVpi::callCbs(cbReadOnlySynch);
        // Advance time
        if (!topp->eventsPending()) break;
        contextp->time(std::min(topp->nextTimeSlot(), VerilatedVpi::cbNextDeadline()));
    }

    if (VL_LIKELY(!contextp->gotFinish())) {
        VL_DEBUG_IF(VL_PRINTF("+ Exiting without $finish; no events left\n"););
    }

    // Execute 'final' processes
    topp->final();
    VerilatedVpi::callCbs(cbEndOfSimulation);

    // Print statistical summary report
    contextp->statsPrintSummary();

    return 0;
}
