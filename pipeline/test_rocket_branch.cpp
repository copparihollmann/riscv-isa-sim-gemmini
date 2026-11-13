#include "VRocketMemControl.h"
#include "verilated.h"
#include "rocket_branch.hpp"
#include <iostream>
#include <random>
#include <stdexcept>
int main() {
  VerilatedContext context;context.threads(1);VRocketMemControl dut(&context);std::mt19937_64 rng(0x1cace);
  constexpr uint64_t mask40=(uint64_t(1)<<40)-1;constexpr unsigned count=200000;uint64_t checks=0;
  for(unsigned i=0;i<count;++i){
    iris::frontend::RocketBranch::Input in;in.instruction=rng();in.pc=rng()&mask40;in.wdata=rng();in.valid=rng()&1;in.exception=rng()&1;in.compressed=rng()&1;
    const unsigned type=i%5;in.branch=type==1;in.jal=type==2;in.jalr=type==3;in.sfence=type==4;in.taken=rng()&1;
    in.ex_pc_valid=rng()&1;in.ibuf_valid=rng()&1;in.fetch_valid=rng()&1;in.take_pc_wb=rng()&1;in.ex_pc=rng()&mask40;in.ibuf_pc=rng()&mask40;
    // Exercise both exact-target and wrong-target comparator paths rather
    // than allowing random40-bit PCs to make every comparison a mismatch.
    auto prediction=iris::frontend::RocketBranch::resolve(in);
    if(i%4==0)in.ex_pc=prediction.next_pc;if(i%4==1)in.ibuf_pc=prediction.next_pc;
    dut.mem_reg_inst=in.instruction;dut.mem_reg_pc=in.pc;dut.mem_reg_wdata=in.wdata;dut.mem_reg_rvc=in.compressed;
    dut.mem_ctrl_branch=in.branch;dut.mem_ctrl_jal=in.jal;dut.mem_ctrl_jalr=in.jalr;dut.mem_ctrl_fp=0;dut.mem_ctrl_wxd=0;dut.mem_reg_sfence=in.sfence;
    dut.mem_br_taken=in.taken;dut.mem_reg_valid=in.valid;dut.mem_reg_xcpt=in.exception;
    dut.ex_reg_valid=in.ex_pc_valid&&i%3==0;dut.ex_reg_replay=in.ex_pc_valid&&i%3==1;dut.ex_reg_xcpt_interrupt=in.ex_pc_valid&&i%3==2;dut.ex_reg_pc=in.ex_pc;
    dut._ibuf_io_inst_0_valid=in.ibuf_valid;dut.io_imem_resp_valid=in.fetch_valid;dut._ibuf_io_pc=in.ibuf_pc;dut.take_pc_wb=in.take_pc_wb;
    dut._csr_io_status_isa=4;dut.io_fpu_toint_data=0;dut.eval();const auto out=iris::frontend::RocketBranch::resolve(in);
    auto check=[&](bool same){++checks;if(!same)throw std::runtime_error("Rocket source MEM control differs case="+std::to_string(i)+" check="+std::to_string(checks));};
    check(out.next_pc==dut.out_next_pc);check(out.wrong_npc==bool(dut.out_wrong_npc));check(out.redirect==bool(dut.out_take_pc&&!in.take_pc_wb));
    check((in.jalr&&!in.exception?out.link:in.wdata)==dut.out_int_wdata);
    check(out.btb_update==bool(dut.out_btb_update));check(out.btb_valid==bool(dut.out_btb_valid));check(out.cfi_type==dut.out_cfi_type);
    check(out.branch_pc==dut.out_branch_pc);check(out.fetch_pc==dut.out_fetch_pc);check(out.bht_update==bool(dut.out_bht_update));
  }
  std::cout<<"{\"status\":\"passed_source_Rocket_MEM_control_differential\",\"cases\":"<<count<<",\"checks\":"<<checks<<",\"C_present\":true,\"integer_only\":true}\n";
}
