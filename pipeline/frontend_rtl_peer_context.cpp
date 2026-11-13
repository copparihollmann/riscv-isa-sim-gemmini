#include "frontend_rtl_peer.hpp"
#include "VShuttleFrontend.h"
#include "verilated.h"
#include <stdexcept>
namespace iris::frontend {
struct SavedShuttleFrontend::Impl {
  VerilatedContext context;std::unique_ptr<VShuttleFrontend> dut;
  bool evaluated=false,request_fire=false,data_fire=false,outstanding=false;unsigned received_beats=0;
  Impl(uint64_t seed,unsigned reset_edges) {
    if(!seed || seed>uint64_t(INT32_MAX))throw std::invalid_argument("source frontend requires explicit nonzero31-bit unreset-state seed");
    if(reset_edges<2)throw std::invalid_argument("source frontend requires explicit reset initialization");
    Verilated::threadContextp(&context);context.randSeed(seed);context.randReset(2);context.threads(1);dut=std::make_unique<VShuttleFrontend>(&context);
#define dut (*this->dut)
#include "zero_inputs.inc"
#undef dut
    dut->io_ptw_status_prv=3;dut->io_ptw_ptbr_mode=0;dut->reset=1;
    for(unsigned i=0;i<reset_edges;++i)edge();
    dut->reset=0;dut->eval();
  }
  void edge() {Verilated::threadContextp(&context);dut->clock=1;dut->eval();context.timeInc(1);dut->clock=0;dut->eval();context.timeInc(1);}
};
SavedShuttleFrontend::SavedShuttleFrontend(uint64_t seed,unsigned reset_edges):impl_(std::make_unique<Impl>(seed,reset_edges)) {}
SavedShuttleFrontend::~SavedShuttleFrontend()=default;
SavedShuttleFrontend::SavedShuttleFrontend(SavedShuttleFrontend&&) noexcept=default;
SavedShuttleFrontend& SavedShuttleFrontend::operator=(SavedShuttleFrontend&&) noexcept=default;
SavedShuttleFrontend::Outputs SavedShuttleFrontend::evaluate(const Inputs& in) {
  Verilated::threadContextp(&impl_->context);impl_->evaluated=false;
  if(in.ready1 && !in.ready0)throw std::invalid_argument("source frontend dequeue readiness must be a prefix");
  if(in.redirect_pc>>40 || in.redirect_ras_head>7 || in.ras.head>7 || in.ras.address>>40 || in.btb.pc>>39 || in.btb.target>>39 || in.btb.branch_pc>>39 || in.btb.prediction_entry>63 || in.btb.cfi_type>3 || in.bht.pc>>39 || in.bht.history>255 || in.bht.value>3)
    throw std::invalid_argument("source frontend interface width exceeded");
  auto& d=*impl_->dut;
  d.auto_icache_master_out_a_ready=in.memory_request_ready;d.auto_icache_master_out_d_valid=bool(in.memory_data);
  d.auto_icache_master_out_d_bits_opcode=1;d.auto_icache_master_out_d_bits_size=6;
  if(in.memory_data)d.auto_icache_master_out_d_bits_data=in.memory_data->value;
  d.io_cpu_resp_0_ready=in.ready0;d.io_cpu_resp_1_ready=in.ready1;
  d.io_cpu_redirect_flush=in.redirect_flush;d.io_cpu_redirect_val=in.redirect_valid;d.io_cpu_redirect_pc=in.redirect_pc;d.io_cpu_redirect_ras_head=in.redirect_ras_head;
  d.io_cpu_flush_icache=in.invalidate_icache;
  d.io_cpu_btb_update_valid=in.btb.valid;d.io_cpu_btb_update_bits_isValid=in.btb.is_valid;d.io_cpu_btb_update_bits_mispredict=in.btb.mispredict;
  d.io_cpu_btb_update_bits_prediction_entry=in.btb.prediction_entry;d.io_cpu_btb_update_bits_cfiType=in.btb.cfi_type;
  d.io_cpu_btb_update_bits_pc=in.btb.pc;d.io_cpu_btb_update_bits_target=in.btb.target;d.io_cpu_btb_update_bits_br_pc=in.btb.branch_pc;
  d.io_cpu_bht_update_valid=in.bht.valid;d.io_cpu_bht_update_bits_branch=in.bht.branch;d.io_cpu_bht_update_bits_taken=in.bht.taken;d.io_cpu_bht_update_bits_mispredict=in.bht.mispredict;
  d.io_cpu_bht_update_bits_prediction_history=in.bht.history;d.io_cpu_bht_update_bits_prediction_value=in.bht.value;d.io_cpu_bht_update_bits_pc=in.bht.pc;
  d.io_cpu_ras_update_valid=in.ras.valid;d.io_cpu_ras_update_bits_head=in.ras.head;d.io_cpu_ras_update_bits_addr=in.ras.address;
  d.eval();
  if(in.memory_data && !impl_->outstanding)throw std::logic_error("source frontend data beat without accepted request");
  impl_->request_fire=d.auto_icache_master_out_a_valid && in.memory_request_ready;
  impl_->data_fire=bool(in.memory_data);
  if(impl_->request_fire && impl_->outstanding)throw std::logic_error("source frontend overlapped refill request");
  if(d.io_ptw_req_valid)throw std::runtime_error("source frontend VM walk is outside the qualified M-mode peer");
  Outputs out;out.memory_request_valid=d.auto_icache_master_out_a_valid;out.memory_request_address=d.auto_icache_master_out_a_bits_address;
#define COPY(lane) {auto& u=out.queue[lane];u.valid=d.io_cpu_resp_##lane##_valid;u.compressed=d.io_cpu_resp_##lane##_bits_rvc;u.edge_instruction=d.io_cpu_resp_##lane##_bits_edge_inst;u.exception=d.io_cpu_resp_##lane##_bits_xcpt;u.pc=d.io_cpu_resp_##lane##_bits_pc;u.exception_cause=d.io_cpu_resp_##lane##_bits_xcpt_cause;u.raw=d.io_cpu_resp_##lane##_bits_raw_inst;u.expanded=d.io_cpu_resp_##lane##_bits_inst;u.prediction_valid=d.io_cpu_resp_##lane##_bits_next_pc_valid;u.predicted_pc=d.io_cpu_resp_##lane##_bits_next_pc_bits;u.btb_valid=d.io_cpu_resp_##lane##_bits_btb_resp_valid;u.btb_entry=d.io_cpu_resp_##lane##_bits_btb_resp_bits_entry;u.bht_history=d.io_cpu_resp_##lane##_bits_btb_resp_bits_bht_history;u.bht_value=d.io_cpu_resp_##lane##_bits_btb_resp_bits_bht_value;u.small_forward_branch=d.io_cpu_resp_##lane##_bits_sfb_br;u.ras_head=d.io_cpu_resp_##lane##_bits_ras_head;}
  COPY(0);COPY(1);
#undef COPY
  impl_->evaluated=true;return out;
}
void SavedShuttleFrontend::commit() {
  Verilated::threadContextp(&impl_->context);
  if(!impl_->evaluated)throw std::logic_error("source frontend edge without evaluated peer inputs");
  impl_->edge();
  if(impl_->request_fire){impl_->outstanding=true;impl_->received_beats=0;}
  if(impl_->data_fire && ++impl_->received_beats==8)impl_->outstanding=false;
  impl_->evaluated=false;
}
}
