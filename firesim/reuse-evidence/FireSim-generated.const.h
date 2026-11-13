// Golden Gate-generated Driver Header
// This contains target-specific preprocessor macro definitions,
// and encodes all required bridge metadata to instantiate bridge drivers.
#ifdef GET_INCLUDES
#include "bridges/master.h"
#endif // GET_INCLUDES
#ifdef GET_SUBSTRUCT_CHECKS
static_assert(offsetof(SIMULATIONMASTER_struct, INIT_DONE) == 0 * sizeof(uint64_t), "invalid INIT_DONE");\
static_assert(offsetof(SIMULATIONMASTER_struct, PRESENCE_READ) == 1 * sizeof(uint64_t), "invalid PRESENCE_READ");\
static_assert(offsetof(SIMULATIONMASTER_struct, PRESENCE_WRITE) == 2 * sizeof(uint64_t), "invalid PRESENCE_WRITE");\
static_assert(sizeof(SIMULATIONMASTER_struct) == 3 * sizeof(uint64_t), "invalid structure"); \

#endif // SIMULATIONMASTER_checks
#ifdef GET_CORE_CONSTRUCTOR
registry.add_widget(new master_t(
  simif,
SIMULATIONMASTER_struct{
    .INIT_DONE = 352,
    .PRESENCE_READ = 356,
    .PRESENCE_WRITE = 360,
},
  0,
  args
  ));
#endif // GET_CORE_CONSTRUCTOR
#ifdef GET_INCLUDES
#include "bridges/peek_poke.h"
#endif // GET_INCLUDES
#ifdef GET_SUBSTRUCT_CHECKS
static_assert(offsetof(PEEKPOKEBRIDGEMODULE_struct, STEP) == 0 * sizeof(uint64_t), "invalid STEP");\
static_assert(offsetof(PEEKPOKEBRIDGEMODULE_struct, DONE) == 1 * sizeof(uint64_t), "invalid DONE");\
static_assert(offsetof(PEEKPOKEBRIDGEMODULE_struct, PRECISE_PEEKABLE) == 2 * sizeof(uint64_t), "invalid PRECISE_PEEKABLE");\
static_assert(sizeof(PEEKPOKEBRIDGEMODULE_struct) == 3 * sizeof(uint64_t), "invalid structure"); \

#endif // PEEKPOKEBRIDGEMODULE_checks
#ifdef GET_BRIDGE_CONSTRUCTOR
registry.add_widget(new peek_poke_t(
  simif,
PEEKPOKEBRIDGEMODULE_struct{
    .STEP = 268,
    .DONE = 272,
    .PRECISE_PEEKABLE = 280,
},
  0,
  args
  ,  std::map<std::string, peek_poke_t::Port, std::less<>>{std::make_pair(R"ESC(reset)ESC", peek_poke_t::Port{.address = 276ULL,.chunks = 1})}
,  std::map<std::string, peek_poke_t::Port, std::less<>>{}
));
#endif // GET_BRIDGE_CONSTRUCTOR
#ifdef GET_INCLUDES
#include "bridges/reset_pulse.h"
#endif // GET_INCLUDES
#ifdef GET_SUBSTRUCT_CHECKS
static_assert(offsetof(RESETPULSEBRIDGEMODULE_struct, pulseLength) == 0 * sizeof(uint64_t), "invalid pulseLength");\
static_assert(offsetof(RESETPULSEBRIDGEMODULE_struct, doneInit) == 1 * sizeof(uint64_t), "invalid doneInit");\
static_assert(sizeof(RESETPULSEBRIDGEMODULE_struct) == 2 * sizeof(uint64_t), "invalid structure"); \

#endif // RESETPULSEBRIDGEMODULE_checks
#ifdef GET_BRIDGE_CONSTRUCTOR
registry.add_widget(new reset_pulse_t(
  simif,
RESETPULSEBRIDGEMODULE_struct{
    .pulseLength = 368,
    .doneInit = 372,
},
  0,
  args
  ,  1023
,  50
));
#endif // GET_BRIDGE_CONSTRUCTOR
#ifdef GET_INCLUDES
#include "bridges/uart.h"
#endif // GET_INCLUDES
#ifdef GET_SUBSTRUCT_CHECKS
static_assert(offsetof(UARTBRIDGEMODULE_struct, out_bits) == 0 * sizeof(uint64_t), "invalid out_bits");\
static_assert(offsetof(UARTBRIDGEMODULE_struct, out_valid) == 1 * sizeof(uint64_t), "invalid out_valid");\
static_assert(offsetof(UARTBRIDGEMODULE_struct, out_ready) == 2 * sizeof(uint64_t), "invalid out_ready");\
static_assert(offsetof(UARTBRIDGEMODULE_struct, in_bits) == 3 * sizeof(uint64_t), "invalid in_bits");\
static_assert(offsetof(UARTBRIDGEMODULE_struct, in_valid) == 4 * sizeof(uint64_t), "invalid in_valid");\
static_assert(offsetof(UARTBRIDGEMODULE_struct, in_ready) == 5 * sizeof(uint64_t), "invalid in_ready");\
static_assert(sizeof(UARTBRIDGEMODULE_struct) == 6 * sizeof(uint64_t), "invalid structure"); \

