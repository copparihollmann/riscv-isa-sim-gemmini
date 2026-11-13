#include "VSaturnCompute.h"
#include "VSaturnCompute___024root.h"
#include "VSaturnRocket.h"
#include "VSaturnRocket___024root.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
struct Sweep {bool active;unsigned cursor;};
static void require(bool value,const char*why){if(!value)throw std::runtime_error(why);}
static void inputs(VSaturnCompute&m){
m.clock=0;
m.reset=0;
m.auto_atl_out_a_ready=0;
m.auto_atl_out_d_valid=0;
m.auto_atl_out_d_bits_opcode=0;
m.auto_atl_out_d_bits_param=0;
m.auto_atl_out_d_bits_size=0;
m.auto_atl_out_d_bits_source=0;
m.auto_atl_out_d_bits_sink=0;
m.auto_atl_out_d_bits_denied=0;
m.auto_atl_out_d_bits_data[0]=0;
m.auto_atl_out_d_bits_data[1]=0;
m.auto_atl_out_d_bits_data[2]=0;
m.auto_atl_out_d_bits_data[3]=0;
m.auto_atl_out_d_bits_data[4]=0;
m.auto_atl_out_d_bits_data[5]=0;
m.auto_atl_out_d_bits_data[6]=0;
m.auto_atl_out_d_bits_data[7]=0;
m.auto_atl_out_d_bits_corrupt=0;
m.io_status_prv=0;
m.io_ex_valid=0;
m.io_ex_uop_inst=0;
m.io_ex_uop_pc=0;
m.io_ex_uop_rs1_data=0;
m.io_ex_uop_rs2_data=0;
m.io_ex_vconfig_vl=0;
m.io_ex_vconfig_vtype_vill=0;
m.io_ex_vconfig_vtype_tm=0;
m.io_ex_vconfig_vtype_tk=0;
m.io_ex_vconfig_vtype_vtwiden=0;
m.io_ex_vconfig_vtype_altfmt=0;
m.io_ex_vconfig_vtype_vma=0;
m.io_ex_vconfig_vtype_vta=0;
m.io_ex_vconfig_vtype_vsew=0;
m.io_ex_vconfig_vtype_vlmul_sign=0;
m.io_ex_vconfig_vtype_vlmul_mag=0;
m.io_ex_vstart=0;
m.io_ex_fire=0;
m.io_mem_kill=0;
m.io_mem_tlb_req_ready=0;
m.io_mem_tlb_resp_miss=0;
m.io_mem_tlb_resp_paddr=0;
m.io_mem_tlb_resp_pf_ld=0;
m.io_mem_tlb_resp_pf_st=0;
m.io_mem_tlb_resp_ae_ld=0;
m.io_mem_tlb_resp_ae_st=0;
m.io_mem_tlb_resp_ma_ld=0;
m.io_mem_tlb_resp_ma_st=0;
m.io_mem_frs1=0;
m.io_com_store_pending=0;
m.io_com_vxrm=0;
m.io_com_frm=0;
m.io_com_scalar_check_bits_addr=0;
m.io_com_scalar_check_bits_store=0;
m.io_resp_ready=0;
m.io_status_prv=3;m.io_resp_ready=1;
}
static void command(VSaturnCompute&m,bool enable){m.io_ex_valid=enable;m.io_ex_fire=enable;m.io_ex_uop_inst=0x428022d7;m.io_ex_uop_pc=0x80001000;m.io_ex_vconfig_vl=1;m.io_ex_vconfig_vtype_vsew=3;}
static Sweep sweep(VSaturnCompute&m){return {bool(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__resetting),unsigned(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__reset_ctr)} ;}
static std::uint32_t ram(VSaturnCompute&m,unsigned eg,unsigned word){switch(eg%4){
case 0:return m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__vrf_ext__DOT__Memory[eg/4][word];
case 1:return m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__vrf_ext__DOT__Memory[eg/4][word];
case 2:return m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__vrf_ext__DOT__Memory[eg/4][word];
case 3:return m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__vrf_ext__DOT__Memory[eg/4][word];
}throw std::logic_error("Invalid bank");}
static unsigned writes(VSaturnCompute&m,unsigned eg){unsigned seen=0;
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_valid){require(eg%4==0,"Scrub selected wrong bank");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_eg==eg/4,"Scrub wrote wrong bank address");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");++seen;}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_valid){require(eg%4==1,"Scrub selected wrong bank");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_eg==eg/4,"Scrub wrote wrong bank address");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");++seen;}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_valid){require(eg%4==2,"Scrub selected wrong bank");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_eg==eg/4,"Scrub wrote wrong bank address");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");++seen;}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_valid){require(eg%4==3,"Scrub selected wrong bank");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_eg==eg/4,"Scrub wrote wrong bank address");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");++seen;}
return seen;}
static bool response(VSaturnCompute&m){return m.io_resp_valid;}
static void check_response(VSaturnCompute&m,bool corrupt){require(m.io_resp_bits_rd==5&&!m.io_resp_bits_fp,"Wrong scalar readback destination");require((m.io_resp_bits_data^(corrupt?1:0))==0,"Reset-scrub architectural readback is nonzero");}
static std::uint64_t tile_observation(VSaturnCompute&m){std::uint64_t h=1469598103934665603ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_0)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_1)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_2)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_3)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_4)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_5)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_6)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_7)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_8)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_9)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_10)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_11)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_12)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_13)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_14)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_15)*1099511628211ULL;return h;}
static void inputs(VSaturnRocket&m){
m.clock=0;
m.reset=0;
m.auto_atl_out_a_ready=0;
m.auto_atl_out_d_valid=0;
m.auto_atl_out_d_bits_opcode=0;
m.auto_atl_out_d_bits_param=0;
m.auto_atl_out_d_bits_size=0;
m.auto_atl_out_d_bits_source=0;
m.auto_atl_out_d_bits_sink=0;
m.auto_atl_out_d_bits_denied=0;
m.auto_atl_out_d_bits_data=0;
m.auto_atl_out_d_bits_corrupt=0;
m.io_core_status_dv=0;
m.io_core_status_prv=0;
m.io_core_ex_valid=0;
m.io_core_ex_inst=0;
m.io_core_ex_pc=0;
m.io_core_ex_vconfig_vl=0;
m.io_core_ex_vconfig_vtype_vill=0;
m.io_core_ex_vconfig_vtype_vtwiden=0;
m.io_core_ex_vconfig_vtype_altfmt=0;
m.io_core_ex_vconfig_vtype_vma=0;
m.io_core_ex_vconfig_vtype_vta=0;
m.io_core_ex_vconfig_vtype_vsew=0;
m.io_core_ex_vconfig_vtype_vlmul_sign=0;
m.io_core_ex_vconfig_vtype_vlmul_mag=0;
m.io_core_ex_vstart=0;
m.io_core_ex_rs1=0;
m.io_core_ex_rs2=0;
m.io_core_killm=0;
m.io_core_mem_frs1=0;
m.io_core_wb_store_pending=0;
m.io_core_wb_vxrm=0;
m.io_core_wb_frm=0;
m.io_core_resp_ready=0;
m.io_tlb_s1_resp_miss=0;
m.io_tlb_s1_resp_paddr=0;
m.io_tlb_s1_resp_pf_ld=0;
m.io_tlb_s1_resp_pf_st=0;
m.io_tlb_s1_resp_ae_ld=0;
m.io_tlb_s1_resp_ae_st=0;
m.io_tlb_s1_resp_ma_ld=0;
m.io_tlb_s1_resp_ma_st=0;
m.io_tlb_s1_resp_cmd=0;
m.io_dmem_req_ready=0;
m.io_dmem_s2_nack=0;
m.io_dmem_resp_valid=0;
m.io_dmem_resp_bits_tag=0;
m.io_dmem_resp_bits_data_raw[0]=0;
m.io_dmem_resp_bits_data_raw[1]=0;
m.io_dmem_resp_bits_data_raw[2]=0;
m.io_dmem_resp_bits_data_raw[3]=0;
m.io_dmem_resp_bits_data_raw[4]=0;
m.io_dmem_resp_bits_data_raw[5]=0;
m.io_dmem_resp_bits_data_raw[6]=0;
m.io_dmem_resp_bits_data_raw[7]=0;
m.io_dmem_s2_xcpt_ma_ld=0;
m.io_dmem_s2_xcpt_ma_st=0;
m.io_dmem_s2_xcpt_pf_ld=0;
m.io_dmem_s2_xcpt_pf_st=0;
m.io_dmem_s2_xcpt_ae_ld=0;
m.io_dmem_s2_xcpt_ae_st=0;
m.io_fp_req_ready=0;
m.io_fp_resp_valid=0;
m.io_fp_resp_bits_data[0]=0;
m.io_fp_resp_bits_data[1]=0;
m.io_fp_resp_bits_data[2]=0;
m.io_core_status_prv=3;m.io_core_resp_ready=1;
}
static void command(VSaturnRocket&m,bool enable){m.io_core_ex_valid=enable;m.io_core_ex_inst=0x428022d7;m.io_core_ex_pc=0x80001000;m.io_core_ex_vconfig_vl=1;m.io_core_ex_vconfig_vtype_vsew=3;}
static Sweep sweep(VSaturnRocket&m){return {bool(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__resetting),unsigned(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__reset_ctr)} ;}
static std::uint32_t ram(VSaturnRocket&m,unsigned eg,unsigned word){switch(eg%1){
case 0:return m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__vrf_ext__DOT__Memory[eg/1][word];
}throw std::logic_error("Invalid bank");}
static unsigned writes(VSaturnRocket&m,unsigned eg){unsigned seen=0;
if(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_valid){require(eg%1==0,"Scrub selected wrong bank");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_eg==eg/1,"Scrub wrote wrong bank address");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[4]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[4]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[5]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[5]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[6]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[6]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[7]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[7]==0xffffffffu,"Scrub mask not full width");++seen;}
return seen;}
static bool response(VSaturnRocket&m){return m.io_core_resp_valid;}
static void check_response(VSaturnRocket&m,bool corrupt){require(m.io_core_resp_bits_rd==5&&!m.io_core_resp_bits_fp,"Wrong scalar readback destination");require((m.io_core_resp_bits_data^(corrupt?1:0))==0,"Reset-scrub architectural readback is nonzero");}
static std::uint64_t tile_observation(VSaturnRocket&m){std::uint64_t h=1469598103934665603ULL;return h;}
template<class M>static void run(const char*name,unsigned egs,unsigned dlen,unsigned seed,bool corrupt){
 auto context=std::make_unique<VerilatedContext>();context->threads(1);context->randSeed(seed);context->randReset(2);M m(context.get());inputs(m);m.reset=1;m.clock=0;m.eval();
 std::uint64_t before_nonzero=0;for(unsigned eg=0;eg<egs;eg++)for(unsigned w=0;w<dlen/32;w++)before_nonzero+=ram(m,eg,w)!=0;
 for(unsigned r=0;r<2;r++){m.clock=1;m.eval();m.clock=0;m.eval();}
 auto tile=tile_observation(m);unsigned response_edge=~0u,write_checks=0,zero_checks=0;std::uint64_t seen=0;m.reset=0;
 for(unsigned edge=0;edge<egs+24;edge++){
  command(m,edge==0);m.eval();auto state=sweep(m);
  if(edge<egs){require(state.active&&state.cursor==edge,"Source scrub progression differs from actual EG count");require(writes(m,edge)==1,"Reset sweep write not accepted by actual bank");if(egs<64||edge<64)seen|=1ULL<<edge;++write_checks;require(!response(m),"Vector read escaped reset-scrub read blocking");}
  else require(!state.active,"Scrub did not complete at exact source boundary");
  if(response(m)){require(response_edge==~0u,"Duplicate scalar response");check_response(m,corrupt);response_edge=edge;}
  m.clock=1;m.eval();m.clock=0;m.eval();
  unsigned cleared=edge<egs?edge+1:egs;for(unsigned eg=0;eg<cleared;eg++)for(unsigned w=0;w<dlen/32;w++){require(ram(m,eg,w)==0,"Scrubbed physical VRF bit is nonzero");++zero_checks;}
 }
 require(response_edge!=~0u&&response_edge>=egs,"Queued architectural readback did not complete after scrub");require(tile_observation(m)==tile,"Idle reset-scrub unexpectedly modified sampled tile entries");
 std::cout<<"SCRUB_RESULT {\"profile\":\""<<name<<"\",\"seed\":"<<seed<<",\"post_reset_scrub_edges\":"<<egs<<",\"accepted_full_EG_writes\":"<<write_checks<<",\"zero_word_checks\":"<<zero_checks<<",\"pre_reset_nonzero_words_observed\":"<<before_nonzero<<",\"early_readback_response_edge\":"<<response_edge<<",\"sampled_tile_state_preserved\":true}\n";
}
int main(int argc,char**argv){try{bool corrupt=argc==2&&std::string(argv[1])=="--corrupt-readback";for(unsigned seed:{0u,1u,17u,91u}){run<VSaturnCompute>("compute",64,128,seed,corrupt);run<VSaturnRocket>("rocket",32,256,seed,corrupt);}return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