#endif // UARTBRIDGEMODULE_checks
#ifdef GET_BRIDGE_CONSTRUCTOR
registry.add_widget(new uart_t(
  simif,
UARTBRIDGEMODULE_struct{
    .out_bits = 288,
    .out_valid = 292,
    .out_ready = 296,
    .in_bits = 300,
    .in_valid = 304,
    .in_ready = 308,
},
  0,
  args
  ));
#endif // GET_BRIDGE_CONSTRUCTOR
#ifdef GET_INCLUDES
#include "bridges/tsibridge.h"
#endif // GET_INCLUDES
#ifdef GET_SUBSTRUCT_CHECKS
static_assert(offsetof(TSIBRIDGEMODULE_struct, in_bits) == 0 * sizeof(uint64_t), "invalid in_bits");\
static_assert(offsetof(TSIBRIDGEMODULE_struct, in_valid) == 1 * sizeof(uint64_t), "invalid in_valid");\
static_assert(offsetof(TSIBRIDGEMODULE_struct, in_ready) == 2 * sizeof(uint64_t), "invalid in_ready");\
static_assert(offsetof(TSIBRIDGEMODULE_struct, out_bits) == 3 * sizeof(uint64_t), "invalid out_bits");\
static_assert(offsetof(TSIBRIDGEMODULE_struct, out_valid) == 4 * sizeof(uint64_t), "invalid out_valid");\
static_assert(offsetof(TSIBRIDGEMODULE_struct, out_ready) == 5 * sizeof(uint64_t), "invalid out_ready");\
static_assert(offsetof(TSIBRIDGEMODULE_struct, step_size) == 6 * sizeof(uint64_t), "invalid step_size");\
static_assert(offsetof(TSIBRIDGEMODULE_struct, done) == 7 * sizeof(uint64_t), "invalid done");\
static_assert(offsetof(TSIBRIDGEMODULE_struct, start) == 8 * sizeof(uint64_t), "invalid start");\
static_assert(sizeof(TSIBRIDGEMODULE_struct) == 9 * sizeof(uint64_t), "invalid structure"); \

#endif // TSIBRIDGEMODULE_checks
#ifdef GET_BRIDGE_CONSTRUCTOR
registry.add_widget(new tsibridge_t(
  simif,
  registry.get_widget<loadmem_t>(),
TSIBRIDGEMODULE_struct{
    .in_bits = 128,
    .in_valid = 132,
    .in_ready = 136,
    .out_bits = 140,
    .out_valid = 144,
    .out_ready = 148,
    .step_size = 152,
    .done = 156,
    .start = 160,
},
  0,
  args
  ,  true
,  -2147483648ULL
));
#endif // GET_BRIDGE_CONSTRUCTOR
#ifdef GET_INCLUDES
#include "bridges/fased_memory_timing_model.h"
#endif // GET_INCLUDES
#ifdef GET_BRIDGE_CONSTRUCTOR
registry.add_widget(new FASEDMemoryTimingModel(
  simif,
  AddressMap{
    std::vector<std::pair<std::string, uint32_t>>{
      { R"ESC(writeLatency)ESC", 0 },\
      { R"ESC(readLatency)ESC", 4 },\
      { R"ESC(writeMaxReqs)ESC", 8 },\
      { R"ESC(readMaxReqs)ESC", 12 },\
      { R"ESC(writeOutstandingHistogram_0)ESC", 16 },\
      { R"ESC(writeOutstandingHistogram_1)ESC", 20 },\
      { R"ESC(writeOutstandingHistogram_2)ESC", 24 },\
      { R"ESC(writeOutstandingHistogram_3)ESC", 28 },\
      { R"ESC(writeOutstandingHistogram_4)ESC", 32 },\
      { R"ESC(readOutstandingHistogram_0)ESC", 36 },\
      { R"ESC(readOutstandingHistogram_1)ESC", 40 },\
      { R"ESC(readOutstandingHistogram_2)ESC", 44 },\
      { R"ESC(readOutstandingHistogram_3)ESC", 48 },\
      { R"ESC(readOutstandingHistogram_4)ESC", 52 },\
      { R"ESC(totalWriteBeats)ESC", 56 },\
      { R"ESC(totalReadBeats)ESC", 60 },\
      { R"ESC(totalWrites)ESC", 64 },\
      { R"ESC(totalReads)ESC", 68 },\
      { R"ESC(relaxFunctionalModel)ESC", 72 },\
      { R"ESC(rrespError)ESC", 76 },\
      { R"ESC(brespError)ESC", 80 },\
    },
    std::vector<std::pair<std::string, uint32_t>>{
      { R"ESC(writeLatency)ESC", 0 },\
      { R"ESC(readLatency)ESC", 4 },\
      { R"ESC(writeMaxReqs)ESC", 8 },\
      { R"ESC(readMaxReqs)ESC", 12 },\
      { R"ESC(relaxFunctionalModel)ESC", 72 },\
    }
  },
  0,
  args
  ,  R"ESC(memory_stats0.csv)ESC"
,  1L << 33
));
#endif // GET_BRIDGE_CONSTRUCTOR
#ifdef GET_INCLUDES
#include "bridges/clock.h"
#endif // GET_INCLUDES
#ifdef GET_SUBSTRUCT_CHECKS
static_assert(offsetof(CLOCKBRIDGEMODULE_struct, hCycle_0) == 0 * sizeof(uint64_t), "invalid hCycle_0");\
static_assert(offsetof(CLOCKBRIDGEMODULE_struct, hCycle_1) == 1 * sizeof(uint64_t), "invalid hCycle_1");\
static_assert(offsetof(CLOCKBRIDGEMODULE_struct, hCycle_latch) == 2 * sizeof(uint64_t), "invalid hCycle_latch");\
static_assert(offsetof(CLOCKBRIDGEMODULE_struct, tCycle_0) == 3 * sizeof(uint64_t), "invalid tCycle_0");\
static_assert(offsetof(CLOCKBRIDGEMODULE_struct, tCycle_1) == 4 * sizeof(uint64_t), "invalid tCycle_1");\
static_assert(offsetof(CLOCKBRIDGEMODULE_struct, tCycle_latch) == 5 * sizeof(uint64_t), "invalid tCycle_latch");\
static_assert(sizeof(CLOCKBRIDGEMODULE_struct) == 6 * sizeof(uint64_t), "invalid structure"); \

#endif // CLOCKBRIDGEMODULE_checks
#ifdef GET_BRIDGE_CONSTRUCTOR
registry.add_widget(new clockmodule_t(
  simif,
CLOCKBRIDGEMODULE_struct{
    .hCycle_0 = 320,
    .hCycle_1 = 324,
    .hCycle_latch = 328,
    .tCycle_0 = 332,
    .tCycle_1 = 336,
    .tCycle_latch = 340,
},
  0,
  args
  ));
#endif // GET_BRIDGE_CONSTRUCTOR
#ifdef GET_INCLUDES
#include "bridges/loadmem.h"
#endif // GET_INCLUDES
#ifdef GET_SUBSTRUCT_CHECKS
static_assert(offsetof(LOADMEMWIDGET_struct, W_ADDRESS_H) == 0 * sizeof(uint64_t), "invalid W_ADDRESS_H");\
static_assert(offsetof(LOADMEMWIDGET_struct, W_ADDRESS_L) == 1 * sizeof(uint64_t), "invalid W_ADDRESS_L");\
static_assert(offsetof(LOADMEMWIDGET_struct, W_LENGTH) == 2 * sizeof(uint64_t), "invalid W_LENGTH");\
static_assert(offsetof(LOADMEMWIDGET_struct, ZERO_OUT_DRAM) == 3 * sizeof(uint64_t), "invalid ZERO_OUT_DRAM");\
static_assert(offsetof(LOADMEMWIDGET_struct, W_DATA) == 4 * sizeof(uint64_t), "invalid W_DATA");\
static_assert(offsetof(LOADMEMWIDGET_struct, ZERO_FINISHED) == 5 * sizeof(uint64_t), "invalid ZERO_FINISHED");\
static_assert(offsetof(LOADMEMWIDGET_struct, R_ADDRESS_H) == 6 * sizeof(uint64_t), "invalid R_ADDRESS_H");\
static_assert(offsetof(LOADMEMWIDGET_struct, R_ADDRESS_L) == 7 * sizeof(uint64_t), "invalid R_ADDRESS_L");\
static_assert(offsetof(LOADMEMWIDGET_struct, R_DATA) == 8 * sizeof(uint64_t), "invalid R_DATA");\
static_assert(sizeof(LOADMEMWIDGET_struct) == 9 * sizeof(uint64_t), "invalid structure"); \

#endif // LOADMEMWIDGET_checks
#ifdef GET_CORE_CONSTRUCTOR
registry.add_widget(new loadmem_t(
  simif,
LOADMEMWIDGET_struct{
    .W_ADDRESS_H = 192,
    .W_ADDRESS_L = 196,
    .W_LENGTH = 200,
    .ZERO_OUT_DRAM = 204,
    .W_DATA = 208,
    .ZERO_FINISHED = 212,
    .R_ADDRESS_H = 216,
    .R_ADDRESS_L = 220,
    .R_DATA = 224,
},
  0,
  args
  ,  conf_target.mem
,  2
));
#endif // GET_CORE_CONSTRUCTOR
#ifdef GET_METASIM_INTERFACE_CONFIG
static constexpr TargetConfig conf_target{
.ctrl = AXI4Config{12, 25, 32},
.mem = AXI4Config{16, 33, 64},
.mem_num_channels = 1,
.cpu_managed = std::nullopt,
.fpga_managed = std::nullopt,
.qsfp = FPGATopQSFPConfig{256, 0},
.target_name = R"ESC(FireSim)ESC"
};
#undef GET_METASIM_INTERFACE_CONFIG
#endif // GET_METASIM_INTERFACE_CONFIG
